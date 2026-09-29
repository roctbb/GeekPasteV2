"""Private GeekPaste adapter, including a genuine streaming interactive judge."""
import gzip,json,os,selectors,subprocess,time
from pathlib import Path
from .core import check

def interactive_case(command,case,limit):
    """Judge stays outside the contestant sandbox; only colors cross stdin."""
    a=list(map(int,case['input'].split()));n,m,k=a[:3];colors=a[3:];N=n*m
    candidates=set(range(1,N+1));queries=0;buffer=b'';total=0
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
    selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ)
    deadline=time.monotonic()+limit
    def line():
        nonlocal buffer,total
        while b'\n' not in buffer:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not selector.select(remaining):raise TimeoutError()
            chunk=os.read(proc.stdout.fileno(),8192)
            if not chunk:raise ValueError('Программа завершилась до ответа.')
            total+=len(chunk)
            if total>1024*1024 or len(buffer)>16384:raise ValueError('Превышен лимит вывода.')
            buffer+=chunk
        value,buffer=buffer.split(b'\n',1)
        return value.decode('utf-8').strip()
    try:
        proc.stdin.write(case['input'].encode());proc.stdin.flush()
        while True:
            command_line=line()
            if command_line=='Ready!':
                parts=line().split()
                if len(parts)!=1:raise ValueError('После Ready! ожидается номер карты.')
                guess=int(parts[0])
                fixed=case.get('hidden_card')
                if fixed is not None:
                    if guess!=fixed:raise ValueError('Карта угадана неверно.')
                elif candidates!={guess}:raise ValueError('Ответ не определён однозначно.')
                proc.stdin.close()
                try:proc.wait(timeout=max(.05,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:raise TimeoutError()
                tail=buffer+proc.stdout.read(1024)
                if proc.returncode or tail.strip():raise ValueError('Ошибка завершения или лишние данные после ответа.')
                return None,queries
            if command_line!='?':raise ValueError('Ожидается ? или Ready!.')
            queries+=1
            if queries>99:
                proc.stdin.write(b'-1\n');proc.stdin.flush()
                raise ValueError('Превышен лимит 99 запросов.')
            grid=[]
            for _ in range(n):
                row=list(map(int,line().split()))
                if len(row)!=m:raise ValueError('Неверное число карт в строке.')
                grid.extend(row)
            if sorted(grid)!=list(range(1,N+1)):raise ValueError('Карты должны образовывать перестановку от 1 до n*m.')
            groups={}
            for v,c in zip(grid,colors):
                if v in candidates:groups.setdefault(c,set()).add(v)
            fixed=case.get('hidden_card')
            if fixed is not None:reply=colors[grid.index(fixed)]
            elif case.get('strategy')=='smallest':reply=min(groups,key=lambda c:(len(groups[c]),-c))
            else:reply=max(groups,key=lambda c:(len(groups[c]),c if queries%2 else -c))
            candidates=groups[reply]
            proc.stdin.write(f'{reply}\n'.encode());proc.stdin.flush()
    except TimeoutError:return 'Превышено время ожидания: проверьте алгоритм и flush после запроса.',queries
    except (ValueError,UnicodeError,BrokenPipeError) as exc:return str(exc) if str(exc) and not str(exc).startswith('invalid literal') else 'Неверный формат протокола.',queries
    finally:
        selector.close()
        if proc.poll() is None:proc.kill()
        proc.wait()
        for stream in (proc.stdin,proc.stdout):
            if stream and not stream.closed:stream.close()

def perform(key,runner,source_code=None):
    from runner import SolutionException,ExecutionException
    if runner.container.language!='python':return 0,'Для этой тренировки разрешён Python.'
    config=json.loads((Path(__file__).parent/'config.json').read_text())[key]
    r=subprocess.run(['docker','update','--memory','512m','--memory-swap','512m','--cpus','1','--pids-limit','64',runner.container.container_id],capture_output=True,timeout=10)
    if r.returncode:raise ExecutionException('Не удалось установить ограничения тренировки.')
    cases=json.loads(gzip.decompress((Path(__file__).parent/'data'/f'{key}.json.gz').read_bytes()))
    for index,case in enumerate(cases,1):
        if key=='2018E':
            command=['docker','exec','-i',runner.container.container_id,'python3','/code/script.py']
            error,_=interactive_case(command,case,config['time_limit'])
            if error:
                # A failed dialog may leave a blocked process; destroy this submission sandbox.
                subprocess.run(['docker','kill',runner.container.container_id],capture_output=True,timeout=10)
                return 0,f'Тест {index}/{len(cases)}: {error} 0 из 5 баллов.'
        else:
            try:output=runner(case['input'],time_limit=config['time_limit'],capture_limit=8*1024*1024)
            except SolutionException as exc:
                message=str(exc)
                error='Превышен лимит времени.' if 'timed out' in message else 'Ошибка выполнения или превышен лимит ресурсов.'
                return 0,f'Тест {index}/{len(cases)}: {error} 0 из 5 баллов.'
            error=check(key,case['input'],output,case['answer'])
            if error:return 0,f'Тест {index}/{len(cases)}: {error} 0 из 5 баллов.'
    return 5,f'Пройдены все {len(cases)} тестов. Полное решение: 5 из 5 баллов.'
