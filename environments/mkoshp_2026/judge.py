"""GeekPaste adapter. Private data stay outside copied task environments."""
from pathlib import Path
import gzip
import json
import subprocess
from .core import check

def perform(key,runner,source_code=None):
    from runner import SolutionException, ExecutionException
    container=runner.container
    if container.language!='python':
        return 0,'Для этой тренировки разрешён только Python.'
    # Scope limits to this submission; do not change other GeekPaste tasks.
    result=subprocess.run(['docker','update','--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','64',container.container_id],capture_output=True,text=True,timeout=10)
    if result.returncode:
        raise ExecutionException('Не удалось установить ограничения олимпиады.')
    cases=json.loads(gzip.decompress((Path(__file__).parent/'data'/f'{key}.json.gz').read_bytes()))
    limit=2 if key=='L2' else 1
    for i,case in enumerate(cases,1):
        try:
            output=runner(case['input'],time_limit=limit,capture_limit=8*1024*1024)
        except SolutionException as exc:
            # Do not include private input/answers in the student comment.
            text=str(exc)
            reason='Превышен лимит времени.' if 'timed out' in text else ('Превышен лимит вывода.' if 'Output limit' in text else 'Ошибка выполнения или превышен лимит памяти.')
            return 0,f'Тест {i}/{len(cases)}: {reason} Задача не решена: 0 из 5 баллов.'
        error=check(key,case['input'],output,case['answer'])
        if error:
            return 0,f'Тест {i}/{len(cases)}: {error} Задача не решена: 0 из 5 баллов.'
    return 5,f'Полное решение: пройдены все {len(cases)} тестов. 5 из 5 баллов.'
