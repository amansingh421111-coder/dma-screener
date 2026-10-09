import sys;sys.path.insert(0,'.')
import numpy as np,pandas as pd,strategies as S
def mk(o,h,l,c):
    i=pd.date_range("2024-01-01",periods=len(o),freq="B");return pd.DataFrame(dict(Open=o,High=h,Low=l,Close=c,Volume=[1e6]*len(o)),index=i)
# signal on day0 -> entry day1 open 100
o=[100,100,100,100,100,100];h=[100,101,106,101,101,101];l=[100,99,99,99,99,99];c=[100]*6
df=mk(o,h,l,c);en=pd.Series([True]+[False]*5,index=df.index)
tr,op=S.simulate(df,en,5,5,10,0.004);print(tr,op)
assert tr[0]["why"]=="target" and abs(tr[0]["ret"]-(0.05-0.004))<1e-9
# both stop and target same day -> stop
h2=[100,106,100,100,100,100];l2=[100,94,100,100,100,100];df=mk(o,h2,l2,c);tr,_=S.simulate(df,en,5,5,10,0.004);assert tr[0]["why"]=="stop" and abs(tr[0]["ret"]+0.054)<1e-9,tr
# gap below stop at open on day 3
o3=[100,100,100,90,100,100];h3=[100,101,101,95,100,100];l3=[100,99,99,89,99,99];df=mk(o3,h3,l3,c);tr,_=S.simulate(df,en,5,10,10,0.004);assert tr[0]["why"]=="stop" and abs(tr[0]["ret"]-(-0.10-0.004))<1e-9,tr
# gap above target
o4=[100,100,100,112,100,100];h4=[100,101,101,113,100,100];l4=[100,99,99,111,99,99];df=mk(o4,h4,l4,c);tr,_=S.simulate(df,en,5,10,10,0.004);assert tr[0]["why"]=="target" and abs(tr[0]["ret"]-(0.12-0.004))<1e-9,tr
# time exit
df=mk(o,[100.5]*6,[99.5]*6,c);tr,_=S.simulate(df,en,5,10,3,0.004);assert tr[0]["why"]=="time" and tr[0]["days"]==3,tr
# open trade
tr,op=S.simulate(df,en,5,10,40,0.004);assert tr==[] and op["stop"]==95,(tr,op)
# stats / rate
trs=[dict(ret=0.1,exit="2025-01-0%d"%(i%9+1),entry="2025-0%d-01"%(i%9+1),days=5,why="target") for i in range(200)]+[dict(ret=-0.05,exit="2025-02-01",entry="2025-02-01",days=5,why="stop") for i in range(100)]
st=S.stats(trs,0.0);print(st);r=S.rate(st,dict(st,edge=0.01));print(r[:2]);assert abs(sum(x[1] for x in r[2])-r[0])<=0.25 or r[0]==5.0
# all strategies on random data
rng=np.random.default_rng(1);n=900;c=100*np.cumprod(1+rng.normal(0.0004,0.02,n));o=c*(1+rng.normal(0,0.005,n));h=np.maximum(o,c)*1.01;l=np.minimum(o,c)*0.99
df=mk(o,h,l,c);df["Volume"]=rng.integers(5e5,2e6,n)
for s in S.STRATS:
    en=s["fn"](df);assert en.dtype==bool and len(en)==n,s["id"]
    tr,op=S.simulate(df,en,5,10,S.MAX_HOLD[s["kind"]],0.004);print(s["id"],int(en.sum()),len(tr))
print("OK")
