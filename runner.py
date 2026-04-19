import subprocess
import os
import uuid
import shutil
import importlib


class ExecutionException(Exception):
    pass


class SolutionException(Exception):
    pass


class ExecutionContainer:
    def __init__(self, language, template_path, code):
        try:
            self.container_id = None
            self.path = None
            self.language = language
            self.code = code
            self.session_id = str(uuid.uuid4())

            self.check()

            self.path = self.get_path()
            self.create_execution_folder(template_path)
            self.container_id = self.prepare()
            self.setup()
        except SolutionException as e:
            print(e)
            raise e
        except ExecutionException as e:
            print(e)
            raise e
        except Exception as e:
            print(e)
            raise ExecutionException(e)

    def __del__(self):
        print("deleting container")
        self.kill()
        self.clear_execution_folder()

    def get_path(self):
        return os.path.abspath(os.path.join("executions", self.session_id))

    def clear_execution_folder(self):
        if self.path:
            shutil.rmtree(self.path)

    def create_execution_folder(self, template_path):
        os.makedirs(self.path, exist_ok=True)

        if not template_path:
            template_path = None
        else:
            template_path = os.path.abspath(template_path)

        if template_path and os.path.isdir(template_path):
            for item in os.listdir(template_path):
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
        try:
            subprocess.run(["docker", "info"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            raise ExecutionException("Error connecting to Docker.")

    def prepare(self):
        try:
            container_image = "python:3.11" if self.language == "python" else "gcc:latest"
            subprocess.run(["docker", "pull", container_image], check=True)

            volume_binding = f"{self.path}:/code"
            container_id = subprocess.run(
                ["docker", "run", "-d", "-v", volume_binding, container_image, "sleep", "infinity"],
                check=True,
                stdout=subprocess.PIPE
            ).stdout.decode().strip()

        except Exception as e:
            raise ExecutionException("Error creating container.")

        return container_id

    def setup(self):
        try:

            if self.language == "python" and os.path.exists(os.path.join(self.path, 'requirements.txt')):
                subprocess.run(
                    ["docker", "exec", self.container_id, "pip", "install", "-r", "/code/requirements.txt"],
                    check=True
                )

            if self.language == "cpp":
                compile_command = f"g++ /code/script.cpp -o /code/program"
                compile_result = subprocess.run(
                    ["docker", "exec", self.container_id, "bash", "-c", compile_command],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                if compile_result.returncode != 0:
                    raise SolutionException(f"Compilation failed: {compile_result.stderr.decode()}")
        except Exception as e:
            print(e)
            raise ExecutionException("Error setting up execution.")

    def kill(self):
        if self.container_id:
            subprocess.run(["docker", "kill", self.container_id])
            subprocess.run(["docker", "rm", self.container_id])

    def run(self, input_data, time_limit=1):
        if self.language == "python":
            exec_command = f"cd /code && python3 script.py"
        else:
            exec_command = f"cd /code && ./program"

        try:
            exec_result = subprocess.run(
                ["docker", "exec", "-i", self.container_id, "bash", "-c", exec_command],
                input=input_data.encode(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=time_limit
            )
            if exec_result.returncode != 0:
                raise SolutionException(f"Runtime error: {exec_result.stderr.decode()}")
            return exec_result.stdout.decode()

        except subprocess.TimeoutExpired:
            raise SolutionException(f"Test failed: Execution timed out after {time_limit} seconds.")
        except subprocess.CalledProcessError as e:
            raise SolutionException(f"Error occurred: {e}")


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

    def __del__(self):
        os.chdir(self.original_path)
        del self.container

    def perform(self):
        try:
            tester_module = importlib.import_module(f"environments.task_{self.code.task_id}.tester")
            perform_tests = getattr(tester_module, 'perform_tests')
        except Exception as e:
            raise ExecutionException(f"Error importing tester module: {e}.")

        try:
            os.chdir(self.container.path)
            result = perform_tests(self.container.run, self.code.code)
            os.chdir(self.original_path)
            return result
        except SolutionException as e:
            os.chdir(self.original_path)
            raise e
        except Exception as e:
            os.chdir(self.original_path)
            raise ExecutionException(f"Error running tester: {e}.")
