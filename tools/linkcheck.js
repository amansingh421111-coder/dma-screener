const fs=require("fs");const src=fs.readFileSync("insights.js","utf8");
const a=src.indexOf("const IN_COMMON"),b=src.indexOf("async function loadIns()");
const feed=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));const names=JSON.parse(fs.readFileSync("names.json","utf8"));
const uni={};fs.readFileSync("universe_nse.csv","utf8").split("\n").slice(1).forEach(ln=>{const m=ln.match(/^([^,]+),("([^"]*)"|[^,]*)/);if(m)uni[m[1].trim()]=(m[3]!=null?m[3]:m[2]).trim()});
let LIVE=feed;const f=new Function("LIVE",src.slice(a,b)+";return inMatcher;")(LIVE);
const seen=new Set(),st=[];for(const t of feed.themes)for(const s of t.stories)if(!seen.has(s.u)){seen.add(s.u);st.push(Object.assign({th:t.id},s))}
let t0=Date.now();const M=f(names,uni,st);const tb=Date.now()-t0;t0=Date.now();
const cnt={};let hit=0;const res=st.map(x=>{const h=M(x.t,x.who);if(h.length)hit++;h.forEach(s=>cnt[s]=(cnt[s]||0)+1);return[x.t,h]});
console.log(`::notice::stories=${st.length} linked=${hit} (${(100*hit/st.length).toFixed(1)}%) build=${tb}ms match=${Date.now()-t0}ms`);
console.log("::notice::top "+Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,40).map(e=>e.join(":")).join(" "));
const out=[];for(const [t,h] of res.slice(0,400))if(h.length)out.push(h.join("+")+" <= "+t.slice(0,90));
for(let i=0;i<out.length&&i<120;i+=6)console.log("::notice::"+out.slice(i,i+6).join(" || ").replace(/[\r\n]/g," "));
