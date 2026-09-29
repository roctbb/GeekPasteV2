"""Private deterministic oracles and semantic checkers for MKOSHP league B."""
from collections import Counter, defaultdict, deque
from math import gcd
import heapq


def words(inp):
    it=iter(map(int,inp.split())); n=next(it); m=next(it)
    return n,m,[[next(it) for _ in range(next(it))] for _ in range(n)]


def beauty(s):
    balance=0; minimum=0; count=0
    for c in s:
        balance += 1 if c=='(' else -1
        if balance<minimum: minimum=balance;count=1
        elif balance==minimum: count+=1
    return count if balance==0 else 0


def brackets(s):
    n=len(s); b=[0]
    for c in s:b.append(b[-1]+(1 if c=='(' else -1))
    if b[-1]:return 0,1,1
    offset=min(range(n),key=b.__getitem__)
    s=s[offset:]+s[:offset];b=[0]
    for c in s:b.append(b[-1]+(1 if c=='(' else -1))
    zeros=[i for i,x in enumerate(b) if x==0]
    base=len(zeros)-1;ans=base;left=right=0
    for l,r in zip(zeros,zeros[1:]):
        ones=[i for i in range(l+1,r) if b[i]==1]
        if len(ones)>ans:ans=len(ones);left=l;right=r-1
        for ll,rr in zip(ones,ones[1:]):
            value=base+sum(b[i]==2 for i in range(ll+1,rr))
            if value>ans:ans=value;left=ll;right=rr-1
    return ans,(left+offset)%n+1,(right+offset)%n+1


def solve(key,inp):
    t=inp.split()
    if key in ('2017F','2018B','2019D'):
        n=int(t[0]);s=t[1]
    else:a=list(map(int,t))
    del t
    if key=='2017A':
        n,x,y,z=a;return str(0 if n==1 else min(x,y)+(n-2)*min(x,y,z))
    if key=='2017B':
        n,k,m=a[:3];groups=defaultdict(list)
        for v in a[3:]:
            groups[v%m].append(v)
            if len(groups[v%m])==k:return 'Yes\n'+' '.join(map(str,groups[v%m]))
        return 'No'
    if key=='2017C':
        n=a[0];v=[x for x in range(max(1,n-9*len(str(n))),n+1) if x+sum(map(int,str(x)))==n]
        return str(len(v))+'\n'+'\n'.join(map(str,v))
    if key=='2017D':
        w,h,y,z=a;return 'Yes' if y+z<=w and 2*h-y-z<=w else 'No'
    if key=='2017E':
        cnt=[0]*27
        for v in a[1:]:
            while v:
                bit=v&-v;cnt[bit.bit_length()-1]+=1;v-=bit
        return str(sum((c*(c-1)//2)<<i for i,c in enumerate(cnt)))
    if key=='2017F':
        nr=s.count('r');nb=s.count('b');ans=(nr==0)+(nb==0)
        for r in range(n-1,0,-2):
            if s[r] not in 'b?' or s[r-1] not in 'r?':break
            nr-=s[r-1]=='r';nb-=s[r]=='b'
            ans+=1 if r==1 else (nr==0)+(nb==0)
        return str(ans)
    if key=='2017G':
        n=a[0];on=bytearray(n);right=n-1;out=[1]
        for count,pos in enumerate(a[1:],1):
            on[pos-1]=1
            while right>=0 and on[right]:right-=1
            out.append(count-(n-right-1)+1)
        return ' '.join(map(str,out))
    if key=='2017H':
        n,m,ws=words(inp);edges=[[] for _ in range(m+1)];upper=bytearray(m+1);forbidden=set()
        for x,y in zip(ws,ws[1:]):
            for u,v in zip(x,y):
                if u!=v:
                    if u>v:upper[u]=1;forbidden.add(v)
                    else:edges[v].append(u)
                    break
            else:
                if len(x)>len(y):return 'No'
        for u in range(m,0,-1):
            if upper[u]:
                for v in edges[u]:upper[v]=1
        if any(upper[v] for v in forbidden):return 'No'
        result=[i for i in range(1,m+1) if upper[i]]
        return 'Yes\n'+str(len(result))+'\n'+' '.join(map(str,result))
    if key=='2017I':
        n=a[0];g=[[] for _ in range(n)]
        for i in range(1,len(a),4):
            u,v,p,q=a[i:i+4];u-=1;v-=1;g[u].append((v,p,q));g[v].append((u,q,p))
        parent=[-1]*n;order=[0];parent[0]=0;cost=[0]*n
        for u in order:
            for v,p,q in g[u]:
                if v!=parent[u]:parent[v]=u;cost[v]=p;order.append(v)
        path=bytearray(n);u=n-1;ans=0
        while u: path[u]=1;ans+=cost[u];u=parent[u]
        path[0]=1;dp=[0]*n
        for u in reversed(order):
            for v,p,q in g[u]:
                if parent[v]==u and v!=u and not path[v]:dp[u]+=max(0,dp[v]+p+q)
            if path[u]:ans+=dp[u]
        return str(ans)
    if key=='2018A':
        x,y,z=sorted(a);return str(max(0,z-x-y+1))
    if key=='2018B':return ''.join(sorted(s))
    if key=='2018C':
        n,k=a[:2];prev=0
        for x in sorted(a[2:]):
            missing=x-prev-1
            if k<=missing:return str(prev+k)
            k-=missing;prev=x
        return str(prev+k)
    if key=='2018D':return '\n'.join(str(1<<x.bit_count()) for x in a[1:])
    if key=='2018F':
        n=a[0];deg=[0]*n
        for v in a[1:]:deg[v-1]+=1
        return 'Billy' if n%2 or max(deg)<=2 else 'Ricardo'
    if key=='2018G':
        lead,p=a
        return next((str(x) for x in range(101) if (2*x-100)*(100-p)>=lead*p+100),'Impossible')
    if key=='2018H':
        n=a[0];a=a[1:];prev=[(i-1)%n for i in range(n)];nxt=[(i+1)%n for i in range(n)];out=[0]*n;remaining=n;round_=1
        todo=[i for i in range(n) if a[i]<a[prev[i]] and a[i]<a[nxt[i]]]
        while remaining>2 and todo:
            candidates=set()
            for i in todo:out[i]=round_
            for i in todo:
                l,r=prev[i],nxt[i];nxt[l]=r;prev[r]=l;candidates.add(l);candidates.add(r)
            remaining-=len(todo);round_+=1
            todo=[i for i in candidates if not out[i] and a[i]<a[prev[i]] and a[i]<a[nxt[i]]]
        return ' '.join(map(str,out))
    if key=='2018I':
        n,l,r,k=a;d=(r-l)%n+1
        for total in range(n,-1,-1):
            for before in range(d):
                for last in (0,1):
                    if not 0<=total-before-last<=n-d:continue
                    base=d-1+before
                    if k<=base:continue
                    rem=(k-base-1)%(n+total)+1
                    if rem<=1+last:return str(total)
        return '-1'
    if key=='2019A':
        n=a[0];x=a[1:n+1];m=a[n+1];y=a[n+2:];ex=sum(v%2==0 for v in x);ey=sum(v%2==0 for v in y)
        return str(ex*ey+(n-ex)*(m-ey))
    if key=='2019B':
        n=a[0];a=a[1:];g=0
        for i in range(n-1,-1,-1):
            x=a[i];g=gcd(g,x)
            if g!=x:continue
            seen=set();ok=True
            for y in a:
                if y==x:continue
                hi,lo=max(x,y),min(x,y);q,r=divmod(hi,lo)
                if r or q in seen:ok=False;break
                seen.add(q)
            if ok:return str(n-1)
        return str(n)
    if key=='2019C':
        x,y,d,l=a;return 'Yes' if x+d<l or d*d*(l-x)**2>((l-x)**2+y*y)*l*l else 'No'
    if key=='2019D':
        v,l,r=brackets(s);return f'{v}\n{l} {r}'
    if key=='2019E':
        n=a[0];k=sum(a[1:]);top=[0]*n;bottom=[0]*n
        for i in range(n-1):
            if k:top[i+1]=1;k-=1
            if k:bottom[i]=1;k-=1
        if k:top[0]=1;k-=1
        if k:bottom[-1]=1
        return ' '.join(map(str,top))+'\n'+' '.join(map(str,bottom))
    if key=='2019F':
        n,m=a;f=[1,1]
        for i in range(2,max(n,m)+1):f.append((f[-1]+f[-2])%1000000007)
        return str(2*(f[n]+f[m]-1)%1000000007)
    if key=='2019G':
        n=a[0];v=sorted(a[1:]);s=sum(v[:n//2]);t=sum(v[n//2:]);return str(s*s+t*t)
    if key=='2019H':
        n,m=a[:2];g=[[] for _ in range(n)];best=[-1]*n;best[0]=10**9+1
        for i in range(2,len(a),3):u,v,w=a[i:i+3];g[v-1].append((u-1,w))
        pq=[(-best[0],0)]
        while pq:
            neg,u=heapq.heappop(pq);c=-neg
            if c!=best[u]:continue
            for v,w in g[u]:
                value=min(c,w)
                if value>best[v]:best[v]=value;heapq.heappush(pq,(-value,v))
        return '\n'.join(map(str,best[1:]))
    raise ValueError(key)


def check(key,inp,out,answer):
    """None means accepted. Never expose private values in diagnostics."""
    try:
        t=out.split();ans=answer.split()
        if key=='2017B':
            if not t or t[0].lower()!=ans[0].lower():return 'Неверный ответ.'
            if t[0].lower()=='no':return None if len(t)==1 else 'Лишние данные.'
            n,k,m,*a=map(int,inp.split());b=list(map(int,t[1:]));c=Counter(a)
            if len(b)!=k or any(v>c[x] for x,v in Counter(b).items()) or len({x%m for x in b})!=1:return 'Некорректный набор чисел.'
            return None
        if key=='2017H':
            if not t or t[0].lower()!=ans[0].lower():return 'Неверный ответ.'
            if t[0].lower()=='no':return None if len(t)==1 else 'Лишние данные.'
            n,m,ws=words(inp);k=int(t[1]);u=list(map(int,t[2:]));upper=set(u)
            if k!=len(u) or len(upper)!=k or any(x<1 or x>m for x in upper):return 'Некорректный список букв.'
            converted=[[(0 if x in upper else 1,x) for x in w] for w in ws]
            return None if all(a<=b for a,b in zip(converted,converted[1:])) else 'Названия не упорядочены.'
        if key=='2018B':
            s=inp.split()[1]
            if len(t)!=1 or Counter(t[0])!=Counter(s):return 'Нужно переставить буквы исходной строки.'
            # Manacher counts all odd/even palindromes in linear time.
            z=t[0];n=len(z);count=0
            for even in (False,True):
                radius=[0]*n;l=0;r=-1
                for i in range(n):
                    k=(0 if even else 1) if i>r else min(radius[l+r-i+(1 if even else 0)],r-i+1)
                    while i-k-(1 if even else 0)>=0 and i+k<n and z[i-k-(1 if even else 0)]==z[i+k]:k+=1
                    radius[i]=k;count+=k
                    if i+k-1>r:l=i-k+(0 if even else 1);r=i+k-1
            return None if count==sum(v*(v+1)//2 for v in Counter(s).values()) else 'Количество палиндромов не максимально.'
        if key=='2019D':
            if len(t)!=3:return 'Ожидаются красота и две позиции.'
            value,l,r=map(int,t);s=list(inp.split()[1]);n=len(s)
            if not 1<=l<=n or not 1<=r<=n:return 'Позиции вне строки.'
            s[l-1],s[r-1]=s[r-1],s[l-1]
            return None if value==int(ans[0])==beauty(s) else 'Обмен не даёт оптимальный ответ.'
        if key=='2019E':
            a=list(map(int,inp.split()));n=a[0];b=list(map(int,t));k=sum(a[1:])
            if len(b)!=2*n or any(x not in (0,1) for x in b) or sum(b)!=k:return 'Некорректная расстановка.'
            top=0;bottom=sum(b[n:]);maximum=0
            for i in range(n):top+=b[i];maximum=max(maximum,top+bottom);bottom-=b[n+i]
            optimum=(k+1)//2 if k<=2*n-2 else n if k==2*n-1 else n+1
            return None if maximum==optimum else 'Расстановка не оптимальна.'
        if key in ('2017D','2019C'):return None if len(t)==1 and t[0].lower()==ans[0].lower() else 'Неверный ответ.'
        if key in ('2018F','2018G'):return None if t==ans else 'Неверный ответ.'
        return None if list(map(int,t))==list(map(int,ans)) else 'Неверный ответ.'
    except (ValueError,IndexError,OverflowError):return 'Некорректный формат ответа.'
