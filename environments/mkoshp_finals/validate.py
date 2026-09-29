"""Input constraints, including tree connectivity and uniqueness promises."""
def validate(key,s):
    t=s.split()
    if key in ('2017F','2018B','2019D'):
        assert len(t)==2;n=int(t[0]);assert len(t[1])==n
        cap={'2017F':200000,'2018B':100000,'2019D':300000}[key]
        alphabet={'2017F':'rb?','2018B':'abcdefghijklmnopqrstuvwxyz','2019D':'()'}[key]
        assert 1<=n<=cap and all(c in alphabet for c in t[1]);return
    a=list(map(int,t));n=a[0]
    def between(xs,l,r):assert all(l<=x<=r for x in xs)
    def array(start,count,l,r):assert len(a)==start+count;between(a[start:],l,r)
    def tree(stride,cap):
        assert 1<=n<=cap and len(a)==1+(n-1)*stride
        parent=list(range(n))
        def root(v):
            while parent[v]!=v:parent[v]=parent[parent[v]];v=parent[v]
            return v
        for i in range(1,len(a),stride):
            u,v=a[i:i+2];between([u,v],1,n);ru,rv=root(u-1),root(v-1);assert ru!=rv;parent[ru]=rv
            if stride==4:between(a[i+2:i+4],-10000,10000)
    if key=='2017A':assert len(a)==4;between(a,1,100)
    elif key=='2017B':
        n,k,m=a[:3];assert 2<=k<=n<=100000 and 1<=m<=100000;array(3,n,0,10**9)
    elif key=='2017C':assert len(a)==1 and 1<=n<=10**9
    elif key=='2017D':
        assert len(a)==4;w,h,y,z=a;between([w,h],2,10**6);between([y,z],1,h-1)
    elif key=='2017E':assert 1<=n<=150000;array(1,n,0,10**8)
    elif key=='2017G':assert 1<=n<=300000;array(1,n,1,n);assert len(set(a[1:]))==n
    elif key=='2017H':
        from .core import words
        n,m,w=words(s);assert 2<=n<=100000 and 1<=m<=100000
        assert sum(map(len,w))<=100000 and len(a)==2+n+sum(map(len,w))
        for x in w:assert len(x)>=1;between(x,1,m)
    elif key=='2017I':tree(4,100000)
    elif key=='2018A':assert len(a)==3;between(a,1,100)
    elif key=='2018C':assert 1<=n<=100000 and 1<=a[1]<=10**9;array(2,n,1,100000);assert len(set(a[2:]))==n
    elif key=='2018D':assert 1<=n<=1000;array(1,n,0,2**30-1)
    elif key=='2018E':
        n,m,k=a[:3];between([n,m],1,10);assert 2<=k<=n*m;array(3,n*m,1,k);assert len(set(a[3:]))==k
    elif key=='2018F':tree(2,300000)
    elif key=='2018G':assert len(a)==2 and 0<=n<=100 and 1<=a[1]<=100
    elif key=='2018H':assert 2<=n<=200000;array(1,n,1,200000)
    elif key=='2018I':assert len(a)==4 and 1<=n<=100 and 1<=a[3]<=100;between(a[1:3],1,n)
    elif key=='2019A':
        assert 1<=n<=100000;m=a[n+1];assert 1<=m<=100000 and len(a)==n+m+2
        between(a[1:n+1],0,10**9);between(a[n+2:],0,10**9);assert len(set(a[1:n+1]))==n and len(set(a[n+2:]))==m
    elif key=='2019B':assert 1<=n<=200000;array(1,n,1,10**18);assert all(x<y for x,y in zip(a[1:],a[2:]))
    elif key=='2019C':assert len(a)==4 and a[0]<=a[3];between(a,1,30000)
    elif key=='2019E':assert 2<=n<=100000;array(1,2*n,0,1)
    elif key=='2019F':assert len(a)==2;between(a,1,100000)
    elif key=='2019G':assert 1<=n<=100000;array(1,n,1,10000)
    elif key=='2019H':
        m=a[1];assert 2<=n<=100000 and 0<=m<=1000000 and len(a)==2+3*m;seen=set()
        for i in range(2,len(a),3):
            u,v,w=a[i:i+3];between([u,v],1,n);assert u!=v and 1<=w<=10**9 and (u,v) not in seen;seen.add((u,v))
    else:raise ValueError(key)
