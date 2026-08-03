import os
import re
import shutil
import subprocess
import tempfile
import unittest

from environments import grade8_2026_chapters_5_6 as target
from runner import SolutionException


TASK_MAXIMA = {
    2665: 5,
    2666: 5,
    2667: 5,
    2670: 5,
    2676: 5,
    2677: 10,
    2678: 5,
    2680: 10,
    2688: 5,
    2691: 10,
    2693: 10,
    2698: 15,
    2699: 5,
    2702: 5,
    2703: 20,
    2706: 10,
}


PASSING_SOURCES = {
    2677: 'void safety_rule() { throw "alarm"; }',
    2676: r"""
int divide(int a, int b) { if (b == 0) throw "division by zero"; return a / b; }
int main() { while (true) { try { break; } catch (const char*) { } } }
""",
    2680: r"""
class Account {
private:
    int number;
    char owner[21];
    int balance;
    int overdraft;
public:
    static int register_account(const char*, int) { return 1; }
};
void missing() { throw "missing"; }
int main() { try { missing(); } catch (const char*) { } }
""",
    2688: r"""
void analyze(const int a[], int n, int* minimum, int* maximum, long long* sum) {
    for (int i = 0; i < n; ++i) { *sum += a[i]; }
}
""",
    2693: r"""
int taken;
int freed;
int* allocate_block(int value) { ++taken; return new int(value); }
void release_block(int* pointer) { delete pointer; ++freed; }
int main() { int* pointer = allocate_block(1); release_block(pointer); }
""",
    2698: r"""
class Vector {
private:
    int* data;
    int size;
public:
    Vector() : data(nullptr), size(0) { }
    ~Vector() { delete[] data; }
    void push_back(int value) { int* next = new int[size + 1]; (void)value; data = next; }
    int get(int index) { return data[index]; }
    void set(int index, int value) { data[index] = value; }
    int get_size() { return size; }
};
int main() { }
""",
    2702: r"""
template <typename T>
class Vector {
public:
    void push_back(T) { }
    T& operator[](int index) { return data[index]; }
private:
    T data[10];
};
template <typename T>
ostream& operator<<(ostream& output, const Vector<T>& value) { return output; }
int main() { }
""",
    2703: r"""
class String {
private:
    char* data;
    int stored_length;
public:
    String(const char* text) : data(new char[1]), stored_length(0) { (void)text; }
    String(const String& other) : data(new char[1]), stored_length(other.stored_length) { }
    ~String() { delete[] data; }
    String& operator=(const String& other) { (void)other; return *this; }
    int length() const { return stored_length; }
};
ostream& operator<<(ostream& output, const String& value) { return output; }
int main() { }
""",
    2706: r"""
template <typename T>
class Stack {
public:
    bool empty() { return false; }
    void push(T) { }
    T pop() { return T(); }
};
int main() {
    Stack<char> brackets;
    brackets.push('(');
    (void)brackets.pop();
    (void)brackets.empty();
}
""",
}


CPP_REFERENCE_SOURCES = {
    2680: r"""
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace std;

class Account {
private:
    int number;
    char owner[21];
    int balance;
    int overdraft;

    string filename() const {
        return "account_" + to_string(number) + ".txt";
    }
public:
    explicit Account(int account_number) : number(account_number) {
        ifstream input(filename());
        if (!(input >> owner >> balance >> overdraft)) throw runtime_error("missing");
    }
    ~Account() {
        ofstream output(filename());
        output << owner << '\n' << balance << '\n' << overdraft << '\n';
    }
    int get_balance() const { return balance; }
    bool change_balance(int amount) {
        if (balance + amount < -overdraft) return false;
        balance += amount;
        return true;
    }
    static int register_account(const char* name, int overdraft) {
        int count = 0;
        ifstream counter_input("accounts.txt");
        counter_input >> count;
        ++count;
        ofstream counter_output("accounts.txt");
        counter_output << count << '\n';
        ofstream account_output("account_" + to_string(count) + ".txt");
        account_output << name << '\n' << 0 << '\n' << overdraft << '\n';
        return count;
    }
};

int main() {
    string command;
    while (cin >> command) {
        if (command == "register") {
            string name;
            int overdraft;
            cin >> name >> overdraft;
            cout << "Registered: "
                 << Account::register_account(name.c_str(), overdraft) << '\n';
        } else if (command == "balance") {
            int number;
            cin >> number;
            try { Account account(number); cout << account.get_balance() << '\n'; }
            catch (...) { cout << "Not found\n"; }
        } else if (command == "change") {
            int number, amount;
            cin >> number >> amount;
            try {
                Account account(number);
                bool changed = account.change_balance(amount);
                cout << (changed ? "OK, balance: " : "ERROR, balance: ")
                     << account.get_balance() << '\n';
            } catch (...) { cout << "Not found\n"; }
        } else if (command == "exit") {
            break;
        } else {
            cout << "Not a command\n";
        }
    }
    return 0;
}
""",
    2688: r"""
#include <iostream>
using namespace std;

void analyze(int const* values, int size, int* minimum, int* maximum,
             long long* sum) {
    *minimum = values[0];
    *maximum = values[0];
    *sum = 0;
    for (int index = 0; index < size; ++index) {
        if (values[index] < *minimum) *minimum = values[index];
        if (values[index] > *maximum) *maximum = values[index];
        *sum += values[index];
    }
}

int main() {
    int size;
    cin >> size;
    int* values = new int[size];
    for (int index = 0; index < size; ++index) cin >> values[index];
    int minimum, maximum;
    long long sum;
    analyze(values, size, &minimum, &maximum, &sum);
    cout << minimum << " " << maximum << " " << sum << '\n';
    delete[] values;
    return 0;
}
""",
    2691: r"""
#include <iostream>
using namespace std;

class Accumulator {
private:
    long long total;
public:
    Accumulator() : total(0) { }
    void add(int value) { total += value; }
    long long get() { return total; }
};

long long sum_of(int n) {
    Accumulator accumulator;
    for (int i = 0; i < n; ++i) {
        int value;
        cin >> value;
        accumulator.add(value);
    }
    long long result = accumulator.get();
    return result < 0 ? -result : result;
}

int main() {
    int count;
    cin >> count;
    for (int i = 0; i < count; ++i) {
        int size;
        cin >> size;
        cout << sum_of(size) << endl;
    }
    return 0;
}
""",
    2693: r"""
#include <iostream>
#include <string>
using namespace std;

int taken = 0;
int freed = 0;

int* allocate_block(int value) {
    ++taken;
    return new int(value);
}

void release_block(int* pointer) {
    delete pointer;
    ++freed;
}

void print_stat() {
    cout << "taken=" << taken << " freed=" << freed
         << " leaked=" << taken - freed << endl;
}

int main() {
    int* blocks[1000] = {};
    int issued = 0;
    string command;
    while (cin >> command) {
        if (command == "take") {
            int value;
            cin >> value;
            blocks[issued] = allocate_block(value);
            ++issued;
            cout << "taken " << issued << endl;
        } else if (command == "get") {
            int number;
            cin >> number;
            if (number < 1 || number > issued || blocks[number - 1] == nullptr)
                cout << "no such block" << endl;
            else
                cout << *blocks[number - 1] << endl;
        } else if (command == "free") {
            int number;
            cin >> number;
            if (number < 1 || number > issued || blocks[number - 1] == nullptr) {
                cout << "no such block" << endl;
            } else {
                release_block(blocks[number - 1]);
                blocks[number - 1] = nullptr;
                cout << "freed " << number << endl;
            }
        } else if (command == "stat") {
            print_stat();
        } else if (command == "exit") {
            for (int i = 0; i < issued; ++i) {
                if (blocks[i] != nullptr) release_block(blocks[i]);
            }
            print_stat();
            break;
        }
    }
    return 0;
}
""",
    2698: r"""
#include <iostream>
#include <string>
using namespace std;

class Vector {
private:
    int* data;
    int size;
public:
    Vector() : data(nullptr), size(0) { }
    ~Vector() { delete[] data; }
    void push_back(int value) {
        int* next = new int[size + 1];
        for (int i = 0; i < size; ++i) next[i] = data[i];
        next[size] = value;
        delete[] data;
        data = next;
        ++size;
    }
    int get(int index) {
        if (index < 0 || index >= size) throw "index";
        return data[index];
    }
    void set(int index, int value) {
        if (index < 0 || index >= size) throw "index";
        data[index] = value;
    }
    int get_size() { return size; }
};

int main() {
    Vector values;
    string command;
    while (cin >> command) {
        if (command == "push") {
            int value;
            cin >> value;
            values.push_back(value);
        } else if (command == "size") {
            cout << values.get_size() << endl;
        } else if (command == "get") {
            int index;
            cin >> index;
            try { cout << values.get(index) << endl; }
            catch (...) { cout << "error" << endl; }
        } else if (command == "set") {
            int index, value;
            cin >> index >> value;
            try { values.set(index, value); }
            catch (...) { cout << "error" << endl; }
        } else if (command == "print") {
            for (int i = 0; i < values.get_size(); ++i) {
                if (i) cout << " ";
                cout << values.get(i);
            }
            cout << endl;
        } else if (command == "exit") {
            break;
        }
    }
    return 0;
}
""",
    2703: r"""
#include <cstring>
#include <iostream>
#include <string>
using namespace std;

class String {
private:
    char* data;
    int stored_length;
public:
    String(const char* text = "") {
        stored_length = static_cast<int>(strlen(text));
        data = new char[stored_length + 1];
        strcpy(data, text);
    }
    String(const String& other) {
        stored_length = other.stored_length;
        data = new char[stored_length + 1];
        strcpy(data, other.data);
    }
    ~String() { delete[] data; }
    String& operator=(const String& other) {
        if (this == &other) return *this;
        char* next = new char[other.stored_length + 1];
        strcpy(next, other.data);
        delete[] data;
        data = next;
        stored_length = other.stored_length;
        return *this;
    }
    int length() const { return stored_length; }
    char& operator[](int index) {
        if (index < 0 || index >= stored_length) throw "index";
        return data[index];
    }
    void push_back(char symbol) {
        char* next = new char[stored_length + 2];
        memcpy(next, data, stored_length);
        next[stored_length] = symbol;
        next[stored_length + 1] = '\0';
        delete[] data;
        data = next;
        ++stored_length;
    }
    const char* c_str() const { return data; }
    String substr(int position, int count) const {
        if (position < 0 || count < 0 || position + count > stored_length)
            throw "range";
        char* buffer = new char[count + 1];
        memcpy(buffer, data + position, count);
        buffer[count] = '\0';
        String result(buffer);
        delete[] buffer;
        return result;
    }
    String operator+(const String& other) const {
        char* buffer = new char[stored_length + other.stored_length + 1];
        strcpy(buffer, data);
        strcat(buffer, other.data);
        String result(buffer);
        delete[] buffer;
        return result;
    }
    String& operator+=(const String& other) {
        *this = *this + other;
        return *this;
    }
    String operator*(int count) const {
        String result;
        for (int i = 0; i < count; ++i) result += *this;
        return result;
    }
    bool operator==(const String& other) const {
        return strcmp(data, other.data) == 0;
    }
    bool operator<(const String& other) const {
        return strcmp(data, other.data) < 0;
    }
};

ostream& operator<<(ostream& output, const String& value) {
    return output << value.c_str();
}

int main() {
    String values[2];
    string command;
    while (cin >> command) {
        if (command == "set") {
            int index;
            string word;
            cin >> index >> word;
            values[index] = String(word.c_str());
        } else if (command == "len") {
            int index;
            cin >> index;
            cout << values[index].length() << endl;
        } else if (command == "at") {
            int index, position;
            cin >> index >> position;
            try { cout << values[index][position] << endl; }
            catch (...) { cout << "error" << endl; }
        } else if (command == "app") {
            int index;
            char symbol;
            cin >> index >> symbol;
            values[index].push_back(symbol);
        } else if (command == "print") {
            int index;
            cin >> index;
            cout << values[index] << endl;
        } else if (command == "cstr") {
            int index;
            cin >> index;
            cout << values[index].c_str() << endl;
        } else if (command == "plus") {
            cout << values[0] + values[1] << endl;
        } else if (command == "pluseq") {
            cout << (values[0] += values[1]) << endl;
        } else if (command == "mul") {
            int index, count;
            cin >> index >> count;
            cout << values[index] * count << endl;
        } else if (command == "eq") {
            cout << (values[0] == values[1] ? "yes" : "no") << endl;
        } else if (command == "less") {
            cout << (values[0] < values[1] ? "yes" : "no") << endl;
        } else if (command == "sub") {
            int index, position, count;
            cin >> index >> position >> count;
            try { cout << values[index].substr(position, count) << endl; }
            catch (...) { cout << "error" << endl; }
        } else if (command == "exit") {
            break;
        }
    }
    return 0;
}
""",
    2706: r"""
#include <iostream>
#include <string>
using namespace std;

template <typename T>
class Vector {
private:
    T* data;
    int stored_size;
    int capacity;
public:
    Vector() : data(nullptr), stored_size(0), capacity(0) { }
    ~Vector() { delete[] data; }
    void push_back(const T& value) {
        if (stored_size == capacity) {
            int next_capacity = capacity == 0 ? 1 : capacity * 2;
            T* next = new T[next_capacity];
            for (int index = 0; index < stored_size; ++index) next[index] = data[index];
            delete[] data;
            data = next;
            capacity = next_capacity;
        }
        data[stored_size++] = value;
    }
    T pop_back() {
        if (stored_size == 0) throw "empty";
        return data[--stored_size];
    }
    int size() const { return stored_size; }
};

template <typename T>
class Stack {
private:
    Vector<T> values;
public:
    bool empty() const { return values.size() == 0; }
    void push(const T& value) { values.push_back(value); }
    T pop() { return values.pop_back(); }
};

struct Opening {
    char bracket;
    int position;
};

int main() {
    string line;
    getline(cin, line);
    Stack<Opening> brackets;
    for (int index = 0; index < static_cast<int>(line.size()); ++index) {
        char symbol = line[index];
        if (symbol == '(' || symbol == '[' || symbol == '{') {
            brackets.push({symbol, index + 1});
        } else if (symbol == ')' || symbol == ']' || symbol == '}') {
            if (brackets.empty()) {
                cout << index + 1 << '\n';
                return 0;
            }
            Opening opening = brackets.pop();
            bool matches = (opening.bracket == '(' && symbol == ')')
                || (opening.bracket == '[' && symbol == ']')
                || (opening.bracket == '{' && symbol == '}');
            if (!matches) {
                cout << index + 1 << '\n';
                return 0;
            }
        }
    }
    if (!brackets.empty()) cout << brackets.pop().position << '\n';
    else cout << "OK\n";
    return 0;
}
""",
}


HARNESS_OUTPUTS = {
    (2665, "pet_methods"): "hunger=90 energy=0\nhunger=80 energy=0\n"
    "hunger=0 energy=80\nhunger=80 energy=0\n",
    (2666, "sludge_truck"): "1 10 0 10 0\n1 5 0\n",
    (2667, "pet_constructors"): "hunger=50 energy=50\nhunger=100 energy=50\n"
    "hunger=95 energy=7\nhunger=100 energy=7\n",
    (2670, "coffee_machine"): "000\n0 1\n12 0 1 1\n3 1 1 0\n",
    (2676, "divide_function"): "3 -3 -3 1\n",
    (2677, "train_states"): "speed=0 doors=closed\nspeed=30 doors=closed\n"
    "speed=90 doors=closed\nspeed=0 doors=open\nspeed=0 doors=closed\n",
    (2677, "train_alarms"): "already stopped\nspeed=0 doors=closed\n"
    "doors are open\nspeed=0 doors=open\nmax speed\n"
    "speed=90 doors=closed\ntrain is moving\nspeed=90 doors=closed\n",
    (2678, "vec_overload"): "3 4\n-6 0\n42\n",
    (2680, "bank_cleanup"): "clean\n",
    (2680, "bank_class"): "1 1 0 1 -7 1 missing\n",
    (2688, "analyze"): "42 42 42\n-1000000000 1000000000 12\n"
    "-999999999 1000000000 50000\n",
    (2691, "sum_paths"): "6 0 6 0 0\n",
    (2691, "main_leak"): "6\n10\n__return=0 live=0\n",
    (2693, "exit_cleanup"): "taken 1\ntaken 2\nfreed 1\ntaken 3\n"
    "taken=3 freed=3 leaked=0\n__return=0 live=0\n",
    (2698, "vector_basic"): "0\n50 -3 2398\n-700 123456\n",
    (2698, "vector_bounds"): "1 1 1 1 11 22\n",
    (2698, "vector_memory"): "live=0\n",
    (2702, "vector_operators"): "8\n42 8 15 | 15\nx y\n",
    (2703, "string_basic"): "3 cat 1\no cots 4 1\n1 1 cots\n",
    (2703, "string_concat"): "abCD ab CD\n1 abCD CD\nabCD!?\n",
    (2703, "string_compare_multiply"): "1 0 1 0\n0 cat catcatcat cat\n",
    (2703, "string_rule_three_substr_stream"): "abcdef Xbcdef aYcdef 1\n"
    "0 cde 0 1\nstream|ok\n",
    (2703, "string_memory"): "live=0\n",
    (2706, "stack_contract"): "1\n0 9 4 1\n",
    (2706, "bracket_memory"): "OK\n__return=0 live=0\n",
}


PROGRAM_OUTPUTS = {
    (2665, ""): "hunger=50 energy=50\nhunger=70 energy=30\n"
    "hunger=100 energy=10\n",
    (2666, ""): "Pumped, tank: 3\nPumped, tank: 6\nPumped, tank: 9\n"
    "Pumped, tank: 10\nFull, going home\nTank: 0\n",
    (2667, ""): "hunger=50 energy=50\nhunger=80 energy=50\n"
    "hunger=80 energy=40\n",
    (2670, ""): "Add coffee - OK\nAdd water - OK\nAdd milk - OK\n"
    + "Cup is ready...\n" * 12
    + "Done!",
    (2676, "10 2\n7 0\n9 4\n"): "5\nALARM: division by zero\n2\n",
    (2676, "-9 2\n1 0\n8 -3\n0 5\n"): "-4\nALARM: division by zero\n-2\n0\n",
    (2677, "+\n+\n-\n-\no\no\nc\n"): "speed=5 doors=closed\n"
    "speed=30 doors=closed\nspeed=5 doors=closed\nspeed=0 doors=closed\n"
    "speed=0 doors=open\nspeed=0 doors=open\nspeed=0 doors=closed\n",
    (2677, "-\no\n+\nc\n+\n+\n+\n+\n+\no\n"): "ALARM: already stopped\n"
    "speed=0 doors=open\nALARM: doors are open\nspeed=0 doors=closed\n"
    "speed=5 doors=closed\nspeed=30 doors=closed\nspeed=45 doors=closed\n"
    "speed=90 doors=closed\nALARM: max speed\nALARM: train is moving\n",
    (2678, "17 42\n"): "2 2\n3 4\n42\n",
    (2680, "register Alice 100\nchange 1 75\nexit\n"): "Registered: 1\n"
    "OK, balance: 75\n",
    (2680, "balance 1\nchange 1 -175\nbalance 1\nexit\n"): "75\n"
    "OK, balance: -100\n-100\n",
    (2680, "change 1 -1\nbalance 1\nexit\n"): "ERROR, balance: -100\n-100\n",
    (2680, "register Bob 0\nregister Cara 5\nbalance 999\nfly\nexit\n"): "Registered: 2\n"
    "Registered: 3\nNot found\nNot a command\n",
    (2688, "5\n3 -7 2 9 1\n"): "-7 9 8\n",
    (2688, "1\n42\n"): "42 42 42\n",
    (2691, "3\n3\n1 2 3\n2\n-5 -5\n1\n0\n"): "6\n10\n0\n",
    (
        2693,
        "take -5\ntake 100\nfree 1\ntake 7\nget 1\nget 3\nfree 1\n"
        "stat\nfree 2\nstat\nexit\n",
    ): "taken 1\ntaken 2\nfreed 1\ntaken 3\nno such block\n7\n"
    "no such block\ntaken=3 freed=1 leaked=2\nfreed 2\n"
    "taken=3 freed=2 leaked=1\ntaken=3 freed=3 leaked=0\n",
    (2693, "stat\nexit\n"): "taken=0 freed=0 leaked=0\n"
    "taken=0 freed=0 leaked=0\n",
    (
        2698,
        "size\nprint\nget -1\npush 1\npush 2\npush 3\nsize\n"
        "set 0 9\nget 0\nget 7\nprint\nexit\n",
    ): "0\n\nerror\n3\n9\nerror\n9 2 3\n",
    (2702, "push 4\npush 8\npush 15\nget 1\nset 0 42\nprint\nexit\n"): "8\n"
    "42 8 15\n",
    (2703, "set 0 cat\nlen 0\nat 0 1\napp 0 s\nprint 0\ncstr 0\nexit\n"): "3\n"
    "a\ncats\ncats\n",
    (
        2703,
        "set 0 cat\nset 1 dog\nplus\nprint 0\nprint 1\npluseq\nprint 0\nexit\n",
    ): "catdog\ncat\ndog\ncatdog\ncatdog\n",
    (
        2703,
        "set 0 cat\nset 1 cattle\neq\nless\nmul 0 0\nmul 0 3\n"
        "set 1 cat\neq\nless\nexit\n",
    ): "no\nyes\n\ncatcatcat\nyes\nno\n",
    (2703, "set 0 abcdef\nsub 0 2 3\nsub 0 6 0\nsub 0 5 2\nexit\n"): "cde\n"
    "\nerror\n",
}


class ContractRunner:
    def __init__(self, task_id, fail=False):
        self.task_id = task_id
        self.fail = fail
        self.program_calls = []
        self.harness_calls = []

    def __call__(self, input_data, time_limit=1):
        input_data = str(input_data).replace("\r", "")
        self.program_calls.append((input_data, time_limit))
        if self.fail:
            return "__wrong__\n"
        fixed = PROGRAM_OUTPUTS.get((self.task_id, input_data))
        if fixed is not None:
            return fixed
        if self.task_id == 2699:
            n = int(input_data.strip())
            grow_one = n * (n - 1) // 2
            capacity = 1
            grow_double = 0
            while capacity < n:
                grow_double += capacity
                capacity *= 2
            return f"{grow_one}\n{grow_double}\n"
        if self.task_id == 2706:
            return self._brackets(input_data.rstrip("\n"))
        raise AssertionError(f"unexpected stdin for task {self.task_id}: {input_data!r}")

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
        compile_options=None,
    ):
        self.assert_no_probe(probe_source)
        marker = re.search(r"GP_TASK_(\d+)_([A-Za-z0-9_]+)", source_code)
        if not marker:
            raise AssertionError("hidden C++ source has no stable task marker")
        key = (int(marker.group(1)), marker.group(2))
        self.harness_calls.append(
            (key, input_data, time_limit, source_code, compile_options)
        )
        if self.fail:
            return "__wrong__\n"
        try:
            return HARNESS_OUTPUTS[key]
        except KeyError as error:
            raise AssertionError(f"unexpected harness {key}") from error

    def assert_no_probe(self, probe_source):
        if probe_source is not None:
            raise AssertionError("C++ harness must not use a Python probe")

    @staticmethod
    def _brackets(line):
        opening = "([{"
        matching = {")": "(", "]": "[", "}": "{"}
        stack = []
        for position, symbol in enumerate(line, start=1):
            if symbol in opening:
                stack.append((symbol, position))
            elif symbol in matching:
                if not stack or stack[-1][0] != matching[symbol]:
                    return f"{position}\n"
                stack.pop()
        if stack:
            return f"{stack[-1][1]}\n"
        return "OK\n"


class HostCppRunner:
    """Compiles trusted C++ fixtures locally; production still uses TestRunner."""

    def __init__(self, source_code, sanitize=False):
        self.source_code = source_code
        self.sanitize = sanitize
        self._temporary = tempfile.TemporaryDirectory(prefix="grade8_5_6_")
        self.directory = self._temporary.name
        self.counter = 0
        self.program = self._compile(source_code, "student_program")

    def close(self):
        self._temporary.cleanup()

    def __call__(self, input_data, time_limit=1):
        return self._run(self.program, input_data, time_limit)

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
        compile_options=None,
    ):
        if probe_source is not None:
            raise AssertionError("C++ harness unexpectedly requested a Python probe")
        self.counter += 1
        binary = self._compile(
            source_code,
            f"hidden_{self.counter}",
            compile_options,
        )
        return self._run(binary, input_data, time_limit)

    def _compile(self, source_code, stem, compile_options=None):
        source_path = os.path.join(self.directory, stem + ".cpp")
        suffix = ".exe" if os.name == "nt" else ""
        binary_path = os.path.join(self.directory, stem + suffix)
        with open(source_path, "w", encoding="utf-8") as source_file:
            source_file.write(source_code)
        command = [shutil.which("g++"), "-std=c++17", "-O1"]
        if compile_options:
            command.extend(
                option for option in compile_options if option not in command
            )
        elif self.sanitize:
            command.extend(
                [
                    "-fsanitize=address,undefined",
                    "-fno-omit-frame-pointer",
                ]
            )
        command.extend([source_path, "-o", binary_path])
        result = subprocess.run(
            command,
            cwd=self.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if result.returncode:
            raise SolutionException(
                f"C++ fixture compilation failed with {result.returncode}:\n"
                f"{result.stderr}"
            )
        return binary_path

    def _run(self, binary_path, input_data, time_limit):
        environment = os.environ.copy()
        if self.sanitize:
            environment.update(
                {
                    "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1",
                    "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
                }
            )
        result = subprocess.run(
            [binary_path],
            cwd=self.directory,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(2, time_limit + 1),
            env=environment,
        )
        if result.returncode:
            raise SolutionException(
                f"C++ fixture execution failed with {result.returncode}:\n"
                f"{result.stderr}"
            )
        return result.stdout

    @staticmethod
    def sanitizers_available():
        compiler = shutil.which("g++")
        if not compiler:
            return False
        with tempfile.TemporaryDirectory(prefix="grade8_sanitizer_probe_") as directory:
            source = os.path.join(directory, "probe.cpp")
            binary = os.path.join(
                directory,
                "probe" + (".exe" if os.name == "nt" else ""),
            )
            with open(source, "w", encoding="utf-8") as source_file:
                source_file.write("int main() { return 0; }\n")
            try:
                compiled = subprocess.run(
                    [
                        compiler,
                        "-std=c++17",
                        "-fsanitize=address,undefined",
                        source,
                        "-o",
                        binary,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                if compiled.returncode:
                    return False
                executed = subprocess.run(
                    [binary],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                return executed.returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False


class Grade8ChaptersFiveSixTests(unittest.TestCase):
    def source_for(self, task_id):
        return PASSING_SOURCES.get(task_id, "// trusted fixture source\n")

    def test_exact_task_set_and_maxima(self):
        self.assertEqual(set(target.TASKS), set(TASK_MAXIMA))
        self.assertEqual(
            {task_id: maximum for task_id, (maximum, _) in target.TASKS.items()},
            TASK_MAXIMA,
        )
        self.assertEqual(len(target.TASKS), 16)
        self.assertTrue(all(maximum % 5 == 0 for maximum in TASK_MAXIMA.values()))

    def test_all_contract_fixtures_receive_full_credit(self):
        for task_id, expected_maximum in TASK_MAXIMA.items():
            with self.subTest(task_id=task_id):
                runner = ContractRunner(task_id)
                _, handler = target.TASKS[task_id]
                points, comment = handler(runner, self.source_for(task_id))
                self.assertEqual(points, expected_maximum, comment)
                self.assertIn(f"/{expected_maximum} баллов", comment)
                criteria = [line for line in comment.splitlines()[1:] if line]
                self.assertEqual(len(criteria), expected_maximum // 5)

    def test_a_broken_hidden_or_stdin_result_never_gets_full_credit(self):
        for task_id, expected_maximum in TASK_MAXIMA.items():
            with self.subTest(task_id=task_id):
                runner = ContractRunner(task_id, fail=True)
                _, handler = target.TASKS[task_id]
                points, _ = handler(runner, self.source_for(task_id))
                self.assertLess(points, expected_maximum)

    def test_class_and_function_tasks_use_hidden_cpp_harnesses(self):
        harness_tasks = set(TASK_MAXIMA) - {2699}
        for task_id in sorted(harness_tasks):
            with self.subTest(task_id=task_id):
                runner = ContractRunner(task_id)
                target.TASKS[task_id][1](runner, self.source_for(task_id))
                self.assertGreater(len(runner.harness_calls), 0)
                self.assertTrue(
                    all(key[0] == task_id for key, *_ in runner.harness_calls)
                )

    @unittest.skipUnless(shutil.which("g++"), "host g++ is not installed")
    def test_memory_heavy_reference_cpp_solutions_pass_real_harnesses(self):
        for task_id, source_code in CPP_REFERENCE_SOURCES.items():
            with self.subTest(task_id=task_id):
                runner = HostCppRunner(source_code)
                try:
                    points, comment = target.TASKS[task_id][1](runner, source_code)
                finally:
                    runner.close()
                self.assertEqual(points, TASK_MAXIMA[task_id], comment)

    @unittest.skipUnless(shutil.which("g++"), "host g++ is not installed")
    def test_memory_reference_solutions_pass_asan_and_ubsan_when_available(self):
        if not HostCppRunner.sanitizers_available():
            self.skipTest("host g++ has no working ASan/UBSan runtime")
        for task_id in (2691, 2693, 2698, 2703, 2706):
            source_code = CPP_REFERENCE_SOURCES[task_id]
            with self.subTest(task_id=task_id):
                runner = HostCppRunner(source_code, sanitize=True)
                try:
                    points, comment = target.TASKS[task_id][1](runner, source_code)
                finally:
                    runner.close()
                self.assertEqual(points, TASK_MAXIMA[task_id], comment)

    @unittest.skipUnless(shutil.which("g++"), "host g++ is not installed")
    def test_guarded_allocator_detects_heap_overflow_without_sanitizer_flags(self):
        source_code = target._ALLOCATION_TRACKER + r"""
int main() {
    __gp_begin_tracking();
    int* values = new int[1];
    values[1] = 42;
    delete[] values;
    std::printf("live=%lld\n", __gp_stop_tracking());
}
"""
        runner = HostCppRunner(source_code)
        try:
            self.assertEqual(runner("", 2), "live=-2\n")
        finally:
            runner.close()

    @unittest.skipUnless(shutil.which("g++"), "host g++ is not installed")
    def test_real_compile_contracts_reject_invalid_signature_and_unchecked_index(self):
        invalid_analyze = CPP_REFERENCE_SOURCES[2688].replace(
            "void analyze(int const* values",
            "void analyze(int* values",
        )
        runner = HostCppRunner(invalid_analyze)
        try:
            points, _ = target.TASKS[2688][1](runner, invalid_analyze)
        finally:
            runner.close()
        self.assertEqual(points, 0)

        unchecked_string = CPP_REFERENCE_SOURCES[2703].replace(
            """char& operator[](int index) {
        if (index < 0 || index >= stored_length) throw \"index\";
        return data[index];
    }""",
            """char& operator[](int index) {
        return data[index];
    }""",
        )
        self.assertNotEqual(unchecked_string, CPP_REFERENCE_SOURCES[2703])
        runner = HostCppRunner(unchecked_string)
        try:
            points, _ = target.TASKS[2703][1](runner, unchecked_string)
        finally:
            runner.close()
        self.assertEqual(points, 15)

    def test_large_inputs_are_present_without_tight_subsecond_limits(self):
        growth_runner = ContractRunner(2699)
        target.TASKS[2699][1](growth_runner, self.source_for(2699))
        growth_case = next(
            call for call in growth_runner.program_calls if call[0].strip() == "1000000000"
        )
        self.assertGreaterEqual(growth_case[1], 2)

        brackets_runner = ContractRunner(2706)
        target.TASKS[2706][1](brackets_runner, self.source_for(2706))
        long_cases = [call for call in brackets_runner.program_calls if len(call[0]) >= 200000]
        self.assertEqual(len(long_cases), 2)
        self.assertTrue(all(limit >= 3 for _, limit in long_cases))

    def test_restrictions_affect_their_own_five_point_criteria(self):
        restricted_sources = {
            2680: """
class Account {
public:
    int number, balance, overdraft;
    char owner[21];
    static int register_account(const char*, int) { return 1; }
};
void missing() { throw "missing"; }
int main() { try { missing(); } catch (...) { } }
""",
            2693: "int main() { return 0; }",
            2698: """
#include <vector>
class Vector { public: ~Vector() {} void push_back(int) {} int get_size() { return 0; } };
""",
            2702: """
template <typename T> class Vector { public: T operator[](int) { return T(); } };
ostream& operator<<(ostream& out, const Vector<int>&) { return out; }
""",
            2703: """
class String { private: std::string data; public: int length() const { return data.size(); } };
""",
            2706: "#include <stack>\nint main() { std::stack<char> value; }",
        }
        expected_points = {2680: 5, 2693: 0, 2698: 5, 2702: 0, 2703: 10, 2706: 5}
        for task_id, source in restricted_sources.items():
            with self.subTest(task_id=task_id):
                runner = ContractRunner(task_id)
                points, _ = target.TASKS[task_id][1](runner, source)
                self.assertEqual(points, expected_points[task_id])

    def test_allocation_wrappers_cannot_be_decoys_for_raw_new_and_delete(self):
        source = r"""
int taken = 0;
int freed = 0;
int* allocate_block(int value) { ++taken; return new int(value); }
void release_block(int* pointer) { delete pointer; ++freed; }
int main() {
    int* bypass = new int(7);
    delete bypass;
    allocate_block(1);
}
"""
        runner = ContractRunner(2693)
        points, _ = target.TASKS[2693][1](runner, source)
        self.assertEqual(points, 5)


if __name__ == "__main__":
    unittest.main()
