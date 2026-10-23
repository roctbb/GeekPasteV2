"""Run explicitly in a Docker-enabled runtime, without any application services."""
import json
import os
import subprocess
import time
import unittest
from unittest.mock import patch

from external_tests import check_external_tests
from runner import ExecutionContainer


DIGIT_PRESS = r'''
#include <bits/stdc++.h>
using namespace std;
int main() {
    long long a;
    cin >> a;
    int c = 0;
    while (a > 9) {
        int s = 1, n = a;
        while (n > 0) { s *= n % 10; n /= 10; }
        a = s;
        ++c;
    }
    cout << a << ' ' << c;
}
'''


@unittest.skipUnless(os.getenv('RUN_EXTERNAL_DOCKER_INTEGRATION') == '1',
                     'set RUN_EXTERNAL_DOCKER_INTEGRATION=1 in a Docker-enabled runtime')
class ExternalDockerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.container_ids = []
        parent = self

        class TrackedContainer(ExecutionContainer):
            compilations = 0

            def prepare(self):
                container_id = super().prepare()
                parent.container_ids.append(container_id)
                return container_id

            def _compile_cpp_harness(self, *args, **kwargs):
                type(self).compilations += 1
                return super()._compile_cpp_harness(*args, **kwargs)

        self.container_class = TrackedContainer
        self.factory_patch = patch('external_tests.ExecutionContainer', TrackedContainer)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)

    def tearDown(self):
        leaked = []
        for container_id in self.container_ids:
            inspection = subprocess.run(['docker', 'inspect', container_id], capture_output=True)
            if inspection.returncode == 0:
                leaked.append(container_id)
                subprocess.run(['docker', 'rm', '-f', container_id], capture_output=True, check=True)
        self.assertEqual(leaked, [], 'All builder and test containers must be removed.')

    def test_52_digit_press_cases_compile_only_once(self):
        config_path = os.getenv('EXTERNAL_TEST_BENCHMARK_CONFIG')
        if config_path:
            with open(config_path, encoding='utf-8') as file:
                config = json.load(file)
        else:
            def expected(n):
                count = 0
                while n > 9:
                    product = 1
                    for digit in str(n):
                        product *= int(digit)
                    n, count = product, count + 1
                return f'{n} {count}'
            inputs = [39, 1005, 0, 1, 9, 10, 999999999, 1000000000, 77, 679, 68889] + list(range(11, 52))
            config = {'time_limit_ms': 3000, 'tests': [
                {'input': f'{value}\n', 'expected': expected(value), 'hidden': index >= 2}
                for index, value in enumerate(inputs)]}
        self.assertEqual(len(config['tests']), 52)
        started = time.perf_counter()
        result = check_external_tests(DIGIT_PRESS, 'cpp', config)
        print(json.dumps({'benchmark': 'digit_press_52', 'seconds': round(time.perf_counter() - started, 3),
                          'compilations': self.container_class.compilations,
                          'passed': result['tests_passed'], 'total': result['tests_total']}), flush=True)
        self.assertEqual(result['verdict'], 'accepted', result)
        self.assertEqual(result['tests_passed'], 52)
        self.assertEqual(self.container_class.compilations, 1)

    def test_files_and_binary_cannot_leak_between_tests(self):
        source = r'''
#include <fstream>
#include <iostream>
#include <cstdio>
#include <sys/stat.h>
int main() {
    bool leaked = bool(std::ifstream("/tmp/previous_input"));
    std::string input; std::cin >> input;
    std::ofstream("/tmp/previous_input") << input;
    chmod("/code/program", 0777);
    FILE* file = fopen("/code/program", "wb");
    std::cout << (leaked ? "LEAK" : "CLEAN") << ' ' << (file ? "WRITABLE" : "READONLY");
    if (file) fclose(file);
}
'''
        result = check_external_tests(source, 'cpp', {'tests': [
            {'input': 'PUBLIC', 'expected': 'CLEAN READONLY'},
            {'input': 'SECRET', 'expected': 'CLEAN READONLY', 'hidden': True},
            {'input': 'PUBLIC_AFTER_SECRET', 'expected': 'CLEAN READONLY'},
        ]})
        self.assertEqual(result['verdict'], 'accepted', result)
        self.assertEqual(result['tests_passed'], 3)
        self.assertEqual(self.container_class.compilations, 1)

    def test_timeout_does_not_break_the_next_test(self):
        source = r'''
#include <iostream>
#include <string>
int main() { std::string s; std::cin >> s; if (s == "hang") for (;;) {} std::cout << s; }
'''
        result = check_external_tests(source, 'cpp', {'time_limit_ms': 3000, 'tests': [
            {'input': 'hang', 'expected': '', 'time_limit_ms': 150, 'hidden': True},
            {'input': 'ok', 'expected': 'ok'},
        ]})
        self.assertEqual(result['verdict'], 'time_limit_exceeded', result)
        self.assertEqual((result['tests_passed'], result['tests_total']), (1, 2))
        self.assertTrue(result['details'][1]['ok'])
        self.assertEqual(self.container_class.compilations, 1)

    def test_compilation_failure_preserves_total_and_cleans_builder(self):
        result = check_external_tests('not valid C++', 'cpp', {'tests': [
            {'input': '', 'expected': ''}, {'input': '', 'expected': '', 'hidden': True},
        ]})
        self.assertEqual(result['verdict'], 'compilation_error', result)
        self.assertEqual((result['tests_passed'], result['tests_total']), (0, 2))
        self.assertEqual(self.container_class.compilations, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
