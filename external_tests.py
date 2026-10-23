"""External test results: explicit verdicts and counts, separate from raw diagnostics."""
import math

from runner import BrainfuckExecutor, ExecutionContainer, ExecutionException, SolutionException


def _time_limit(test, config):
    for settings in (test, config):
        for key, multiplier in (('time_limit_ms', 0.001), ('time_limit', 1)):
            if key in settings:
                value = settings[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ExecutionException('Test time limit must be a positive finite number.')
                try:
                    seconds = float(value) * multiplier
                except OverflowError as error:
                    raise ExecutionException('Test time limit must be a positive finite number.') from error
                if not math.isfinite(seconds) or seconds <= 0:
                    raise ExecutionException('Test time limit must be a positive finite number.')
                return seconds
    return 5


def check_external_tests(code, lang, config):
    tests = config.get('tests', [])
    if not isinstance(tests, list) or not tests or any(not isinstance(test, dict) for test in tests):
        raise ExecutionException('A non-empty list of tests is required.')
    time_limits = [_time_limit(test, config) for test in tests]

    result = {
        'status': 'success', 'verdict': 'wrong_answer', 'error_type': None,
        'points': 0, 'max_points': len(tests), 'tests_passed': 0, 'tests_total': len(tests),
        'visible_tests_passed': 0, 'visible_tests_total': sum(not test.get('hidden', False) for test in tests),
        'hidden_tests_passed': 0, 'hidden_tests_total': sum(bool(test.get('hidden', False)) for test in tests),
        'details': [],
    }
    def record_error(test, error):
        error_type = 'internal_error' if isinstance(error, ExecutionException) else error.error_type
        result['details'].append({'input': test.get('input'), 'error': str(error),
                                  'error_type': error_type, 'ok': False})
        if result['error_type'] is None or error_type == 'internal_error':
            result['error_type'] = error_type
        return error_type

    try:
        program = ExecutionContainer.compile_cpp(code) if lang == 'cpp' else None
    except (SolutionException, ExecutionException) as error:
        record_error(tests[0], error)
    else:
        for test, time_limit in zip(tests, time_limits):
            container = None
            try:
                # Nothing written by a hidden test can survive into a public test.
                if lang == 'brainfuck':
                    executor = BrainfuckExecutor(code)
                else:
                    options = {'isolated': True}
                    if program is not None:
                        options['compiled_program'] = program
                    container = ExecutionContainer(lang, '', '' if program is not None else code, **options)
                    executor = container
                output = executor.run(test.get('input', ''), time_limit=time_limit).strip()
                expected = str(test.get('expected', '')).strip()
                passed = output == expected
                result['details'].append({'input': test.get('input'), 'expected': expected, 'got': output, 'ok': passed})
                if passed:
                    result['tests_passed'] += 1
                    result['hidden_tests_passed' if test.get('hidden', False) else 'visible_tests_passed'] += 1
            except (SolutionException, ExecutionException) as error:
                # Compilation and infrastructure errors stop the job; neither
                # should invent a one-test denominator. Execution errors do not.
                if record_error(test, error) in {'compilation_error', 'internal_error'}:
                    break
            finally:
                if container is not None:
                    container.cleanup()

    result['points'] = result['tests_passed']
    result['verdict'] = result['error_type'] or (
        'accepted' if result['tests_passed'] == result['tests_total'] else 'wrong_answer')
    result['status'] = 'error' if result['verdict'] == 'internal_error' else 'success'
    result['comment'] = f"{result['tests_passed']} из {result['tests_total']} тестов пройдено"
    return result
