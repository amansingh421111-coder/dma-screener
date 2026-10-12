// Browser and Python must work out the same automatic stop and target: run python3 qa/exits_parity.py, then node qa/exits_parity.js
const fs=require('fs');global.render=()=>{};global.EQ={charts:{}};
eval(fs.readFileSync(__dirname+'/../exits.js','utf8').replace(/^let EXI/m,'var EXI'));
const D=JSON.parse(fs.readFileSync('/tmp/exits_cases.json'));const N=a=>a.map(x=>x==null?NaN:x);
let bad=0;for(const k of D.cases){const m=k.m;const r=exLive(D.dates.slice(0,m),N(D.o.slice(0,m)),N(D.h.slice(0,m)),N(D.l.slice(0,m)),N(D.c.slice(0,m)),k.entry,k.ep,k.rule,k.final);
 const p=k.out;const d=(a,b)=>a==null&&b==null?0:a==null||b==null?1:Math.abs(a-b);
 if(d(r.sl,p.sl)>0.011||d(r.target,p.target)>0.011||r.days_left!==p.days_left||JSON.stringify(r.exit&&[r.exit.date,r.exit.why])!==JSON.stringify(p.exit&&[p.exit.date,p.exit.why])||(r.exit&&Math.abs(r.exit.price-p.exit.price)>0.011)){bad++;if(bad<5)console.log(k.rule.id,k.final,JSON.stringify(r),JSON.stringify(p))}}
console.log("cases",D.cases.length,"mismatch",bad);
