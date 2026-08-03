import re

from environments.grade8_2026_common import (
    exact_text_equal,
    finish_criteria,
    run_case_group,
    run_cpp_harness_case,
    source_has_all,
    source_has_none,
    tokens_equal,
)


def _cpp_case(
    runner,
    source_code,
    task_id,
    label,
    harness,
    expected,
    input_data="",
    time_limit=3,
    comparator=tokens_equal,
):
    harness = f"\n// GP_TASK_{task_id}_{label}\n{harness}"
    case = {
        "harness": harness,
        "input": input_data,
        "expected": expected,
        "time_limit": time_limit,
        "comparator": comparator,
    }
    if "__gp_allocation_node" in harness:
        case["compile_options"] = (
            "-O1",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
        )
    return run_cpp_harness_case(
        runner,
        source_code,
        case,
        comparator,
    )


def _stdin_cases(runner, cases):
    return run_case_group(runner, cases, exact_text_equal)


def _mask_cpp(source_code):
    pattern = re.compile(
        r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'",
        re.S,
    )

    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    return pattern.sub(blank, source_code or "")


def _balanced_body(masked_source, opening_brace):
    if opening_brace < 0:
        return None
    depth = 0
    for index in range(opening_brace, len(masked_source)):
        symbol = masked_source[index]
        if symbol == "{":
            depth += 1
        elif symbol == "}":
            depth -= 1
            if depth == 0:
                return masked_source[opening_brace + 1 : index]
    return None


def _class_body(source_code, class_name):
    masked = _mask_cpp(source_code)
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\b[^;{{]*{{", masked)
    if not match:
        return None
    return _balanced_body(masked, masked.find("{", match.start()))


def _function_body(source_code, function_name):
    masked = _mask_cpp(source_code)
    pattern = re.compile(
        rf"\b(?:[A-Za-z_]\w*\s*::\s*)?{re.escape(function_name)}\s*"
        r"\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{"
    )
    match = pattern.search(masked)
    if not match:
        return None
    return _balanced_body(masked, masked.find("{", match.start()))


def _brace_depths(masked_source):
    result = []
    depth = 0
    for symbol in masked_source:
        result.append(depth)
        if symbol == "{":
            depth += 1
        elif symbol == "}":
            depth = max(0, depth - 1)
    return result


def _has_global_counters_and_wrappers(source_code):
    masked = _mask_cpp(source_code)
    depths = _brace_depths(masked)
    declaration_pattern = re.compile(
        r"\b(?:static\s+)?(?:unsigned\s+)?(?:int|long\s+long|size_t|std\s*::\s*size_t)"
        r"\s+([^;{}]+);"
    )
    counter_names = []
    for match in declaration_pattern.finditer(masked):
        if depths[match.start()] != 0 or "(" in match.group(1):
            continue
        for declarator in match.group(1).split(","):
            name = re.search(
                r"\b([A-Za-z_]\w*)\s*(?:=\s*0|\{\s*0?\s*\})?\s*$",
                declarator,
            )
            if name:
                counter_names.append(name.group(1))

    if len(set(counter_names)) < 2:
        return False

    allocation_wrappers = []
    release_wrappers = []
    wrapper_regions = []
    function_pattern = re.compile(
        r"\b(?:[A-Za-z_]\w*(?:\s*[*&])?\s+)+(?P<name>[A-Za-z_]\w*)\s*"
        r"\([^;{}]*\)\s*\{"
    )
    for match in function_pattern.finditer(masked):
        if depths[match.start()] != 0:
            continue
        opening = masked.find("{", match.start())
        body = _balanced_body(masked, opening) or ""
        closing = opening + len(body) + 1
        mutates_counter = any(
            re.search(
                rf"(?:\+\+\s*{re.escape(counter)}\b|\b{re.escape(counter)}\s*\+\+|"
                rf"\b{re.escape(counter)}\s*\+=\s*1\b|"
                rf"\b{re.escape(counter)}\s*=\s*{re.escape(counter)}\s*\+\s*1\b)",
                body,
            )
            for counter in counter_names
        )
        if not mutates_counter:
            continue
        name = match.group("name")
        if re.search(r"\bnew\b", body) and not re.search(r"\bdelete\b", body):
            allocation_wrappers.append(name)
            wrapper_regions.append((match.start(), closing + 1))
        if re.search(r"\bdelete\b", body) and not re.search(r"\bnew\b", body):
            release_wrappers.append(name)
            wrapper_regions.append((match.start(), closing + 1))

    if not allocation_wrappers or not release_wrappers:
        return False

    outside_wrappers = list(masked)
    for start, end in wrapper_regions:
        outside_wrappers[start:end] = " " * (end - start)
    outside_wrappers = "".join(outside_wrappers)

    # The wrappers must be the only place where heap blocks are acquired and
    # released, and both wrappers must actually be called by the solution.
    if re.search(r"\b(?:new|delete)\b", outside_wrappers):
        return False
    return any(
        re.search(rf"\b{re.escape(name)}\s*\(", outside_wrappers)
        for name in allocation_wrappers
    ) and any(
        re.search(rf"\b{re.escape(name)}\s*\(", outside_wrappers)
        for name in release_wrappers
    )


def _access_section(class_body, requested_access):
    depths = _brace_depths(class_body)
    access_pattern = re.compile(r"\b(public|protected|private)\s*:")
    current_access = "private"
    start = 0
    parts = []
    for match in access_pattern.finditer(class_body):
        if depths[match.start()] != 0:
            continue
        if current_access == requested_access:
            parts.append(class_body[start : match.start()])
        current_access = match.group(1)
        start = match.end()
    if current_access == requested_access:
        parts.append(class_body[start:])
    return "\n".join(parts)


def _account_private_storage_policy(source_code):
    body = _class_body(source_code, "Account")
    if body is None:
        return False
    private = _access_section(body, "private")
    depths = _brace_depths(private)

    integer_fields = 0
    for declaration in re.finditer(r"\bint\b\s*([^;{}]+);", private):
        if depths[declaration.start()] != 0 or "(" in declaration.group(1):
            continue
        for declarator in declaration.group(1).split(","):
            if "*" not in declarator and re.search(r"\b[A-Za-z_]\w*", declarator):
                integer_fields += 1

    owner_field = any(
        depths[declaration.start()] == 0
        and re.search(r"\b[A-Za-z_]\w*\s*\[\s*21\s*\]", declaration.group(1))
        for declaration in re.finditer(r"\bchar\b\s*([^;{}]+);", private)
    )
    return integer_fields >= 3 and owner_field


def _private_section(class_body):
    private_match = re.search(r"\bprivate\s*:", class_body)
    if private_match:
        start = private_match.end()
    else:
        start = 0
    next_access = re.search(r"\b(?:public|protected|private)\s*:", class_body[start:])
    end = start + next_access.start() if next_access else len(class_body)
    return class_body[start:end]


def _basic_vector_policy(source_code):
    body = _class_body(source_code, "Vector")
    if body is None:
        return False
    private = _private_section(body)
    pointer_fields = 0
    scalar_fields = 0
    for declaration in re.finditer(r"\bint\b\s*([^;]+);", private):
        if "(" in declaration.group(1):
            continue
        for declarator in declaration.group(1).split(","):
            if not re.search(r"\b[A-Za-z_]\w*", declarator):
                continue
            if "*" in declarator:
                pointer_fields += 1
            else:
                scalar_fields += 1
    return (
        pointer_fields == 1
        and scalar_fields == 1
        and source_has_all(
            source_code,
            [
                r"\bnew\s+int\s*\[",
                r"~\s*Vector\s*\(",
                r"\bpush_back\s*\(",
                r"\bget_size\s*\(",
            ],
        )
        and source_has_none(
            source_code,
            [r"\b(?:std\s*::\s*)?(?:vector|array|deque|list)\s*<"],
        )
    )


def _template_vector_operator_policy(source_code):
    masked = _mask_cpp(source_code)
    return (
        bool(
            re.search(
                r"\btemplate\s*<[^>]+>\s*class\s+Vector\b", masked, re.S
            )
        )
        and bool(
            re.search(
                r"\b(?:T|auto)\s*&\s*operator\s*\[\s*\]", masked
            )
        )
        and bool(
            re.search(
                r"\b(?:friend\s+)?(?:std\s*::\s*)?ostream\s*&\s*"
                r"operator\s*<<\s*\(",
                masked,
            )
        )
        and not re.search(
            r"\b(?:std\s*::\s*)?(?:vector|array|deque|list)\s*<", masked
        )
    )


def _string_storage_policy(source_code):
    body = _class_body(source_code, "String")
    length_body = _function_body(source_code, "length")
    if body is None or length_body is None:
        return False
    private = _private_section(body)
    has_buffer = bool(re.search(r"\bchar\s*\*\s*[A-Za-z_]\w*", private))
    has_length = bool(
        re.search(
            r"\b(?:int|size_t|std\s*::\s*size_t)\s+[A-Za-z_]\w*\s*"
            r"(?:=\s*[^;]+|\{[^;]*\})?\s*;",
            private,
        )
    )
    constant_length = not re.search(
        r"\b(?:strlen|for|while)\b", length_body
    )
    return (
        has_buffer
        and has_length
        and constant_length
        and not re.search(r"\b(?:std\s*::\s*)?(?:basic_string|string)\b", body)
    )


def _string_rule_of_three_policy(source_code):
    masked = _mask_cpp(source_code)
    return all(
        re.search(pattern, masked, re.S)
        for pattern in (
            r"~\s*String\s*\(",
            r"\bString\s*\(\s*(?:const\s+String|String\s+const)\s*&",
            r"\boperator\s*=\s*\(\s*(?:const\s+String|String\s+const)\s*&",
            r"\bdelete\s*\[\s*\]",
            r"\b(?:friend\s+)?(?:std\s*::\s*)?ostream\s*&\s*"
            r"operator\s*<<\s*\(",
        )
    )


def _uses_own_stack(source_code):
    masked = _mask_cpp(source_code)
    if not re.search(
        r"\btemplate\s*<[^>]+>\s*(?:class|struct)\s+Stack\b",
        masked,
        re.S,
    ) or re.search(r"\bstd\s*::\s*stack\s*<", masked):
        return False

    main_body = _function_body(source_code, "main")
    if main_body is None:
        return False
    declarations = re.findall(
        r"\bStack\s*<[^;{}]+?>\s+([A-Za-z_]\w*)\s*(?:[;{(=])",
        main_body,
    )
    return any(
        all(
            re.search(rf"\b{re.escape(name)}\s*\.\s*{method}\s*\(", main_body)
            for method in ("push", "pop", "empty")
        )
        for name in declarations
    )


_ALLOCATION_TRACKER = r"""
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

struct __gp_allocation_node {
    void* pointer;
    bool tracked;
    __gp_allocation_node* next;
};

struct alignas(std::max_align_t) __gp_allocation_header {
    std::uint64_t magic;
    std::size_t size;
    bool array;
};

static constexpr std::uint64_t __gp_header_magic = 0x4750414c4c4f4341ULL;
static constexpr std::uint64_t __gp_trailer_magic = 0x4750545241494c52ULL;

static bool __gp_tracking = false;
static long long __gp_live_allocations = 0;
static long long __gp_memory_errors = 0;
static __gp_allocation_node* __gp_allocations = nullptr;

static void __gp_record_allocation(void* pointer) {
    if (pointer == nullptr) return;
    auto* node = static_cast<__gp_allocation_node*>(
        std::malloc(sizeof(__gp_allocation_node))
    );
    if (node == nullptr) std::abort();
    node->pointer = pointer;
    node->tracked = __gp_tracking;
    node->next = __gp_allocations;
    __gp_allocations = node;
    if (node->tracked) ++__gp_live_allocations;
}

static bool __gp_record_release(void* pointer) {
    if (pointer == nullptr) return true;
    __gp_allocation_node** link = &__gp_allocations;
    while (*link != nullptr) {
        if ((*link)->pointer == pointer) {
            __gp_allocation_node* found = *link;
            *link = found->next;
            if (found->tracked) --__gp_live_allocations;
            std::free(found);
            return true;
        }
        link = &((*link)->next);
    }
    if (__gp_tracking) ++__gp_memory_errors;
    return false;
}

static void* __gp_allocate(std::size_t size, bool array) {
    if (size == 0) size = 1;
    constexpr std::size_t overhead =
        sizeof(__gp_allocation_header) + sizeof(__gp_trailer_magic);
    if (size > std::numeric_limits<std::size_t>::max() - overhead)
        throw std::bad_alloc();
    auto* raw = static_cast<unsigned char*>(std::malloc(overhead + size));
    if (raw == nullptr) throw std::bad_alloc();
    auto* header = reinterpret_cast<__gp_allocation_header*>(raw);
    header->magic = __gp_header_magic;
    header->size = size;
    header->array = array;
    void* pointer = raw + sizeof(__gp_allocation_header);
    std::memcpy(
        static_cast<unsigned char*>(pointer) + size,
        &__gp_trailer_magic,
        sizeof(__gp_trailer_magic)
    );
    __gp_record_allocation(pointer);
    return pointer;
}

static void __gp_release(void* pointer, bool array) noexcept {
    if (pointer == nullptr) return;
    if (!__gp_record_release(pointer)) return;
    auto* raw = static_cast<unsigned char*>(pointer)
        - sizeof(__gp_allocation_header);
    auto* header = reinterpret_cast<__gp_allocation_header*>(raw);
    std::uint64_t trailer = 0;
    if (header->magic != __gp_header_magic) {
        ++__gp_memory_errors;
    } else {
        std::memcpy(
            &trailer,
            static_cast<unsigned char*>(pointer) + header->size,
            sizeof(trailer)
        );
        if (trailer != __gp_trailer_magic || header->array != array)
            ++__gp_memory_errors;
        header->magic = 0;
    }
    std::free(raw);
}

void* operator new(std::size_t size) {
    return __gp_allocate(size, false);
}

void* operator new[](std::size_t size) {
    return __gp_allocate(size, true);
}

void operator delete(void* pointer) noexcept {
    __gp_release(pointer, false);
}

void operator delete[](void* pointer) noexcept {
    __gp_release(pointer, true);
}

void operator delete(void* pointer, std::size_t) noexcept {
    __gp_release(pointer, false);
}

void operator delete[](void* pointer, std::size_t) noexcept {
    __gp_release(pointer, true);
}

static void __gp_begin_tracking() {
    __gp_live_allocations = 0;
    __gp_memory_errors = 0;
    __gp_tracking = true;
}

static long long __gp_stop_tracking() {
    __gp_tracking = false;
    return __gp_memory_errors == 0
        ? __gp_live_allocations
        : -1 - __gp_memory_errors;
}
"""


def _task_2665(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2665,
        "pet_methods",
        r"""
#include <iostream>
int main() {
    Pet first;
    first.hunger = 95;
    first.energy = 10;
    first.feed();
    first.play();
    first.status();
    first.play();
    first.status();

    Pet second;
    second.hunger = 0;
    second.energy = 100;
    second.play();
    second.status();
    first.status();
}
""",
        "hunger=90 energy=0\nhunger=80 energy=0\n"
        "hunger=0 energy=80\nhunger=80 energy=0\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {
                "input": "",
                "expected": "hunger=50 energy=50\nhunger=70 energy=30\n"
                "hunger=100 energy=10\n",
            }
        ],
    )
    return finish_criteria(
        2665,
        5,
        [(hidden and program, "методы Pet, границы 0/100 и независимые объекты")],
    )


def _task_2666(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2666,
        "sludge_truck",
        r"""
#include <iostream>
int main() {
    SludgeTruck first;
    first.capacity = 10;
    first.speed = 3;
    first.current = 9;
    std::cout << first.pump() << " " << first.current << " ";
    std::cout << first.pump() << " " << first.current << " ";
    first.clear();
    std::cout << first.current << "\n";

    SludgeTruck second;
    second.capacity = 5;
    second.speed = 20;
    second.current = 0;
    std::cout << second.pump() << " " << second.current << " ";
    std::cout << second.pump() << "\n";
}
""",
        "1 10 0 10 0\n1 5 0\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {
                "input": "",
                "expected": "Pumped, tank: 3\nPumped, tank: 6\n"
                "Pumped, tank: 9\nPumped, tank: 10\n"
                "Full, going home\nTank: 0\n",
            }
        ],
    )
    return finish_criteria(
        2666,
        5,
        [(hidden and program, "pump заполняет только до capacity и clear обнуляет бак")],
    )


def _task_2667(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2667,
        "pet_constructors",
        r"""
#include <iostream>
int main() {
    Pet defaults[2];
    Pet custom(95, 7);
    defaults[0].status();
    defaults[1].feed();
    defaults[1].feed();
    defaults[1].status();
    custom.status();
    custom.feed();
    custom.status();
}
""",
        "hunger=50 energy=50\nhunger=100 energy=50\n"
        "hunger=95 energy=7\nhunger=100 energy=7\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {
                "input": "",
                "expected": "hunger=50 energy=50\nhunger=80 energy=50\n"
                "hunger=80 energy=40\n",
            }
        ],
    )
    return finish_criteria(
        2667,
        5,
        [(hidden and program, "оба конструктора Pet и корректная инициализация массива")],
    )


def _task_2670(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2670,
        "coffee_machine",
        r"""
#include <iostream>
int main() {
    CoffeeMachine machine;
    std::cout << machine.HasCoffee() << machine.HasWater()
              << machine.HasMilk() << "\n";
    machine.AddCoffee();
    std::cout << machine.MakeCup() << " " << machine.HasCoffee() << "\n";
    machine.AddWater();
    machine.AddMilk();
    int first = 0;
    while (machine.MakeCup()) ++first;
    std::cout << first << " " << machine.HasCoffee() << " "
              << machine.HasWater() << " " << machine.HasMilk() << "\n";
    machine.AddCoffee();
    int second = 0;
    while (machine.MakeCup()) ++second;
    std::cout << second << " " << machine.HasCoffee() << " "
              << machine.HasWater() << " " << machine.HasMilk() << "\n";
}
""",
        "000\n0 1\n12 0 1 1\n3 1 1 0\n",
        comparator=exact_text_equal,
    )
    program_output = (
        "Add coffee - OK\nAdd water - OK\nAdd milk - OK\n"
        + "Cup is ready...\n" * 12
        + "Done!"
    )
    program = _stdin_cases(runner, [{"input": "", "expected": program_output}])
    return finish_criteria(
        2670,
        5,
        [(hidden and program, "ресурсы добавляются точно и MakeCup атомарен")],
    )


def _task_2676(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2676,
        "divide_function",
        r"""
#include <exception>
#include <iostream>
#include <string>
int main() {
    std::cout << divide(10, 3) << " " << divide(-7, 2)
              << " " << divide(7, -2) << " ";
    bool exact = false;
    try {
        (void)divide(1, 0);
    } catch (const char* message) {
        exact = std::string(message) == "division by zero";
    } catch (const std::string& message) {
        exact = message == "division by zero";
    } catch (const std::exception& error) {
        exact = std::string(error.what()) == "division by zero";
    } catch (...) {
    }
    std::cout << exact << "\n";
}
""",
        "3 -3 -3 1\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {
                "input": "10 2\n7 0\n9 4\n",
                "expected": "5\nALARM: division by zero\n2\n",
            },
            {
                "input": "-9 2\n1 0\n8 -3\n0 5\n",
                "expected": "-4\nALARM: division by zero\n-2\n0\n",
            },
        ],
    )
    exception_shape = source_has_all(
        source_code, [r"\bthrow\b", r"\btry\b", r"\bcatch\s*\("]
    )
    return finish_criteria(
        2676,
        5,
        [
            (
                hidden and program and exception_shape,
                "divide выбрасывает точную ошибку, а цикл продолжает работу",
            )
        ],
    )


def _task_2677(runner, source_code):
    state_hidden = _cpp_case(
        runner,
        source_code,
        2677,
        "train_states",
        r"""
#include <iostream>
int main() {
    Train train;
    train.status();
    train.faster();
    train.faster();
    train.status();
    train.faster();
    train.faster();
    train.status();
    train.slower();
    train.slower();
    train.slower();
    train.slower();
    train.open_doors();
    train.open_doors();
    train.status();
    train.close_doors();
    train.close_doors();
    train.status();
}
""",
        "speed=0 doors=closed\nspeed=30 doors=closed\n"
        "speed=90 doors=closed\nspeed=0 doors=open\n"
        "speed=0 doors=closed\n",
        comparator=exact_text_equal,
    )
    state_program = _stdin_cases(
        runner,
        [
            {
                "input": "+\n+\n-\n-\no\no\nc\n",
                "expected": "speed=5 doors=closed\nspeed=30 doors=closed\n"
                "speed=5 doors=closed\nspeed=0 doors=closed\n"
                "speed=0 doors=open\nspeed=0 doors=open\n"
                "speed=0 doors=closed\n",
            }
        ],
    )
    alarms_hidden = _cpp_case(
        runner,
        source_code,
        2677,
        "train_alarms",
        r"""
#include <iostream>
#include <string>
template <typename Action>
void alarm(Action action) {
    try {
        action();
        std::cout << "NO ALARM\n";
    } catch (const char* message) {
        std::cout << message << "\n";
    } catch (...) {
        std::cout << "WRONG TYPE\n";
    }
}
int main() {
    Train train;
    alarm([&]() { train.slower(); });
    train.status();
    train.open_doors();
    alarm([&]() { train.faster(); });
    train.status();
    train.close_doors();
    train.faster();
    train.faster();
    train.faster();
    train.faster();
    alarm([&]() { train.faster(); });
    train.status();
    alarm([&]() { train.open_doors(); });
    train.status();
}
""",
        "already stopped\nspeed=0 doors=closed\ndoors are open\n"
        "speed=0 doors=open\nmax speed\nspeed=90 doors=closed\n"
        "train is moving\nspeed=90 doors=closed\n",
        comparator=exact_text_equal,
    )
    alarms_program = _stdin_cases(
        runner,
        [
            {
                "input": "-\no\n+\nc\n+\n+\n+\n+\n+\no\n",
                "expected": "ALARM: already stopped\nspeed=0 doors=open\n"
                "ALARM: doors are open\nspeed=0 doors=closed\n"
                "speed=5 doors=closed\nspeed=30 doors=closed\n"
                "speed=45 doors=closed\nspeed=90 doors=closed\n"
                "ALARM: max speed\nALARM: train is moving\n",
            }
        ],
    )
    return finish_criteria(
        2677,
        10,
        [
            (
                state_hidden and state_program,
                "ступени скорости, двери и status переключаются верно",
            ),
            (
                alarms_hidden
                and alarms_program
                and source_has_all(source_code, [r"\bthrow\b"]),
                "четыре нарушения выбрасывают точные исключения без смены состояния",
            ),
        ],
    )


def _task_2678(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2678,
        "vec_overload",
        r"""
#include <algorithm>
#include <iostream>
int main() {
    Vec tie_first(3, 4);
    Vec tie_second(0, -5);
    Vec tie = max(tie_first, tie_second);
    std::cout << tie.x << " " << tie.y << "\n";

    Vec longer(-6, 0);
    Vec shorter(5, 3);
    Vec result = max(longer, shorter);
    std::cout << result.x << " " << result.y << "\n";
    std::cout << std::max(-17, 42) << "\n";
}
""",
        "3 4\n-6 0\n42\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [{"input": "17 42\n", "expected": "2 2\n3 4\n42\n"}],
    )
    return finish_criteria(
        2678,
        5,
        [(hidden and program, "перегрузка max сравнивает длины и сохраняет std::max")],
    )


def _task_2680(runner, source_code):
    clean = _cpp_case(
        runner,
        source_code,
        2680,
        "bank_cleanup",
        r"""
#include <cstdio>
int main() {
    std::remove("accounts.txt");
    char filename[64];
    for (int number = 1; number <= 1100; ++number) {
        std::snprintf(filename, sizeof(filename), "account_%d.txt", number);
        std::remove(filename);
    }
    std::puts("clean");
}
""",
        "clean\n",
        comparator=exact_text_equal,
    )
    persistence = _stdin_cases(
        runner,
        [
            {
                "input": "register Alice 100\nchange 1 75\nexit\n",
                "expected": "Registered: 1\nOK, balance: 75\n",
            },
            {
                "input": "balance 1\nchange 1 -175\nbalance 1\nexit\n",
                "expected": "75\nOK, balance: -100\n-100\n",
            },
            {
                "input": "change 1 -1\nbalance 1\nexit\n",
                "expected": "ERROR, balance: -100\n-100\n",
            },
        ],
    )
    registration_program = _stdin_cases(
        runner,
        [
            {
                "input": "register Bob 0\nregister Cara 5\nbalance 999\nfly\nexit\n",
                "expected": "Registered: 2\nRegistered: 3\nNot found\n"
                "Not a command\n",
            }
        ],
    )
    class_hidden = _cpp_case(
        runner,
        source_code,
        2680,
        "bank_class",
        r"""
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>
int main() {
    std::remove("accounts.txt");
    for (int index = 1; index <= 8; ++index) {
        std::string filename = "account_" + std::to_string(index) + ".txt";
        std::remove(filename.c_str());
    }

    char name[] = "Dana";
    int number = Account::register_account(name, 7);
    int registered_count = -1;
    std::ifstream counter("accounts.txt");
    counter >> registered_count;
    counter.close();

    std::string owner;
    int stored_balance = 1;
    int stored_overdraft = -1;
    std::string extra;
    std::ifstream created("account_1.txt");
    bool created_ok = static_cast<bool>(
        std::getline(created, owner)
        && (created >> stored_balance >> stored_overdraft)
        && !(created >> extra)
    );
    created.close();

    std::cout << number << " "
              << (registered_count == 1 && created_ok && owner == "Dana"
                  && stored_balance == 0 && stored_overdraft == 7) << " ";
    {
        Account account(number);
        std::cout << account.get_balance() << " ";
        std::cout << account.change_balance(-7) << " ";
        std::cout << account.get_balance() << " ";
    }

    owner.clear();
    stored_balance = 1;
    stored_overdraft = -1;
    extra.clear();
    std::ifstream saved("account_1.txt");
    bool saved_ok = static_cast<bool>(
        std::getline(saved, owner)
        && (saved >> stored_balance >> stored_overdraft)
        && !(saved >> extra)
    );
    saved.close();
    std::cout << (saved_ok && owner == "Dana" && stored_balance == -7
                  && stored_overdraft == 7) << " ";
    try {
        Account missing(999);
        std::cout << "bad\n";
    } catch (...) {
        std::cout << "missing\n";
    }
}
""",
        "1 1 0 1 -7 1 missing\n",
        time_limit=4,
        comparator=exact_text_equal,
    )
    static_and_exceptions = source_has_all(
        source_code,
        [
            r"\bstatic\b[\s\S]{0,160}\bregister_account\s*\(",
            r"\bthrow\b",
            r"\bcatch\s*\(",
        ],
    )
    return finish_criteria(
        2680,
        10,
        [
            (
                clean and persistence,
                "Account загружается и сохраняется, включая границу овердрафта",
            ),
            (
                clean
                and registration_program
                and class_hidden
                and static_and_exceptions
                and _account_private_storage_policy(source_code),
                "приватные поля Account, владелец и формат account_<n>.txt соблюдены; отсутствующий счёт даёт Not found",
            ),
        ],
    )


def _task_2688(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2688,
        "analyze",
        r"""
#include <iostream>
using AnalyzeSignature = void (*)(const int*, int, int*, int*, long long*);
int main() {
    AnalyzeSignature checked_signature = &analyze;
    (void)checked_signature;
    int one[] = {42};
    int minimum = 0;
    int maximum = 0;
    long long sum = 0;
    analyze(one, 1, &minimum, &maximum, &sum);
    std::cout << minimum << " " << maximum << " " << sum << "\n";

    int mixed[] = {7, -9, 7, 1000000000, -1000000000, 7};
    analyze(mixed, 6, &minimum, &maximum, &sum);
    std::cout << minimum << " " << maximum << " " << sum << "\n";

    static int large[100000];
    for (int i = 0; i < 100000; ++i)
        large[i] = (i % 2 == 0) ? 1000000000 : -999999999;
    analyze(large, 100000, &minimum, &maximum, &sum);
    std::cout << minimum << " " << maximum << " " << sum << "\n";
}
""",
        "42 42 42\n-1000000000 1000000000 12\n"
        "-999999999 1000000000 50000\n",
        time_limit=4,
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {"input": "5\n3 -7 2 9 1\n", "expected": "-7 9 8\n"},
            {"input": "1\n42\n", "expected": "42 42 42\n"},
        ],
    )
    return finish_criteria(
        2688,
        5,
        [
            (
                hidden and program,
                "analyze имеет заданную сигнатуру и за линейный проход находит минимум, максимум и long long сумму",
            )
        ],
    )


def _task_2691(runner, source_code):
    sum_hidden = _cpp_case(
        runner,
        source_code,
        2691,
        "sum_paths",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    long long negative = sum_of(3);
    long long after_negative = __gp_live_allocations;
    long long positive = sum_of(3);
    long long after_positive = __gp_live_allocations;
    long long leaked = __gp_stop_tracking();
    std::printf("%lld %lld %lld %lld %lld\n", negative, after_negative,
                positive, after_positive, leaked);
}
""",
        "6 0 6 0 0\n",
        input_data="-1 -2 -3 1 2 3\n",
        comparator=exact_text_equal,
    )
    output_unchanged = _stdin_cases(
        runner,
        [
            {
                "input": "3\n3\n1 2 3\n2\n-5 -5\n1\n0\n",
                "expected": "6\n10\n0\n",
            }
        ],
    )
    main_hidden = _cpp_case(
        runner,
        source_code,
        2691,
        "main_leak",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    int result = __geekpaste_student_main();
    long long leaked = __gp_stop_tracking();
    std::printf("__return=%d live=%lld\n", result, leaked);
}
""",
        "6\n10\n__return=0 live=0\n",
        input_data="2\n3\n1 2 3\n2\n-5 -5\n",
        comparator=exact_text_equal,
    )
    return finish_criteria(
        2691,
        10,
        [
            (
                sum_hidden and output_unchanged,
                "sum_of не течёт ни на обычном, ни на досрочном return",
            ),
            (main_hidden, "вторая утечка в main устранена"),
        ],
    )


def _task_2693(runner, source_code):
    bookkeeping = _stdin_cases(
        runner,
        [
            {
                "input": "take -5\ntake 100\nfree 1\ntake 7\nget 1\nget 3\n"
                "free 1\nstat\nfree 2\nstat\nexit\n",
                "expected": "taken 1\ntaken 2\nfreed 1\ntaken 3\n"
                "no such block\n7\nno such block\n"
                "taken=3 freed=1 leaked=2\nfreed 2\n"
                "taken=3 freed=2 leaked=1\n"
                "taken=3 freed=3 leaked=0\n",
            },
            {
                "input": "stat\nexit\n",
                "expected": "taken=0 freed=0 leaked=0\n"
                "taken=0 freed=0 leaked=0\n",
            },
        ],
    )
    cleanup_hidden = _cpp_case(
        runner,
        source_code,
        2693,
        "exit_cleanup",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    int result = __geekpaste_student_main();
    long long leaked = __gp_stop_tracking();
    std::printf("__return=%d live=%lld\n", result, leaked);
}
""",
        "taken 1\ntaken 2\nfreed 1\ntaken 3\n"
        "taken=3 freed=3 leaked=0\n__return=0 live=0\n",
        input_data="take 10\ntake 20\nfree 1\ntake 30\nexit\n",
        comparator=exact_text_equal,
    )
    wrappers = _has_global_counters_and_wrappers(source_code)
    return finish_criteria(
        2693,
        10,
        [
            (
                bookkeeping and wrappers,
                "глобальные счётчики и обёртки ведут корректный учёт блоков",
            ),
            (
                cleanup_hidden and source_has_all(source_code, [r"\bdelete\b"]),
                "exit освобождает каждый оставшийся настоящий блок",
            ),
        ],
    )


def _task_2698(runner, source_code):
    basic_hidden = _cpp_case(
        runner,
        source_code,
        2698,
        "vector_basic",
        r"""
#include <iostream>
int main() {
    Vector values;
    std::cout << values.get_size() << "\n";
    for (int i = 0; i < 50; ++i) values.push_back(i * i - 3);
    std::cout << values.get_size() << " " << values.get(0)
              << " " << values.get(49) << "\n";
    values.set(0, -700);
    values.set(49, 123456);
    std::cout << values.get(0) << " " << values.get(49) << "\n";
}
""",
        "0\n50 -3 2398\n-700 123456\n",
        comparator=exact_text_equal,
    )
    basic_program = _stdin_cases(
        runner,
        [
            {
                "input": "size\nprint\nget -1\npush 1\npush 2\npush 3\n"
                "size\nset 0 9\nget 0\nget 7\nprint\nexit\n",
                "expected": "0\n\nerror\n3\n9\nerror\n9 2 3\n",
            }
        ],
    )
    bounds_hidden = _cpp_case(
        runner,
        source_code,
        2698,
        "vector_bounds",
        r"""
#include <iostream>
template <typename Action>
bool throws(Action action) {
    try { action(); } catch (...) { return true; }
    return false;
}
int main() {
    Vector values;
    values.push_back(11);
    values.push_back(22);
    std::cout << throws([&]() { (void)values.get(-1); }) << " ";
    std::cout << throws([&]() { (void)values.get(2); }) << " ";
    std::cout << throws([&]() { values.set(-1, 9); }) << " ";
    std::cout << throws([&]() { values.set(2, 9); }) << " ";
    std::cout << values.get(0) << " " << values.get(1) << "\n";
}
""",
        "1 1 1 1 11 22\n",
        comparator=exact_text_equal,
    )
    memory_hidden = _cpp_case(
        runner,
        source_code,
        2698,
        "vector_memory",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    {
        Vector values;
        for (int i = 0; i < 200; ++i) values.push_back(i);
    }
    long long leaked = __gp_stop_tracking();
    std::printf("live=%lld\n", leaked);
}
""",
        "live=0\n",
        time_limit=5,
        comparator=exact_text_equal,
    )
    return finish_criteria(
        2698,
        15,
        [
            (
                basic_hidden and basic_program and _basic_vector_policy(source_code),
                "Vector хранит два приватных поля в куче и реализует базовый API",
            ),
            (bounds_hidden, "get/set выбрасывают исключение на обеих границах"),
            (
                memory_hidden
                and source_has_all(source_code, [r"\bdelete\s*\[\s*\]"]),
                "деструктор освобождает все динамические массивы",
            ),
        ],
    )


def _task_2699(runner, source_code):
    cases = [
        {"input": "1\n", "expected": "0\n0\n"},
        {"input": "2\n", "expected": "1\n1\n"},
        {"input": "8\n", "expected": "28\n7\n"},
        {"input": "1000\n", "expected": "499500\n1023\n"},
        {
            "input": "1000000000\n",
            "expected": "499999999500000000\n1073741823\n",
            "time_limit": 2,
        },
    ]
    return finish_criteria(
        2699,
        5,
        [
            (
                _stdin_cases(runner, cases),
                "обе стратегии посчитаны формулой и степенями двойки до 10^9",
            )
        ],
    )


def _task_2702(runner, source_code):
    hidden = _cpp_case(
        runner,
        source_code,
        2702,
        "vector_operators",
        r"""
#include <iostream>
int main() {
    Vector<int> values;
    values.push_back(4);
    values.push_back(8);
    values.push_back(15);
    std::cout << values[1] << "\n";
    values[0] = 42;
    (std::cout << values) << " | " << values[2] << "\n";

    Vector<char> letters;
    letters.push_back('x');
    letters.push_back('y');
    std::cout << letters << "\n";
}
""",
        "8\n42 8 15 | 15\nx y\n",
        comparator=exact_text_equal,
    )
    program = _stdin_cases(
        runner,
        [
            {
                "input": "push 4\npush 8\npush 15\nget 1\nset 0 42\n"
                "print\nexit\n",
                "expected": "8\n42 8 15\n",
            }
        ],
    )
    return finish_criteria(
        2702,
        5,
        [
            (
                hidden and program and _template_vector_operator_policy(source_code),
                "operator[] возвращает T&, а свободный operator<< поддерживает цепочку",
            )
        ],
    )


def _task_2703(runner, source_code):
    basic_hidden = _cpp_case(
        runner,
        source_code,
        2703,
        "string_basic",
        r"""
#include <iostream>
template <typename Action>
bool throws(Action action) {
    try { action(); } catch (...) { return true; }
    return false;
}
int main() {
    char raw[] = "cat";
    String value(raw);
    raw[0] = 'R';
    std::cout << value.length() << " " << value.c_str() << " "
              << (value.c_str()[value.length()] == '\0') << "\n";
    value[1] = 'o';
    value.push_back('s');
    std::cout << value[1] << " " << value.c_str() << " "
              << value.length() << " "
              << (value.c_str()[value.length()] == '\0') << "\n";
    std::cout << throws([&]() { (void)value[-1]; }) << " "
              << throws([&]() { (void)value[value.length()]; }) << " "
              << value.c_str() << "\n";
}
""",
        "3 cat 1\no cots 4 1\n1 1 cots\n",
        comparator=exact_text_equal,
    )
    basic_program = _stdin_cases(
        runner,
        [
            {
                "input": "set 0 cat\nlen 0\nat 0 1\napp 0 s\n"
                "print 0\ncstr 0\nexit\n",
                "expected": "3\na\ncats\ncats\n",
            }
        ],
    )
    concat_hidden = _cpp_case(
        runner,
        source_code,
        2703,
        "string_concat",
        r"""
#include <iostream>
int main() {
    String left("ab");
    String right("CD");
    String joined = left + right;
    std::cout << joined.c_str() << " " << left.c_str()
              << " " << right.c_str() << "\n";
    String* address = &(left += right);
    std::cout << (address == &left) << " " << left.c_str()
              << " " << right.c_str() << "\n";
    (left += String("!")) += String("?");
    std::cout << left.c_str() << "\n";
}
""",
        "abCD ab CD\n1 abCD CD\nabCD!?\n",
        comparator=exact_text_equal,
    )
    concat_program = _stdin_cases(
        runner,
        [
            {
                "input": "set 0 cat\nset 1 dog\nplus\nprint 0\nprint 1\n"
                "pluseq\nprint 0\nexit\n",
                "expected": "catdog\ncat\ndog\ncatdog\ncatdog\n",
            }
        ],
    )
    compare_hidden = _cpp_case(
        runner,
        source_code,
        2703,
        "string_compare_multiply",
        r"""
#include <iostream>
int main() {
    String empty("");
    String cat("cat");
    String cattle("cattle");
    String second_empty("");
    std::cout << (empty == second_empty) << " " << (cat == cattle)
              << " " << (cat < cattle) << " " << (cattle < cat) << "\n";
    String zero = cat * 0;
    String once = cat * 1;
    String thrice = cat * 3;
    std::cout << zero.length() << " " << once.c_str()
              << " " << thrice.c_str() << " " << cat.c_str() << "\n";
}
""",
        "1 0 1 0\n0 cat catcatcat cat\n",
        comparator=exact_text_equal,
    )
    compare_program = _stdin_cases(
        runner,
        [
            {
                "input": "set 0 cat\nset 1 cattle\neq\nless\nmul 0 0\n"
                "mul 0 3\nset 1 cat\neq\nless\nexit\n",
                "expected": "no\nyes\n\ncatcatcat\nyes\nno\n",
            }
        ],
    )
    copy_hidden = _cpp_case(
        runner,
        source_code,
        2703,
        "string_rule_three_substr_stream",
        r"""
#include <iostream>
int main() {
    String original("abcdef");
    String copy(original);
    copy[0] = 'X';
    String assigned("z");
    String* address = &(assigned = original);
    assigned[1] = 'Y';
    original = original;
    std::cout << original.c_str() << " " << copy.c_str() << " "
              << assigned.c_str() << " " << (address == &assigned) << "\n";

    String first = original.substr(0, 0);
    String middle = original.substr(2, 3);
    String end = original.substr(6, 0);
    bool invalid = false;
    try { (void)original.substr(5, 2); } catch (...) { invalid = true; }
    std::cout << first.length() << " " << middle.c_str() << " "
              << end.length() << " " << invalid << "\n";
    const String frozen("stream");
    (std::cout << frozen) << "|ok\n";
}
""",
        "abcdef Xbcdef aYcdef 1\n0 cde 0 1\nstream|ok\n",
        comparator=exact_text_equal,
    )
    substr_program = _stdin_cases(
        runner,
        [
            {
                "input": "set 0 abcdef\nsub 0 2 3\nsub 0 6 0\n"
                "sub 0 5 2\nexit\n",
                "expected": "cde\n\nerror\n",
            }
        ],
    )
    memory_hidden = _cpp_case(
        runner,
        source_code,
        2703,
        "string_memory",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    {
        String first("alpha");
        String copy(first);
        String assigned("x");
        assigned = first;
        assigned = assigned;
        for (int i = 0; i < 100; ++i) assigned.push_back('z');
        String joined = first + copy;
        String repeated = joined * 7;
        String piece = repeated.substr(3, 20);
        (void)piece.length();
    }
    long long leaked = __gp_stop_tracking();
    std::printf("live=%lld\n", leaked);
}
""",
        "live=0\n",
        time_limit=5,
        comparator=exact_text_equal,
    )
    return finish_criteria(
        2703,
        20,
        [
            (
                basic_hidden
                and basic_program
                and _string_storage_policy(source_code),
                "char* хранится своей копией, length O(1), [], push_back и c_str верны",
            ),
            (
                concat_hidden and concat_program,
                "+ не меняет операнды, += меняет левый и возвращает String&",
            ),
            (
                compare_hidden and compare_program,
                "*, == и лексикографический < работают на пустых и префиксах",
            ),
            (
                copy_hidden
                and substr_program
                and memory_hidden
                and _string_rule_of_three_policy(source_code),
                "правило трёх, substr, потоковый вывод и освобождение памяти",
            ),
        ],
    )


def _task_2706(runner, source_code):
    correctness = _stdin_cases(
        runner,
        [
            {"input": "while (i < n) { a[i] = 0; }\n", "expected": "OK\n"},
            {"input": "sum = (a[0] + b[1);\n", "expected": "18\n"},
            {"input": "f(x))\n", "expected": "5\n"},
            {"input": "(()\n", "expected": "1\n"},
            {"input": "([)]\n", "expected": "3\n"},
            {"input": "{x[()]}\n", "expected": "OK\n"},
            {"input": "]abc\n", "expected": "1\n"},
            {"input": "([\n", "expected": "2\n"},
        ],
    )
    long_valid = "(" * 100000 + ")" * 100000 + "\n"
    long_unclosed = "x" + "{" * 199999 + "\n"
    performance = _stdin_cases(
        runner,
        [
            {"input": long_valid, "expected": "OK\n", "time_limit": 3},
            {"input": long_unclosed, "expected": "200000\n", "time_limit": 3},
        ],
    )
    stack_hidden = _cpp_case(
        runner,
        source_code,
        2706,
        "stack_contract",
        r"""
#include <iostream>
int main() {
    Stack<int> values;
    std::cout << values.empty() << "\n";
    values.push(4);
    values.push(9);
    std::cout << values.empty() << " " << values.pop() << " "
              << values.pop() << " " << values.empty() << "\n";
}
""",
        "1\n0 9 4 1\n",
        comparator=exact_text_equal,
    )
    memory_hidden = _cpp_case(
        runner,
        source_code,
        2706,
        "bracket_memory",
        _ALLOCATION_TRACKER
        + r"""
int main() {
    __gp_begin_tracking();
    int result = __geekpaste_student_main();
    long long leaked = __gp_stop_tracking();
    std::printf("__return=%d live=%lld\n", result, leaked);
}
""",
        "OK\n__return=0 live=0\n",
        input_data="(" * 10000 + ")" * 10000 + "\n",
        time_limit=4,
        comparator=exact_text_equal,
    )
    return finish_criteria(
        2706,
        10,
        [
            (correctness, "первая ошибка и вершина незакрытого стека определяются верно"),
            (
                performance
                and stack_hidden
                and memory_hidden
                and _uses_own_stack(source_code),
                "200 000 символов обрабатываются за O(n) реально используемым Stack<T> без ошибок памяти",
            ),
        ],
    )


TASKS = {
    2665: (5, _task_2665),
    2666: (5, _task_2666),
    2667: (5, _task_2667),
    2670: (5, _task_2670),
    2676: (5, _task_2676),
    2677: (10, _task_2677),
    2678: (5, _task_2678),
    2680: (10, _task_2680),
    2688: (5, _task_2688),
    2691: (10, _task_2691),
    2693: (10, _task_2693),
    2698: (15, _task_2698),
    2699: (5, _task_2699),
    2702: (5, _task_2702),
    2703: (20, _task_2703),
    2706: (10, _task_2706),
}
