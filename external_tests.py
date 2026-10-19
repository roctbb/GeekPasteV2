"""External test results: explicit verdicts and counts, separate from raw diagnostics."""
from runner import BrainfuckExecutor, ExecutionContainer, ExecutionException, SolutionException


def check_external_tests(code, lang, config):
    tests = config.get('tests', [])
    if not isinstance(tests, list) or not tests or any(not isinstance(test, dict) for test in tests):
        raise ExecutionException('A non-empty list of tests is required.')

    result = {
        'status': 'success', 'verdict': 'wrong_answer', 'error_type': None,
        'points': 0, 'max_points': len(tests), 'tests_passed': 0, 'tests_total': len(tests),
        'visible_tests_passed': 0, 'visible_tests_total': sum(not test.get('hidden', False) for test in tests),
        'hidden_tests_passed': 0, 'hidden_tests_total': sum(bool(test.get('hidden', False)) for test in tests),
        'details': [],
    }
    for test in tests:
        container = None
        try:
            # Nothing written by a hidden test can survive into a public test.
            if lang == 'brainfuck':
                executor = BrainfuckExecutor(code)
            else:
                container = ExecutionContainer(lang, '', code, isolated=True)
                executor = container
            output = executor.run(test.get('input', ''),
                                  time_limit=test.get('time_limit', config.get('time_limit', 5))).strip()
            expected = str(test.get('expected', '')).strip()
            passed = output == expected
            result['details'].append({'input': test.get('input'), 'expected': expected, 'got': output, 'ok': passed})
            if passed:
                result['tests_passed'] += 1
                result['hidden_tests_passed' if test.get('hidden', False) else 'visible_tests_passed'] += 1
        except (SolutionException, ExecutionException) as error:
            error_type = 'internal_error' if isinstance(error, ExecutionException) else error.error_type
            result['details'].append({'input': test.get('input'), 'error': str(error),
                                      'error_type': error_type, 'ok': False})
            if result['error_type'] is None or error_type == 'internal_error':
                result['error_type'] = error_type
            # Compilation fails before any test executes. Infrastructure errors
            # also stop the job; neither should invent a one-test denominator.
            if error_type in {'compilation_error', 'internal_error'}:
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
