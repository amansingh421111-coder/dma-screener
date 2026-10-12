import json, numpy as np, pandas as pd, sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import exitrules as X
rng=np.random.default_rng(7); n=400
c=200*np.exp(np.cumsum(rng.normal(0.001,0.02,n))); o=c*np.exp(rng.normal(0,.01,n)); h=np.maximum(o,c)*np.exp(np.abs(rng.normal(0,.01,n))); l=np.minimum(o,c)*np.exp(-np.abs(rng.normal(0,.01,n)))
o[150]=np.nan; h[150]=np.nan; l[150]=np.nan; c[150]=np.nan
dates=[str(d.date()) for d in pd.bdate_range('2025-01-01',periods=n)]
cases=[]
rules=X.grid('swing')+X.grid('short')
for i,r in enumerate(rules):
    e=[60,120,145,300,380,395][i%6]; m=[n,n-3,n][i%3]; ep=round(float(c[e-1])*(0.98+0.04*((i*7)%10)/10),2)
    for fin in (True,False):
        L=X.live_levels(dates[:m],o[:m],h[:m],l[:m],c[:m],dates[e],ep,r,final=fin)
        cases.append(dict(rule=r,m=m,entry=dates[e],ep=ep,final=fin,out=L))
L=X.live_levels(dates,o,h,l,c,'2099-01-01',150.0,rules[20]); cases.append(dict(rule=rules[20],m=n,entry='2099-01-01',ep=150.0,final=True,out=L))
nan=lambda a:[None if x!=x else float(x) for x in a]
json.dump(dict(dates=dates,o=nan(o),h=nan(h),l=nan(l),c=nan(c),cases=cases),open('/tmp/exits_cases.json','w'))
print(len(cases))
