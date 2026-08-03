import base64
import os
import importlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import threading
import uuid

from config import IGNORED_PARTS


PROBE_OUTPUT_LIMIT = 100 * 1024
PROBE_PAYLOAD_LIMIT = 100 * 1024
_PROBE_PROTOCOL_LIMIT = 256 * 1024
EXECUTION_CAPTURE_LIMIT = 100 * 1024
ISOLATED_CONTROLLER_CAPTURE_LIMIT = 256 * 1024
ALLOWED_CPP_HARNESS_OPTIONS = frozenset({
    "-O1",
    "-O2",
    "-fno-omit-frame-pointer",
    "-fsanitize=address,undefined",
})


class ExecutionException(Exception):
    pass


class SolutionException(Exception):
    pass


_ISOLATED_PROBE_CHILD = r"""
import base64
import builtins
import io
import json
import math
import os
import resource
import sys
import tempfile

OUTPUT_LIMIT = 100 * 1024
PAYLOAD_LIMIT = 100 * 1024
PROTOCOL_FD = os.dup(sys.stdout.fileno())
PROTOCOL_INPUT = sys.stdin.buffer


def send_frame(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    os.write(PROTOCOL_FD, encoded + b"\n")


def safe_error(error):
    return type(error).__name__


def bounded_jsonable(value, budget, depth=0):
    if depth > 20:
        raise ValueError("payload is nested too deeply")
    if value is None or isinstance(value, (bool, int)):
        budget[0] -= 8
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number in payload")
        budget[0] -= 24
        return value
    if isinstance(value, str):
        budget[0] -= len(value.encode("utf-8")) + 2
        if budget[0] < 0:
            raise ValueError("payload is too large")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 4096:
            raise ValueError("payload has too many items")
        result = []
        for item in value:
            budget[0] -= 1
            result.append(bounded_jsonable(item, budget, depth + 1))
        return result
    if isinstance(value, dict):
        if len(value) > 4096:
            raise ValueError("payload has too many items")
        result = {}
        for key, item in value.items():
            if not isinstance(key, (str, int, float, bool)) and key is not None:
                raise ValueError("payload has an unsupported key")
            safe_key = str(key)
            budget[0] -= len(safe_key.encode("utf-8")) + 2
            result[safe_key] = bounded_jsonable(item, budget, depth + 1)
        return result
    raise ValueError("payload contains an unsupported value")


def read_frame():
    raw = PROTOCOL_INPUT.readline(256 * 1024 + 1)
    if not raw or len(raw) > 256 * 1024:
        raise ValueError("invalid controller frame")
    return json.loads(raw)


capture = tempfile.TemporaryFile(mode="w+b")
os.dup2(capture.fileno(), sys.stdout.fileno())
os.dup2(capture.fileno(), sys.stderr.fileno())
sys.stdout = io.TextIOWrapper(
    os.fdopen(os.dup(1), "wb", closefd=True),
    encoding="utf-8",
    errors="replace",
    write_through=True,
)
sys.stderr = io.TextIOWrapper(
    os.fdopen(os.dup(2), "wb", closefd=True),
    encoding="utf-8",
    errors="replace",
    write_through=True,
)

try:
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    file_limit = OUTPUT_LIMIT + 1
    if hard_limit != resource.RLIM_INFINITY:
        file_limit = min(file_limit, hard_limit)
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, hard_limit))
except (OSError, ValueError):
    pass

try:
    initial = read_frame()
    source = base64.b64decode(initial["source"], validate=True).decode("utf-8")
    input_data = base64.b64decode(
        initial.get("input", ""),
        validate=True,
    ).decode("utf-8")
    namespace = {
        "__name__": "__student__",
        "__builtins__": builtins.__dict__,
    }
    sys.stdin = io.StringIO(input_data)
    exec(compile(source, "<student>", "exec"), namespace, namespace)
except BaseException as error:
    send_frame({"type": "load_error", "error": safe_error(error)})
    raise SystemExit(0)

send_frame({"type": "ready"})

try:
    command = read_frame()
    nonce = command["nonce"]
    probe = base64.b64decode(command["probe"], validate=True).decode("utf-8")
    namespace["__gc_json"] = json
    try:
        exec(compile(probe, "<trusted-probe>", "exec"), namespace, namespace)
        payload = namespace.get(
            "__gc_payload",
            {"__error__": "проверочный сценарий не вернул результат"},
        )
    except BaseException as error:
        payload = {"__error__": safe_error(error)}

    try:
        payload = bounded_jsonable(payload, [PAYLOAD_LIMIT])
    except (TypeError, ValueError):
        payload = {"__error__": "ответ проверочного сценария слишком велик"}

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:
        pass
    capture.seek(0)
    output_bytes = capture.read(OUTPUT_LIMIT + 1)
    output_truncated = len(output_bytes) > OUTPUT_LIMIT
    output = output_bytes[:OUTPUT_LIMIT].decode("utf-8", errors="replace")
    if output_truncated:
        payload = {"__error__": "вывод программы превышает 100 КиБ"}

    send_frame(
        {
            "type": "result",
            "nonce": nonce,
            "output_b64": base64.b64encode(
                output.encode("utf-8")
            ).decode("ascii"),
            "payload": payload,
        }
    )
except BaseException as error:
    send_frame({"type": "driver_error", "error": safe_error(error)})
"""


def build_isolated_probe_controller(source_code, probe_source, input_data=""):
    encoded_source = base64.b64encode(source_code.encode("utf-8")).decode("ascii")
    encoded_probe = base64.b64encode(probe_source.encode("utf-8")).decode("ascii")
    encoded_input = base64.b64encode(input_data.encode("utf-8")).decode("ascii")
    child_literal = repr(textwrap.dedent(_ISOLATED_PROBE_CHILD))

    return f"""
import base64
import json
import secrets
import subprocess
import sys

CHILD_SOURCE = {child_literal}
INITIAL_FRAME = {{
    "source": {encoded_source!r},
    "input": {encoded_input!r},
}}
PROBE = {encoded_probe!r}
FRAME_LIMIT = {_PROBE_PROTOCOL_LIMIT}
OUTPUT_LIMIT = {PROBE_OUTPUT_LIMIT}
PAYLOAD_LIMIT = {PROBE_PAYLOAD_LIMIT}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def read_frame(stream):
    raw = stream.readline(FRAME_LIMIT + 1)
    if not raw or len(raw) > FRAME_LIMIT:
        raise ValueError("invalid child frame")
    return json.loads(raw)


process = subprocess.Popen(
    [sys.executable, "-I", "-B", "-u", "-c", CHILD_SOURCE],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

try:
    process.stdin.write(
        json.dumps(INITIAL_FRAME, separators=(",", ":")).encode("utf-8") + b"\\n"
    )
    process.stdin.flush()
    ready = read_frame(process.stdout)
    if ready != {{"type": "ready"}}:
        raise ValueError("student source did not become ready")

    nonce = secrets.token_hex(32)
    command = {{"nonce": nonce, "probe": PROBE}}
    process.stdin.write(
        json.dumps(command, separators=(",", ":")).encode("utf-8") + b"\\n"
    )
    process.stdin.close()

    frames = []
    while True:
        raw = process.stdout.readline(FRAME_LIMIT + 1)
        if not raw:
            break
        if len(raw) > FRAME_LIMIT:
            frames.append(None)
            break
        try:
            frames.append(json.loads(raw))
        except json.JSONDecodeError:
            frames.append(None)

    stderr = process.stderr.read(4097)
    return_code = process.wait()
    valid = (
        return_code == 0
        and not stderr
        and len(frames) == 1
        and isinstance(frames[0], dict)
        and frames[0].get("type") == "result"
        and secrets.compare_digest(str(frames[0].get("nonce", "")), nonce)
        and isinstance(frames[0].get("output_b64"), str)
        and isinstance(frames[0].get("payload"), dict)
    )
    if not valid:
        emit({{"ok": False, "error": "student protocol validation failed"}})
    else:
        try:
            encoded_output = base64.b64decode(
                frames[0]["output_b64"],
                validate=True,
            )
        except (ValueError, TypeError):
            encoded_output = b""
            valid = False
        encoded_payload = json.dumps(
            frames[0]["payload"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if (
            not valid
            or len(encoded_output) > OUTPUT_LIMIT
            or len(encoded_payload) > PAYLOAD_LIMIT
        ):
            emit({{"ok": False, "error": "student result exceeds the limit"}})
        else:
            emit(
                {{
                    "ok": True,
                    "output_b64": frames[0]["output_b64"],
                    "payload": frames[0]["payload"],
                }}
            )
except BaseException:
    if process.poll() is None:
        process.kill()
    process.wait()
    emit({{"ok": False, "error": "isolated probe failed"}})
"""


def _run_process_bounded(command, input_bytes, timeout, capture_limit):
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()

    def drain(stream, destination):
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            remaining = capture_limit - len(destination)
            if remaining > 0:
                destination.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()
                try:
                    process.kill()
                except OSError:
                    pass

    def write_input():
        try:
            if input_bytes:
                process.stdin.write(input_bytes)
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    readers = [
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr),
            daemon=True,
        ),
    ]
    writer = threading.Thread(target=write_input, daemon=True)
    for thread in readers:
        thread.start()
    writer.start()

    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        for thread in readers:
            thread.join()
        writer.join()
        process.stdout.close()
        process.stderr.close()
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=bytes(stdout),
            stderr=bytes(stderr),
        ) from error

    for thread in readers:
        thread.join()
    writer.join()
    process.stdout.close()
    process.stderr.close()
    return return_code, bytes(stdout), bytes(stderr), overflow.is_set()


class ExecutionContainer:
    _docker_checked = False
    _harness_docker_timeout = 10
    _harness_compile_timeout = max(
        1,
        int(os.getenv("CPP_HARNESS_COMPILE_TIMEOUT", "10")),
    )

    def __init__(self, language, template_path, code):
        try:
            self.container_id = None
            self.path = None
            self._unusable = False
            self.language = language
            self.code = code
            self.session_id = str(uuid.uuid4())
            self._template_ignored_parts = set(IGNORED_PARTS) | {"__pycache__"}
            self._pip_cache_volume = os.getenv("DOCKER_PIP_CACHE_VOLUME", "geekpaste_pip_cache")
            self._docker_transfer_mode = os.getenv("DOCKER_TRANSFER_MODE", "bind").strip().lower()

            self.check()

            self.path = self.get_path()
            self.create_execution_folder(template_path)
            self.container_id = self.prepare()
            self.setup()
        except SolutionException as e:
            print(e)
            self.cleanup()
            raise e
        except ExecutionException as e:
            print(e)
            self.cleanup()
            raise e
        except Exception as e:
            print(e)
            self.cleanup()
            raise ExecutionException(e)

    def __del__(self):
        print("deleting container")
        self.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    def cleanup(self):
        if not self.container_id and not self.path:
            return
        self.kill()
        self.clear_execution_folder()
        self.container_id = None
        self.path = None

    def get_path(self):
        return os.path.abspath(os.path.join("executions", self.session_id))

    def clear_execution_folder(self):
        if self.path:
            shutil.rmtree(self.path, ignore_errors=True)

    def create_execution_folder(self, template_path):
        os.makedirs(self.path, exist_ok=True)

        if not template_path:
            template_path = None
        else:
            template_path = os.path.abspath(template_path)

        if template_path and os.path.isdir(template_path):
            for item in os.listdir(template_path):
                if item in self._template_ignored_parts:
                    continue
                s = os.path.join(template_path, item)
                d = os.path.join(self.path, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

        if self.language == "python":
            with open(os.path.join(self.path, 'script.py'), 'w') as file:
                file.write(self.code)

        if self.language == "cpp":
            with open(os.path.join(self.path, 'script.cpp'), 'w') as file:
                file.write(self.code)

    def check(self):
        if self.__class__._docker_checked:
            return
        try:
            subprocess.run(["docker", "info"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.__class__._docker_checked = True
        except subprocess.CalledProcessError:
            raise ExecutionException("Error connecting to Docker.")

    def prepare(self):
        try:
            container_image = "python:3.11" if self.language == "python" else "gcc:latest"
            run_command = ["docker", "run", "-d", "--pull", "missing"]
            if self.language == "python":
                run_command.extend(["-v", f"{self._pip_cache_volume}:/root/.cache/pip"])
            else:
                run_command.extend([
                    "--network", "none",
                    "--memory", "512m",
                    "--cpus", "1.0",
                    "--pids-limit", "128",
                    "--ulimit", "fsize=67108864:67108864",
                    "--ulimit", "nofile=256:256",
                    "--read-only",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                ])
            if self._docker_transfer_mode == "bind":
                volume_binding = f"{self.path}:/code"
                run_command.extend(["-v", volume_binding])
            elif self.language == "cpp":
                run_command.extend([
                    "--tmpfs", "/code:rw,exec,nosuid,nodev,size=128m",
                ])
            run_command.extend([container_image, "sleep", "infinity"])

            container_id = subprocess.run(
                run_command,
                check=True,
                stdout=subprocess.PIPE
            ).stdout.decode().strip()

            if self._docker_transfer_mode == "cp":
                subprocess.run(
                    ["docker", "exec", container_id, "mkdir", "-p", "/code"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                if self.language == "cpp":
                    self._stream_path_into_container(
                        container_id,
                        self.path,
                        "/code",
                    )
                else:
                    subprocess.run(
                        ["docker", "cp", f"{self.path}/.", f"{container_id}:/code"],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
            elif self._docker_transfer_mode != "bind":
                raise ExecutionException(f"Unsupported DOCKER_TRANSFER_MODE: {self._docker_transfer_mode}")

        except Exception:
            raise ExecutionException("Error creating container.")

        return container_id

    def _stream_path_into_container(
        self,
        container_id,
        local_path,
        container_path,
    ):
        """Copy trusted files into a writable mount of a read-only container.

        Docker refuses ``docker cp`` whenever the container root filesystem is
        marked read-only, even when the destination itself is a writable tmpfs.
        Stream a locally-created archive through ``docker exec`` instead; tar
        writes directly into the mounted ``/code`` filesystem.
        """
        local_path = os.path.abspath(local_path)
        if not os.path.exists(local_path):
            raise ExecutionException("C++ sandbox source path does not exist.")
        if not container_path.startswith("/"):
            raise ExecutionException("C++ sandbox destination must be absolute.")

        if os.path.isdir(local_path):
            destination = container_path.rstrip("/") or "/"
            entries = [
                (os.path.join(local_path, name), name)
                for name in sorted(os.listdir(local_path))
            ]
        else:
            destination, archive_name = container_path.rsplit("/", 1)
            destination = destination or "/"
            if not archive_name:
                raise ExecutionException("C++ sandbox destination file is missing.")
            entries = [(local_path, archive_name)]

        try:
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
                with tarfile.open(fileobj=stream, mode="w") as archive:
                    for source, archive_name in entries:
                        archive.add(source, arcname=archive_name, recursive=True)
                stream.seek(0)
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        container_id,
                        "tar",
                        "-xpf",
                        "-",
                        "-C",
                        destination,
                    ],
                    stdin=stream,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self._harness_docker_timeout,
                )
        except (OSError, tarfile.TarError, subprocess.SubprocessError) as error:
            raise ExecutionException(
                "Error transferring files into the C++ sandbox."
            ) from error

    def setup(self):
        try:

            if self.language == "python" and os.path.exists(os.path.join(self.path, 'requirements.txt')):
                subprocess.run(
                    [
                        "docker", "exec", self.container_id, "pip", "install",
                        "--disable-pip-version-check", "--prefer-binary",
                        "-r", "/code/requirements.txt"
                    ],
                    check=True
                )

            if self.language == "cpp":
                self._compile_cpp_harness("/code/script.cpp", "/code/program")
        except (SolutionException, ExecutionException):
            raise
        except Exception as e:
            print(e)
            raise ExecutionException("Error setting up execution.")

    def kill(self):
        if self.container_id:
            subprocess.run(["docker", "kill", self.container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rm", self.container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(
        self,
        input_data,
        time_limit=1,
        capture_limit=EXECUTION_CAPTURE_LIMIT,
    ):
        if getattr(self, "_unusable", False):
            raise SolutionException("Execution container stopped after a timeout.")
        if self.language == "python":
            exec_command = "cd /code && python3 script.py"
        else:
            exec_command = "cd /code && ./program"

        return self._run_command(
            exec_command,
            input_data,
            time_limit,
            capture_limit=capture_limit,
        )

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
        compile_options=None,
    ):
        if getattr(self, "_unusable", False):
            raise SolutionException("Execution container stopped after a timeout.")
        if self.language == "cpp":
            if probe_source is not None:
                raise ExecutionException(
                    "Isolated probes are supported only for Python tasks."
                )
            return self._run_cpp_source(
                source_code,
                input_data,
                time_limit,
                compile_options,
            )

        if self.language != "python":
            raise ExecutionException("Test harnesses are supported only for Python tasks.")

        command_input = input_data
        if probe_source is not None:
            source_code = build_isolated_probe_controller(
                source_code,
                probe_source,
                input_data,
            )
            command_input = ""

        filename = f"__geekpaste_test_{uuid.uuid4().hex}.py"
        local_path = os.path.join(self.path, filename)
        container_path = f"/code/{filename}"

        try:
            with open(local_path, "w", encoding="utf-8") as file:
                file.write(source_code)

            if self._docker_transfer_mode == "cp":
                try:
                    subprocess.run(
                        [
                            "docker",
                            "cp",
                            local_path,
                            f"{self.container_id}:{container_path}",
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=self._harness_docker_timeout,
                    )
                except (OSError, subprocess.SubprocessError) as error:
                    raise ExecutionException(
                        "Error transferring the isolated test harness."
                    ) from error

            command = f"cd /code && python3 {filename}"
            if probe_source is None:
                return self._run_command(command, command_input, time_limit)
            return self._run_command(
                command,
                command_input,
                time_limit,
                system_on_nonzero=True,
                capture_limit=ISOLATED_CONTROLLER_CAPTURE_LIMIT,
            )
        finally:
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass

            if self._docker_transfer_mode == "cp" and self.container_id:
                try:
                    subprocess.run(
                        ["docker", "exec", self.container_id, "rm", "-f", container_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=self._harness_docker_timeout,
                    )
                except (OSError, subprocess.SubprocessError):
                    # The execution container itself is removed immediately after
                    # checking, so a failed best-effort file cleanup is harmless.
                    pass

    def _run_cpp_source(
        self,
        source_code,
        input_data,
        time_limit,
        compile_options=None,
    ):
        identifier = uuid.uuid4().hex
        source_filename = f"__geekpaste_test_{identifier}.cpp"
        binary_filename = f"__geekpaste_test_{identifier}"
        local_source_path = os.path.join(self.path, source_filename)
        local_binary_path = os.path.join(self.path, binary_filename)
        container_source_path = f"/code/{source_filename}"
        container_binary_path = f"/code/{binary_filename}"

        try:
            try:
                with open(local_source_path, "w", encoding="utf-8") as file:
                    file.write(source_code)
            except (OSError, TypeError) as error:
                raise ExecutionException(
                    "Error creating the C++ test harness."
                ) from error

            if self._docker_transfer_mode == "cp":
                self._stream_path_into_container(
                    self.container_id,
                    local_source_path,
                    container_source_path,
                )
            elif self._docker_transfer_mode != "bind":
                raise ExecutionException(
                    f"Unsupported DOCKER_TRANSFER_MODE: {self._docker_transfer_mode}"
                )

            self._compile_cpp_harness(
                container_source_path,
                container_binary_path,
                compile_options,
            )
            return self._run_command(
                f"cd /code && ./{binary_filename}",
                input_data,
                time_limit,
            )
        finally:
            for local_path in (local_source_path, local_binary_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass

            if self._docker_transfer_mode == "cp" and self.container_id:
                try:
                    subprocess.run(
                        [
                            "docker",
                            "exec",
                            self.container_id,
                            "rm",
                            "-f",
                            container_source_path,
                            container_binary_path,
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=self._harness_docker_timeout,
                    )
                except (OSError, subprocess.SubprocessError):
                    # Container teardown after the task is the final cleanup fallback.
                    pass

    def _compile_cpp_harness(
        self,
        source_path,
        binary_path,
        compile_options=None,
    ):
        options = tuple(compile_options or ())
        if any(option not in ALLOWED_CPP_HARNESS_OPTIONS for option in options):
            raise ExecutionException("Unsupported C++ harness compiler option.")
        command = [
            "docker",
            "exec",
            self.container_id,
            "g++",
            "-std=c++17",
            *options,
            source_path,
            "-o",
            binary_path,
        ]
        try:
            return_code, stdout, stderr, overflow = _run_process_bounded(
                command,
                b"",
                self._harness_compile_timeout,
                EXECUTION_CAPTURE_LIMIT,
            )
        except subprocess.TimeoutExpired:
            self._stop_after_timeout()
            raise SolutionException(
                "Compilation timed out after "
                f"{self._harness_compile_timeout} seconds."
            ) from None
        except OSError as error:
            raise ExecutionException(
                "Error starting the C++ test harness compiler."
            ) from error

        if overflow:
            self._stop_after_timeout()
            raise SolutionException(
                f"Compilation output limit exceeded ({EXECUTION_CAPTURE_LIMIT} bytes)."
            )

        error_text = stderr.decode(errors="replace").strip()
        if return_code in (125, 126, 127):
            details = f": {error_text}" if error_text else ""
            raise ExecutionException(
                f"Error running the C++ test harness compiler{details}"
            )
        if return_code != 0:
            details = error_text or stdout.decode(errors="replace").strip()
            raise SolutionException(
                f"Compilation failed: {details or 'unknown compiler error'}"
            )

    def _stop_after_timeout(self):
        self._unusable = True
        if not self.container_id:
            return
        try:
            subprocess.run(
                ["docker", "kill", self.container_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=getattr(self, "_harness_docker_timeout", 10),
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _run_command(
        self,
        exec_command,
        input_data,
        time_limit,
        system_on_nonzero=False,
        capture_limit=EXECUTION_CAPTURE_LIMIT,
    ):
        try:
            command = [
                "docker",
                "exec",
                "-i",
                self.container_id,
                "bash",
                "-c",
                exec_command,
            ]
            return_code, stdout, stderr, overflow = _run_process_bounded(
                command,
                input_data.encode(),
                time_limit,
                capture_limit,
            )
            if overflow:
                self._stop_after_timeout()
                raise SolutionException(
                    f"Output limit exceeded ({capture_limit} bytes)."
                )
            if return_code != 0:
                exception_type = (
                    ExecutionException
                    if system_on_nonzero
                    else SolutionException
                )
                raise exception_type(
                    f"Runtime error: {stderr.decode(errors='replace')}"
                )
            return stdout.decode(errors="replace")

        except subprocess.TimeoutExpired:
            self._stop_after_timeout()
            raise SolutionException(
                f"Test failed: Execution timed out after {time_limit} seconds."
            ) from None
        except OSError as error:
            raise ExecutionException(
                "Error starting the execution process."
            ) from error


class TestRunner:
    def __init__(self, container):
        self.container = container

    def __call__(
        self,
        input_data,
        time_limit=1,
        capture_limit=EXECUTION_CAPTURE_LIMIT,
    ):
        return self.container.run(input_data, time_limit, capture_limit)

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
        compile_options=None,
    ):
        return self.container.run_source(
            source_code,
            input_data,
            time_limit,
            probe_source,
            compile_options,
        )


class BrainfuckExecutor:
    """Pure-Python Brainfuck interpreter. No Docker needed."""

    def __init__(self, code):
        self.code = code

    def run(self, input_data='', time_limit=5):
        import signal

        tape = [0] * 30000
        dp = 0  # data pointer
        ip = 0  # instruction pointer
        output = []
        inp = iter(input_data.encode())

        # Precompute bracket matching
        brackets = {}
        stack = []
        for i, c in enumerate(self.code):
            if c == '[':
                stack.append(i)
            elif c == ']':
                if not stack:
                    raise SolutionException('Unmatched ]')
                j = stack.pop()
                brackets[j] = i
                brackets[i] = j
        if stack:
            raise SolutionException('Unmatched [')

        def _timeout(signum, frame):
            raise SolutionException(f'Execution timed out after {time_limit} seconds.')

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(time_limit)
        try:
            while ip < len(self.code):
                c = self.code[ip]
                if c == '+':
                    tape[dp] = (tape[dp] + 1) % 256
                elif c == '-':
                    tape[dp] = (tape[dp] - 1) % 256
                elif c == '>':
                    dp += 1
                    if dp >= len(tape):
                        raise SolutionException('Tape overflow')
                elif c == '<':
                    dp -= 1
                    if dp < 0:
                        raise SolutionException('Tape underflow')
                elif c == '.':
                    output.append(chr(tape[dp]))
                elif c == ',':
                    tape[dp] = next(inp, 0)
                elif c == '[':
                    if tape[dp] == 0:
                        ip = brackets[ip]
                elif c == ']':
                    if tape[dp] != 0:
                        ip = brackets[ip]
                ip += 1
        finally:
            signal.alarm(0)

        return ''.join(output)


class TestExecutor:
    def __init__(self, code):
        self.original_path = os.getcwd()
        self.code = code
        self.task = code.task
        self.container = ExecutionContainer(code.lang, f"environments/task_{code.task_id}", code.code)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    def cleanup(self):
        if not self.container:
            return
        os.chdir(self.original_path)
        self.container.cleanup()
        mod_name = f"environments.task_{self.code.task_id}.tester"
        sys.modules.pop(mod_name, None)
        self.container = None

    def __del__(self):
        self.cleanup()

    def perform(self):
        mod_name = f"environments.task_{self.code.task_id}.tester"
        try:
            tester_module = importlib.import_module(mod_name)
            importlib.reload(tester_module)  # force fresh load
            perform_tests = getattr(tester_module, 'perform_tests')
        except Exception as e:
            raise ExecutionException(f"Error importing tester module: {e}.")

        try:
            os.chdir(self.container.path)
            result = perform_tests(TestRunner(self.container), self.code.code)
            os.chdir(self.original_path)
            return result
        except SolutionException as e:
            os.chdir(self.original_path)
            raise e
        except Exception as e:
            os.chdir(self.original_path)
            raise ExecutionException(f"Error running tester: {e}.")
