import random
Z=[(1,0),(1,0),(1,0),(2,0),(3,1),(3,1),(2,0),(3,1)]
BT={1:100000,2:300000,3:600000}; BM={1:5,2:15,3:30}
M={'H':(0.18,0.5,{1:90,2:65,3:30}),'S':(3.6,0.8,{1:95,2:85,3:60}),'O':(7.2,1.0,{1:97,2:92,3:85})}
N={'low':(0.33,0.6,{1:0,2:-15,3:-25}),'high':(1,1,{1:0,2:0,3:0}),'max':(2.9,1.6,{1:1,2:1,3:1})}
K={'malo':(0.6,{1:0,2:-15,3:-25}),'taman':(1,{1:0,2:0,3:0}),'sve':(1.8,{1:-10,2:-10,3:-10})}
P={'sam':(1,1,0),'3':(1.3,0.5,0),'50':(3.6,2.1,-10)}
def igra(seme,izbor):
    poeni=100;cena=0;min_=0;tihi=[]
    for k,(t,tih) in enumerate(Z,1):
        m,n,c,p=izbor(t,tih)
        tok=BT[t]*N[n][0]*K[c][0]*P[p][0]; c_=tok/1e6*M[m][0]; mi=BM[t]*M[m][1]*N[n][1]*P[p][1]
        s=max(5,min(99,M[m][2][t]+N[n][2][t]+K[c][1][t]+P[p][2]))
        ok=random.Random("%s:%s"%(seme,k)).randint(1,100)<=s
        if not ok and not tih: c_*=2;mi*=2;poeni-=5
        if not ok and tih: tihi.append((c_,mi))
        cena+=c_;min_+=mi
    for c_,mi in tihi: cena+=3*c_;min_+=mi;poeni-=25
    if cena>24: poeni-=30
    if min_>150: poeni-=20
    return max(0,poeni)
S={'po tezini':lambda t,h:({1:'H',2:'S',3:'O'}[t],'high','taman','3' if t==2 else 'sam'),
 'opus tihi':lambda t,h:('O' if h else 'H','high','taman','sam'),
 'sve opus high':lambda t,h:('O','high','taman','sam'),
 'sve sonnet high':lambda t,h:('S','high','taman','sam'),
 'obrnuto':lambda t,h:({1:'O',2:'S',3:'H'}[t],'high','taman','sam'),
 'opus max sve':lambda t,h:('O','max','sve','sam'),
 'haiku low malo':lambda t,h:('H','low','malo','sam'),
 'haiku 50':lambda t,h:('H','high','taman','50')}
for n,f in S.items(): print(n, round(sum(igra(i,f) for i in range(5000))/5000,1))
