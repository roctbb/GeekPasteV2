"""Freeze and verify the 56 Python IO migrations from an immutable Git revision.

Run from the repository root. The original modules are read from Git even after
their task directories have been retired. No database or submissions are changed.
"""
import argparse
import ast
from decimal import Decimal, localcontext
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from io_tests import outputs_equal, score_results, validate_test_config

SOURCE_REF = '31762b7'
DESTINATION = ROOT / 'io_test_presets' / 'python_remaining'
LEGACY = {
    1952: 'lower_suffix', 1953: 'lower_suffix', 1957: 'lower_suffix',
    1981: 'strip_suffix', 1983: 'strip_suffix', 1984: 'strip_suffix', 1985: 'strip_suffix',
    1991: 'lower_exact', 1996: 'lower_suffix', 1997: 'lower_suffix', 1999: 'tokens',
}
GRADE7 = (2440, 2443, 2444, 2446, 2447, 2449)
QUALIFIER_KEYS = ('A', 'B', 'C', 'D', 'E', 'F1', 'F2', 'G1', 'G2', 'H1', 'H2', 'I1', 'I2', 'J1', 'J2', 'K', 'L1', 'L2')
EXCLUDED_QUALIFIERS = {'B', 'G1', 'G2', 'J1', 'J2'}
EXCLUDED_FINALS = {'2017B', '2017H', '2018B', '2018E', '2019D', '2019E'}


def source(path):
    return subprocess.check_output(['git', 'show', f'{SOURCE_REF}:{path}'], cwd=ROOT)


def module(path):
    name = '_io_migration_' + path.replace('/', '_').replace('.', '_')
    value = types.ModuleType(name)
    sys.modules[name] = value
    exec(compile(source(path), f'{SOURCE_REF}:{path}', 'exec'), value.__dict__)
    return value


def variants(expected):
    # Large outputs need only full-size boundary probes; small outputs also
    # cover numeric spelling, Unicode, trailing spaces and prompt handling.
    yield from (expected, expected + '\n', ' ' + expected + '\t', '', 'wrong',
                expected + ' wrong', 'prompt: ' + expected, expected.replace('\n', '\r\n'))
    if len(expected) < 4096:
        yield from (expected.swapcase(), expected.replace(' ', '\t'), expected + '\n\n',
                    expected.replace('\n', '\v'), expected.replace(' ', '\u00a0'),
                    expected.replace('1', '１'), expected + '\r', expected.replace('\n', '\r'))
        yield from ('0', '-0', '+0', '00', '1', '+01', '1.0', '1e0', '1_0', '١', '１',
                    '+1', '--1', '-+1', '1 ' * 3, '9' * 31, 'nan', 'inf', '1e-1000', '12:00',
                    'prompt 12:00', '112:00', 'prompt -1', 'prompt +-1')


def same_comparison(config, index, output, oracle):
    test = config['tests'][index]
    actual = outputs_equal(output, test['output'], test.get('comparison', config['comparison']))
    assert actual == oracle(output), (config['comparison'], index, repr(output[:120]))


def freeze(verify_only=False):
    index = {'format': 1, 'source_commit': subprocess.check_output(
        ['git', 'rev-parse', SOURCE_REF], cwd=ROOT, text=True).strip(), 'tasks': {}}
    counters = {'comparisons': 0, 'grading_scenarios': 0, 'tests': 0}
    if not verify_only:
        DESTINATION.mkdir(parents=True, exist_ok=True)

    def save(task_id, config, metadata, oracles, grade):
        config = validate_test_config(config, metadata['points'])
        for i, (test, oracle) in enumerate(zip(config['tests'], oracles)):
            for output in variants(metadata.get('answers', [])[i] if metadata.get('answers') else test['output']):
                same_comparison(config, i, output, oracle)
                counters['comparisons'] += 1
            if config['comparison'] == 'rational_absolute':
                numerator, denominator = map(int, test['output'].split('/'))
                with localcontext() as context:
                    context.prec = 80
                    center = Decimal(numerator) / denominator
                    for delta in ('0.000001', '-0.000001', '0.000000999999999999', '0.000001000000000001'):
                        same_comparison(config, i, str(center + Decimal(delta)), oracle)
                        counters['comparisons'] += 1
        n = len(config['tests'])
        flags = (itertools.product((False, True), repeat=n) if n <= 10 else
                 itertools.chain(([False] * n, [True] * n),
                                 ([j != i for j in range(n)] for i in range(n))))
        for results in flags:
            new = score_results(config, results, metadata['points'])[0]
            if task_id < 2871:
                new = max(1, new)
            assert new == max(1 if task_id < 2871 else 0, grade(results)), task_id
            counters['grading_scenarios'] += 1
        raw = json.dumps(config, ensure_ascii=False, separators=(',', ':')).encode()
        metadata = {key: value for key, value in metadata.items() if key != 'answers'}
        if task_id == 2914:
            # The production reference takes ~6.7s on the largest input.
            # Keep the original frozen suite intact; grant a 12s runtime limit.
            metadata['time_limit_override'] = 12
        metadata.update(language='python', count=n, sha256=hashlib.sha256(raw).hexdigest())
        index['tasks'][str(task_id)] = metadata
        counters['tests'] += n
        path = DESTINATION / f'{task_id}.json.gz'
        if verify_only:
            assert gzip.decompress(path.read_bytes()) == raw, path
        else:
            path.write_bytes(gzip.compress(raw, mtime=0))
        print(f'{task_id}: {n} tests, comparison and scoring verified', flush=True)

    for task_id, comparison in LEGACY.items():
        old = module(f'environments/task_{task_id}/tester.py')
        cases = old.scenarios
        def accepted(output, i, old=old, cases=cases):
            position = 0
            def runner(data):
                nonlocal position
                value = output if position == i else cases[position][1]
                position += 1
                return value
            return old.perform_tests(runner)[0] == 5
        def grade(results, old=old, cases=cases):
            answers = iter(expected if passed else 'wrong' for (_, expected), passed in zip(cases, results))
            return old.perform_tests(lambda data: next(answers))[0]
        save(task_id, dict(comparison=comparison, scoring='all_or_nothing', time_limit=1,
                           tests=[dict(input=a, output=b, is_public=False) for a, b in cases]),
             dict(points=5, source='legacy'),
             [lambda output, i=i: accepted(output, i) for i in range(len(cases))], grade)

    old = module('environments/grade7_chapter0_io.py')
    names = dict(suffix='normalized_suffix', exact_suffix='exact_suffix', clock='last_time', final_integer='last_integer')
    for task_id in GRADE7:
        spec = old.TASK_SPECS[task_id]
        assert not spec.coherent_families
        groups = [dict(id=f'g{i}', name=criterion.description, points=5)
                  for i, criterion in enumerate(spec.criteria)]
        assignments = {key: group['id'] for group, criterion in zip(groups, spec.criteria)
                       for key in criterion.case_groups[0]}
        assert len(assignments) == sum(len(criterion.case_groups[0]) for criterion in spec.criteria)
        tests = []
        for case in spec.cases:
            assert len(case.expected) == 1
            tests.append(dict(input=case.input_data, output='\n'.join(case.expected[0]), is_public=False,
                              group=assignments[case.key], comparison=names[case.matcher]))
        config = dict(comparison=names[spec.cases[0].matcher], scoring='groups', groups=groups,
                      tests=tests, time_limit=1, output_limit=100000)
        oracles = [lambda output, case=case: old._MATCHERS[case.matcher](output, case.expected) for case in spec.cases]
        def grade(results, spec=spec):
            return 5 * len(old._score_criteria(spec, dict(zip((case.key for case in spec.cases), results)))[0])
        metadata = dict(points=spec.max_points, source='grade7', source_task=task_id,
                        case_keys=[case.key for case in spec.cases], case_labels=[case.label for case in spec.cases])
        for destination in (task_id, task_id + 330):
            save(destination, config, metadata, oracles, grade)

    for family, keys in (('mkoshp_2026', dict(zip(QUALIFIER_KEYS, range(2871, 2889)))),
                         ('mkoshp_finals', {key: value['task_id'] for key, value in
                                           json.loads(source('environments/mkoshp_finals/config.json')).items()})):
        old = module(f'environments/{family}/core.py')
        times = json.loads(source('environments/mkoshp_finals/config.json')) if family == 'mkoshp_finals' else {}
        for key, task_id in keys.items():
            if key in (EXCLUDED_QUALIFIERS if family == 'mkoshp_2026' else EXCLUDED_FINALS):
                continue
            cases = json.loads(gzip.decompress(source(f'environments/{family}/data/{key}.json.gz')))
            comparison = ('keyword_integers_ascii30' if key == 'D' else 'word_integer_ascii30' if key == 'E'
                          else 'splitlines' if key in ('I1', 'I2') else 'rational_absolute' if key in ('L1', 'L2')
                          else 'integer_tokens_ascii30') if family == 'mkoshp_2026' else (
                              'word_lower' if key in ('2017D', '2019C') else 'tokens' if key in ('2018F', '2018G') else 'integer_tokens')
            tests = []
            for case in cases:
                expected = case['answer']
                if comparison == 'rational_absolute':
                    values = list(map(int, case['input'].split()))[1:]
                    numerator = denominator = 0
                    for left, right in zip(values[::2], values[1::2]):
                        count = right - left + 1
                        numerator += (left + right) * count // 2
                        denominator += count
                    expected = f'{numerator}/{denominator}'
                tests.append(dict(input=case['input'], output=expected, is_public=False))
            save(task_id, dict(comparison=comparison, scoring='all_or_nothing', tests=tests,
                               time_limit=(2 if key == 'L2' else 1) if not times else times[key]['time_limit'],
                               output_limit=8*1024*1024, memory_limit=256 if not times else 512,
                               process_limit=64, disable_swap=True),
                 dict(points=5, source=family, source_key=key, answers=[case['answer'] for case in cases]),
                 [lambda output, case=case, old=old, key=key: old.check(key, case['input'], output, case['answer']) is None for case in cases],
                 lambda results: 5 if all(results) else 0)
    assert len(index['tasks']) == 56 and counters['tests'] == 1335, counters
    index['verification'] = counters
    if verify_only:
        assert json.loads((DESTINATION / 'index.json').read_text()) == index
    else:
        (DESTINATION / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(counters))


def reference_programs(destination):
    """Export algorithms only, without any test inputs or reference answers."""
    programs = {}
    for task_id in LEGACY:
        text = source(f'environments/task_{task_id}/tester.py').decode()
        tree = ast.parse(text)
        if task_id in (1952, 1953, 1957):
            literal = next(node for node in reversed(tree.body)
                           if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                           and isinstance(node.value.value, str))
            programs[task_id] = ast.get_source_segment(text, literal)[3:-3]
        else:
            tree.body = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                         or isinstance(node, ast.FunctionDef) and node.name != 'perform_tests']
            programs[task_id] = ast.unparse(tree) + '\nimport sys\nprint(simulated_runner(sys.stdin.read()))\n'
    programs.update({
        2440: 'n=int(input("Минуты: ")); print(f"{n//60} ч. {n%60} мин.")',
        2443: 'a=sorted(int(input("Сторона: ")) for _ in range(3)); print("Треугольник не существует" if a[0]+a[1]<=a[2] else "Равносторонний треугольник" if a[0]==a[2] else "Равнобедренный треугольник" if a[0]==a[1] or a[1]==a[2] else "Разносторонний треугольник")',
        2444: 'h=int(input()); m=int(input()); d=int(input()); n=(h*60+m+d)%1440; print(f"{n//60:02}:{n%60:02}")',
        2446: 's="".join(c for c in input().lower() if c.isalnum()); print("Это палиндром" if s==s[::-1] else "Это не палиндром")',
        2447: 'from itertools import groupby\nprint(max((len(list(g)) for _,g in groupby(input())),default=0))',
        2449: 'from itertools import groupby\nprint("".join(c+str(len(list(g))) for c,g in groupby(input())))',
    })
    for task_id in GRADE7:
        programs[task_id + 330] = programs[task_id]
    metadata = json.loads((DESTINATION / 'index.json').read_text())['tasks']
    for task_id, data in metadata.items():
        if data['source'].startswith('mkoshp_'):
            programs[int(task_id)] = source(f"environments/{data['source']}/core.py").decode() + (
                f'\nimport sys\nprint(solve({data["source_key"]!r}, sys.stdin.read()), end="")\n')
    assert len(programs) == 56
    Path(destination).write_text(json.dumps(programs, ensure_ascii=False))
    print(f'Wrote {len(programs)} reference algorithms to {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--write-references')
    args = parser.parse_args()
    if args.write_references:
        reference_programs(args.write_references)
    else:
        freeze(args.verify_only)
