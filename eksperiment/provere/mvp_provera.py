import re,sys,random,statistics as st
sys.stdout.reconfigure(encoding='utf-8')
mvp=open(r'C:\posao\diplomski\MVP-orkestrator.md',encoding='utf-8').read()
par=open(r'C:\posao\diplomski\skills\sloj-projekta\projekat-domen\references\parametri.md',encoding='utf-8').read()
def redovi(t):
    o={}
    for r in t.split('\n'):
        if r.startswith('|') and '---' not in r:
            c=[x.strip() for x in r.strip('|').split('|')]
            o.setdefault(c[0],[]).append(c[1:])
    return o
a,b=redovi(par),redovi(mvp)
br=lambda c:re.findall(r'[-+]?\d[\d.,]*',' '.join(c))
kljucevi=['1','2','3','4','5','6','7','8','Haiku','Sonnet','Opus','low','high','max','malo','taman','sve','sam','3 agenta','50 agenata']
pogresno=0
for k in kljucevi:
    for red in b.get(k,[]):
        if not any(set(br(red))<=set(br(p)) for p in a.get(k,[])):
            pogresno+=1; print('RAZLIKA',k,red,a.get(k))
    if k not in b: pogresno+=1; print('NEMA',k)
print('redova provereno',sum(len(b[k]) for k in kljucevi if k in b),'razlika',pogresno)
for f in ('skill','plugin','brain','projekat-','agent ','CLAUDE'):
    print('sadrzi %-9s'%f, len(re.findall(f,mvp)))
print('Budzet 24:', 'Budzet **24 $**' in mvp and 'Budzet **24 $**' in par, ' rok 150:', 'rok **150 min**' in mvp and 'rok **150 min**' in par)
# simulacija iz brojeva procitanih iz MVP-a
n=lambda s:float(s.replace('.','').replace(',','.')) if ',' in s or s.count('.')>1 or re.fullmatch(r'\d+\.\d{3}',s) else float(s)
tr=lambda s:[int(x) for x in s.split('/')]
m={k:(n(b[k][0][0]),n(b[k][0][1]),dict(zip((1,2,3),tr(b[k][0][2])))) for k in ('Haiku','Sonnet','Opus')}
i={k:(n(b[k][0][0]),n(b[k][0][1]),dict(zip((1,2,3),tr(b[k][0][2])))) for k in ('low','high','max')}
ko={k:(n(b[k][0][0]),dict(zip((1,2,3),tr(b[k][0][1])))) for k in ('malo','taman','sve')}
po={k:(n(b[k][0][0]),n(b[k][0][1]),int(b[k][0][2])) for k in ('sam','3 agenta','50 agenata')}
Bz={1:100000,2:300000,3:600000};Mz={1:5,2:15,3:30}
Z=[(int(b[str(i_)][0][1]),b[str(i_)][0][2]=='da') for i_ in range(1,9)]
def igra(s,f):
    p,c,mi=100,0,0;t_=[]
    for kr,(t,h) in enumerate(Z,1):
        a_,b_,c_,d_=f(t);A,N,K,P=m[a_],i[b_],ko[c_],po[d_]
        tk=Bz[t]*N[0]*K[0]*P[0];ce=tk/1e6*A[0];mn=Mz[t]*A[1]*N[1]*P[1]
        sh=max(5,min(99,A[2][t]+N[2][t]+K[1][t]+P[2]))
        ok=random.Random('%s:%s'%(s,kr)).randint(1,100)<=sh
        if ok or h:c+=ce;mi+=mn
        else:c+=2*ce;mi+=2*mn;p-=5
        if not ok and h:t_.append((ce,mn))
    for ce,mn in t_:c+=3*ce;mi+=mn;p-=25
    if c>24:p-=30
    if mi>150:p-=20
    return max(p,0)
S={'po tezini':lambda t:({1:'Haiku',2:'Sonnet',3:'Opus'}[t],'high','taman','3 agenta' if t==2 else 'sam'),
'sve Opus high':lambda t:('Opus','high','taman','sam'),'sve Haiku low malo':lambda t:('Haiku','low','malo','sam')}
v=[]
for k,f in S.items():
    x=st.mean(igra(s,f) for s in range(5000));v.append(x);print('%-20s %.1f'%(k,x))
print('POREDAK','OK' if v[0]>v[1]>v[2] else 'PAO')
