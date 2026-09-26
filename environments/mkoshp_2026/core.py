"""Independent judge-side algorithms and semantic output checkers (stdlib only)."""
from decimal import Decimal, InvalidOperation, localcontext
from math import gcd, isqrt
import re

KEYS = ('A','B','C','D','E','F1','F2','G1','G2','H1','H2','I1','I2','J1','J2','K','L1','L2')

def boxes(n, a, b):
    g = gcd(a, b)
    if n % g:
        return None
    aa, bb, nn = a // g, b // g, n // g
    x = 0 if bb == 1 else nn * pow(aa, -1, bb) % bb
    y = (n - a*x) // b
    if y < 0:
        return None
    if b < a:
        t = y // aa
        x += t * bb
        y -= t * aa
    return x, y

def game(n):
    step = 0
    while True:
        step += 1
        p = 1
        for c in str(n):
            p *= int(c)
        n = p - 1
        if n <= 0:
            return 'LOSE', step
        if n >= 2 and all(n % d for d in range(2, isqrt(n)+1)):
            return 'WIN', step

def poster(initial, commands):
    h, w = len(initial), len(initial[0])
    rows, cols = [0]*h, [0]*w
    colors = ['']
    for t, (a,b,c) in enumerate(commands, 1):
        colors.append(c)
        rows.extend([t]*max(0,a-len(rows)))
        cols.extend([t]*max(0,b-len(cols)))
    return [''.join(initial[i][j] if max(rt,ct)==0 else colors[max(rt,ct)]
                    for j,ct in enumerate(cols)) for i,rt in enumerate(rows)]

def min_changes(a, s):
    if s < len(a):
        return None
    total = sum(a)
    if total <= s:
        return int(total < s)
    need, count = total-s, 0
    for v in sorted(a, reverse=True):
        need -= v-1
        count += 1
        if need <= 0:
            return count
    raise AssertionError('unreachable')

def solve(key, data):
    t = data.split()
    if key == 'A':
        return str((int(t[0])+6)//7)+'\n'
    if key == 'B':
        v = boxes(*map(int,t))
        return '-1\n' if v is None else f'{sum(v)}\n{v[0]} {v[1]}\n'
    if key == 'C':
        a = list(map(int,t[1:]))
        return str(max(a)+(max(a)-min(a))//(len(a)-1))+'\n'
    if key == 'D':
        n = int(t[0]); a = list(map(int,t[1:n+1])); b = list(map(int,t[n+1:2*n+1])); c = list(map(int,t[2*n+1:]))
        res = [z-x for x,z in zip(a,c)]
        return 'NO\n' if any(x not in (0,1) for x in res) or sum(res)!=sum(b) else 'YES\n'+' '.join(map(str,res))+'\n'
    if key == 'E':
        word, step = game(int(t[0])); return f'{word}\n{step}\n'
    if key[0] == 'F':
        n,s = map(int,t[:2]); a = list(map(int,t[2:])); total = sum(a)
        if not total: return '-1\n'
        cycles = (s-1)//total; rem = s-cycles*total
        pref = 0
        for i,x in enumerate(a,1):
            pref += x
            if pref >= rem: return str(cycles*n+i)+'\n'
    if key[0] == 'G':
        n,m,k = map(int,t)
        if k > ((n-1)//2)*((m-1)//2): return 'impossible\n'
        out = []
        for i in range(n):
            row = []
            for j in range(m):
                if i%2 and j%2 and i<n-1 and j<m-1 and k:
                    row.append('#'); k-=1
                else: row.append('+')
            out.append(''.join(row))
        return '\n'.join(out)+'\n'
    if key[0] == 'H':
        people = odd = 0; out = []
        for c in t[1]:
            if c == 'A': odd = people-odd+(people%2); people+=1
            elif c == 'B': people+=1
            elif people%2 == 0: odd = people-odd
            out.append(str(odd))
        return ' '.join(out)+'\n'
    if key[0] == 'I':
        h,w,q = map(int,t[:3]); initial=t[3:3+h]
        commands=[(int(t[i]),int(t[i+1]),t[i+2]) for i in range(3+h,len(t),3)]
        return '\n'.join(poster(initial,commands))+'\n'
    if key[0] == 'J':
        n,s=map(int,t[:2]); a=list(map(int,t[2:])); total=sum(a)
        if s<n: return '-1\n'
        if s>=total: a[0]+=s-total
        else:
            need=total-s
            for i in sorted(range(n),key=lambda i:a[i],reverse=True):
                delta=min(need,a[i]-1); a[i]-=delta; need-=delta
                if need==0: break
        return ' '.join(map(str,a))+'\n'
    if key == 'K':
        n=int(t[0]); x1,y1,x2,y2=map(int,t[1:5]); s1,s2=t[5:]
        # Follow the two remote-control trajectories; a meeting swaps robot labels.
        flip=False; move={'U':(0,1),'D':(0,-1),'L':(-1,0),'R':(1,0)}
        for a,b in zip(s1,s2):
            dx,dy=move[a]; x1+=dx; y1+=dy
            dx,dy=move[b]; x2+=dx; y2+=dy
            if (x1,y1)==(x2,y2): flip=not flip
        if flip: x1,y1,x2,y2=x2,y2,x1,y1
        return f'{x1} {y1}\n{x2} {y2}\n'
    if key[0] == 'L':
        a=list(map(int,t[1:])); num=den=0
        for l,r in zip(a[::2],a[1::2]):
            count=r-l+1; num+=(l+r)*count//2; den+=count
        with localcontext() as ctx:
            ctx.prec=60
            return str(Decimal(num)/Decimal(den))+'\n'
    raise ValueError(key)

def integers(tokens):
    if any(len(x)>30 or not re.fullmatch(r'[+-]?[0-9]+',x) for x in tokens):
        raise ValueError('Ожидались целые числа.')
    return list(map(int,tokens))

def check(key, data, output, expected):
    """Returns None for acceptance, a short diagnostic otherwise."""
    try:
        ts=output.split(); src=data.split()
        if key=='B':
            n,a,b=map(int,src); opt=boxes(n,a,b)
            if opt is None: return None if ts==['-1'] else 'Упаковка невозможна: ожидалось -1.'
            if len(ts)!=3: return 'Нужны три числа: k, x, y.'
            k,x,y=integers(ts)
            if min(x,y)<0 or a*x+b*y!=n or x+y!=k: return 'Коробки не дают ровно n сувениров или k не равно x + y.'
            return None if k==sum(opt) else 'Количество коробок не минимально.'
        if key[0]=='G':
            n,m,k=map(int,src); possible=k<=((n-1)//2)*((m-1)//2)
            if not possible: return None if ts==['impossible'] else 'Такой дом построить невозможно.'
            lines=output.strip('\r\n').splitlines()
            if len(lines)!=n or any(len(row)!=m for row in lines): return 'Неверные размеры таблицы.'
            if any(c not in '+#' for row in lines for c in row): return 'Допустимы только + и #, без пробелов внутри строк.'
            if sum(row.count('#') for row in lines)!=k: return 'Неверное число окон.'
            for i,row in enumerate(lines):
                for j,c in enumerate(row):
                    if c!='#': continue
                    if i in (0,n-1) or j in (0,m-1): return 'Окно находится на границе.'
                    if any(lines[i+di][j+dj]=='#' for di,dj in ((0,1),(1,-1),(1,0),(1,1))): return 'Окна соприкасаются стороной или углом.'
            return None
        if key[0]=='J':
            n,s=map(int,src[:2]); a=list(map(int,src[2:])); opt=min_changes(a,s)
            if opt is None: return None if ts==['-1'] else 'Сумма натуральных чисел не может быть меньше n.'
            if len(ts)!=n: return 'Неверное количество элементов.'
            b=integers(ts)
            if min(b)<1 or sum(b)!=s: return 'Элементы должны быть натуральными, а сумма равна S.'
            return None if sum(x!=y for x,y in zip(a,b))==opt else 'Количество изменённых позиций не минимально.'
        if key[0]=='L':
            if len(ts)!=1 or len(ts[0])>100: return 'Ожидалось одно вещественное число.'
            if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',ts[0]): return 'Неверный формат числа.'
            with localcontext() as ctx:
                ctx.prec=80
                v=Decimal(ts[0]); x=list(map(int,src[1:])); num=den=0
                for l,r in zip(x[::2],x[1::2]):
                    cnt=r-l+1; num+=(l+r)*cnt//2; den+=cnt
                return None if v.is_finite() and abs(v*den-num)<=Decimal('0.000001')*den else 'Абсолютная погрешность больше 10^-6.'
        if key=='D':
            es=expected.split()
            if not ts or ts[0].upper()!=es[0]: return 'Неверный ответ YES/NO.'
            return None if integers(ts[1:])==integers(es[1:]) else 'Неверный восстановленный ряд.'
        if key[0]=='I':
            return None if output.splitlines()==expected.splitlines() else 'Итоговый плакат неверен.'
        if key=='E':
            return None if len(ts)==2 and ts[0]==expected.split()[0] and integers(ts[1:])==integers(expected.split()[1:]) else 'Неверный исход игры или номер хода.'
        return None if integers(ts)==integers(expected.split()) else 'Неверный ответ.'
    except (ValueError,InvalidOperation,OverflowError):
        return 'Некорректный формат ответа.'

def validate(key,data):
    t=data.split(); vals=lambda x:list(map(int,x))
    if key=='A': assert len(t)==1 and 1<=int(t[0])<=10**6
    elif key=='B': assert len(t)==3 and all(1<=v<=10**6 for v in vals(t))
    elif key=='C':
        n=int(t[0]); a=sorted(vals(t[1:])); assert 2<=n<=1000 and len(a)==n and 1<=a[0]<a[-1]<=10**9
        assert len(set(a[i+1]-a[i] for i in range(n-1)))==1 and a[1]>a[0]
    elif key=='D':
        n=int(t[0]); assert 1<=n<=200000 and len(t)==1+3*n
        assert set(vals(t[1:1+2*n]))<={0,1} and set(vals(t[1+2*n:]))<={0,1,2}
    elif key=='E': assert len(t)==1 and 1<=int(t[0])<=10**6
    elif key[0]=='F':
        n,s=vals(t[:2]); N,S,V=(100,1000,100) if key=='F1' else (100000,10**12,10**9)
        assert 1<=n<=N and 1<=s<=S and len(t)==n+2 and all(0<=v<=V for v in vals(t[2:]))
    elif key[0]=='G':
        n,m,k=vals(t); assert min(n,m)>=1 and k>=0
        assert (max(n,m)<=30 and k<=10) if key=='G1' else (n*m<=100000 and k<=10**9)
    elif key[0]=='H':
        n=int(t[0]); assert len(t)==2 and len(t[1])==n and 1<=n<=(50 if key=='H1' else 200000) and set(t[1])<=set('ABC')
    elif key[0]=='I':
        h,w,q=vals(t[:3]); easy=key=='I1'; assert 1<=h<=(100 if easy else 1000) and 1<=w<=(100 if easy else 1000) and 1<=q<=(100 if easy else 200000)
        assert len(t)==3+h+q*3 and all(len(row)==w and set(row)<=set('abcdefghijklmnopqrstuvwxyz') for row in t[3:3+h])
        for i in range(3+h,len(t),3):
            a,b=vals(t[i:i+2]); c=t[i+2]; assert 1<=a<=(100 if easy else 200000) and 1<=b<=(100 if easy else 200000) and len(c)==1 and 'a'<=c<='z'
            h,w=max(h,a),max(w,b); assert h*w<=(10000 if easy else 10**6)
    elif key[0]=='J':
        n,s=vals(t[:2]); assert 1<=n<=(1000 if key=='J1' else 100000) and 1<=s<=10**9 and len(t)==n+2 and all(1<=v<=10**9 for v in vals(t[2:]))
    elif key=='K':
        n=int(t[0]); p=vals(t[1:5]); assert len(t)==7 and 1<=n<=200000 and all(abs(v)<=10**9 for v in p) and p[:2]!=p[2:]
        assert all(len(s)==n and set(s)<=set('UDLR') for s in t[5:])
    elif key[0]=='L':
        n=int(t[0]); a=vals(t[1:]); assert 1<=n<=(100 if key=='L1' else 100000) and len(a)==2*n and all(x<y for x,y in zip(a,a[1:]))
        assert (0<=a[0] and a[-1]<=1000) if key=='L1' else (-10**9<=a[0] and a[-1]<=10**9)
    else: raise ValueError(key)
