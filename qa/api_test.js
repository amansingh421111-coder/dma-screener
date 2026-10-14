process.env.KV_REST_API_URL="https://r";process.env.KV_REST_API_TOKEN="t";process.env.Bot_token="BT";process.env.bot_username="my_bot";process.env.Youtube_Api_Key="K";
const store=new Map(),sets=new Map(),tg=[];
const ytc=[];
global.fetch=async(url,o)=>{
 if(String(url).startsWith("https://www.googleapis.com/youtube/v3/")){const u=new URL(url);const p=u.pathname.split("/").pop();ytc.push([p,Object.fromEntries(u.searchParams)]);
  const ok=b=>({ok:true,status:200,json:async()=>b});
  if(p==="channels")return ok({items:[{id:"UC"+"a".repeat(22),snippet:{title:"Chan"},contentDetails:{relatedPlaylists:{uploads:"UU"+"a".repeat(22)}},statistics:{videoCount:"2"}}]});
  if(p==="playlistItems")return ok({items:[{contentDetails:{videoId:"abcdefghijk"}},{contentDetails:{videoId:"bcdefghijkl"}}],nextPageToken:"NP"});
  if(p==="videos")return ok({items:u.searchParams.get("id").split(",").map((id,i)=>({id,snippet:{title:"V"+i,publishedAt:"2026-01-0"+(i+1)+"T00:00:00Z",description:"d"},contentDetails:{duration:"PT1H2M3S"},statistics:{viewCount:"10"}}))});}

 if(String(url).startsWith("https://news.google.com/")){global.newsCalls=(global.newsCalls||0)+1;return{ok:true,status:200,text:async()=>'<rss><channel><item><title><![CDATA[Reliance Q2 results: profit up 9%; board okays bonus - Mint]]></title><link>https://news.google.com/a</link><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate><source url="https://m">Mint</source></item><item><title>Old &amp; news</title><link>https://x/b</link><pubDate>Thu, 08 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'}}
 if(String(url).startsWith("https://query1.finance.yahoo.com/")){return{json:async()=>({chart:{result:[{meta:{longName:"Reliance Industries"},timestamp:[1760000000,1760086400,1760172800],indicators:{quote:[{open:[100,101,null],high:[102,103,104],low:[99,100,101],close:[101,102,null],volume:[5,6,7]}],adjclose:[{adjclose:[50.5,51,null]}]}}]}})}}
 if(url.startsWith("https://api.telegram.org")){tg.push(JSON.parse(o.body));return{json:async()=>({ok:true})}}
 const c=JSON.parse(o.body);let r=null;const k=c[1];
 switch(c[0]){case"GET":r=store.has(k)?store.get(k):null;break;
  case"SET":if(c.includes("NX")&&store.has(k)){r=null}else{store.set(k,c[2]);r="OK"}break;
  case"DEL":store.delete(k);break;case"INCR":{const n=(+store.get(k)||0)+1;store.set(k,String(n));r=n}break;case"EXPIRE":break;
  case"SADD":(sets.get(k)||sets.set(k,new Set()).get(k)).add(c[2]);break;case"SREM":sets.get(k)&&sets.get(k).delete(c[2]);break;case"SMEMBERS":r=[...(sets.get(k)||[])];break}
 return{json:async()=>({result:r})}};
const h=require(process.argv[2]);
// tiny browser: keeps cookies per "device"
const dev=()=>({cookie:""});
const SEC=require("crypto").createHash("sha256").update("tg-webhook:BT").digest("hex").slice(0,48),TGH={"x-telegram-bot-api-secret-token":SEC};
const call=async(d,a,{method="POST",body={},hdr={"x-dma":"1"},ip="1.1.1.1"}={})=>{let out={headers:{}};
 const res={setHeader(k,v){out.headers[k]=v},status(c){out.code=c;return this},json(b){out.body=b;return this}};
 await h({query:{a},headers:{...hdr,cookie:d.cookie,"x-forwarded-for":ip,host:"x.test"},body,method},res);
 const sc=out.headers["Set-Cookie"];if(sc){const v=sc.split(";")[0].split("=")[1];d.cookie=v?"dma_s="+v:""}return out};
let f=0;const chk=(n,g,e)=>{const ok=JSON.stringify(g)===JSON.stringify(e);if(!ok)f++;console.log(ok?"PASS":"FAIL",n,ok?"":JSON.stringify(g)+" expected "+JSON.stringify(e))};
(async()=>{
 const A=dev(),B=dev(),C=dev();
 chk("positions need login",(await call(A,"positions",{method:"GET"})).code,401);
 chk("me when logged out",(await call(A,"me",{method:"GET"})).code,401);
 chk("POST without x-dma header rejected",(await call(A,"register",{hdr:{}, body:{username:"aman",password:"password1"}})).code,400);
 chk("short password",(await call(A,"register",{body:{username:"aman",password:"short"}})).code,400);
 chk("bad username",(await call(A,"register",{body:{username:"a b",password:"password1"}})).code,400);

 // ---- legacy data (created before accounts existed)
 const legacy="a1b2c3d4e5f60718293a4b5c6d7e8f90";
 store.set("pos:"+legacy,JSON.stringify({positions:[{symbol:"UTLSOLAR",exchange:"NSE",qty:10,buy:450,sl:432,target:495}],ts:5}));
 store.set("chat:"+legacy,"555");store.set("uid:555",legacy);
 const r1=await call(A,"register",{body:{username:"Aman",password:"password1",legacy_uid:legacy}});
 chk("register claims legacy data",[r1.code,r1.body],[200,{username:"aman",claimed:true}]);
 chk("cookie is HttpOnly+Secure+Strict",/HttpOnly/.test(r1.headers["Set-Cookie"])&&/Secure/.test(r1.headers["Set-Cookie"])&&/SameSite=Strict/.test(r1.headers["Set-Cookie"]),true);
 chk("me after register",(await call(A,"me",{method:"GET"})).body,{username:"aman"});
 const p=(await call(A,"positions",{method:"GET"})).body;chk("legacy positions kept",[p.positions.length,p.positions[0].symbol],[1,"UTLSOLAR"]);
 chk("legacy Telegram link kept",(await call(A,"status",{method:"GET"})).body,{connected:true});
 chk("username taken (case-insens.)",(await call(B,"register",{body:{username:"AMAN",password:"password1"}})).code,409);
 // someone else cannot claim the same legacy key
 const r2=await call(B,"register",{body:{username:"mallory",password:"password1",legacy_uid:legacy}});
 chk("legacy key cannot be claimed twice",r2.body.claimed,false);
 chk("mallory sees nothing of aman",(await call(B,"positions",{method:"GET"})).body.positions.length,0);
 chk("mallory not connected",(await call(B,"status",{method:"GET"})).body,{connected:false});
 // separate accounts keep separate positions
 await call(B,"positions",{body:{ts:9,positions:[{symbol:"tcs",exchange:"NSE",qty:1,buy:100,evil:"x"}]}});
 chk("B saved own",(await call(B,"positions",{method:"GET"})).body.positions.map(x=>x.symbol),["TCS"]);
 chk("A unchanged",(await call(A,"positions",{method:"GET"})).body.positions.map(x=>x.symbol),["UTLSOLAR"]);

 { // holdings model: one holding per share, average-cost
  await call(B,"positions",{body:{ts:20,positions:[
   {id:"h1",symbol:"acesoft",exchange:"NSE",sl:95,target:120,txns:[{type:"buy",date:"2026-09-01",qty:10,price:100},{type:"buy",date:"2026-09-10",qty:10,price:120},{type:"sell",date:"2026-10-01",qty:5,price:140}]},
   {symbol:"ACESOFT",exchange:"NSE",sl:98,target:110,txns:[{type:"buy",date:"2026-09-20",qty:5,price:130}]},
   {symbol:"OLD",exchange:"BSE",qty:10,buy:50,date:"2026-01-01",sellDate:"2026-02-01",sellPrice:60},
   {symbol:"BAD",exchange:"NSE",txns:[{type:"sell",date:"2026-01-01",qty:5,price:10}]}]}});
  const hp=(await call(B,"positions",{method:"GET"})).body.positions,a=hp.find(x=>x.symbol==="ACESOFT"),o=hp.find(x=>x.symbol==="OLD");
  chk("same share merged into one holding",hp.filter(x=>x.symbol==="ACESOFT").length,1);
  chk("average cost and qty",[a.qty,+a.avg.toFixed(2),+a.realised.toFixed(2)],[20,114,130]);
  chk("highest stop, nearest target",[a.sl,a.target],[98,110]);
  chk("legacy single lot converted to buy+sell",[o.txns.length,o.qty,o.realised],[2,0,100]);
  chk("oversell-only holding dropped or flat",hp.some(x=>x.symbol==="BAD"&&x.qty>0),false);
 }

 { // watchlist, settings, journal fields
  await call(B,"positions",{body:{ts:30,positions:[{symbol:"jrn",exchange:"NSE",txns:[{type:"buy",date:"2026-09-01",qty:5,price:10,note:"x".repeat(300),rule:"yes"},{type:"sell",date:"2026-09-05",qty:5,price:12,rule:"bogus"}]}],
   watchlist:[{id:"w1",symbol:"tcs",exchange:"NSE",alertBuy:true,above:4000,note:"n"},{symbol:"tcs",exchange:"NSE"},{symbol:"<script>"}],settings:{capital:100000,riskPct:1,evil:5,sttPct:-1}}});
  const d=(await call(B,"positions",{method:"GET"})).body,t=d.positions.find(x=>x.symbol==="JRN").txns;
  chk("journal note trimmed and rule whitelisted",[t[0].note.length,t[0].rule,t[1].rule],[200,"yes",""]);
  chk("watchlist cleaned and deduplicated",d.watchlist.map(x=>x.symbol),["TCS","SCRIPT"]);
  chk("settings whitelisted",d.settings,{capital:100000,riskPct:1});
  await call(B,"positions",{body:{ts:31,positions:d.positions}});
  const d2=(await call(B,"positions",{method:"GET"})).body;
  chk("older client that omits watchlist/settings does not erase them",[d2.watchlist.length,d2.settings.capital],[2,100000]);
 }
 // login / logout
 chk("wrong password",(await call(C,"login",{body:{username:"aman",password:"nope-nope"}})).code,401);
 chk("unknown user same message",(await call(C,"login",{body:{username:"ghost",password:"nope-nope"}})).body.error,"Wrong username or password.");
 chk("login ok",(await call(C,"login",{body:{username:"AMAN",password:"password1"}})).body,{username:"aman"});
 chk("C sees aman's data",(await call(C,"positions",{method:"GET"})).body.positions[0].symbol,"UTLSOLAR");
 await call(C,"logout");chk("after logout",(await call(C,"me",{method:"GET"})).code,401);
 chk("forged cookie rejected",(await call({cookie:"dma_s="+"ab".repeat(32)},"me",{method:"GET"})).code,401);
 // lockout after 8 wrong attempts (new IP so only the per-account limiter triggers)
 let last;for(let i=0;i<9;i++)last=await call(C,"login",{ip:"9.9.9."+i,body:{username:"mallory",password:"wrong-wrong"}});
 chk("account lockout",last.code,429);
 chk("lockout blocks even right password",(await call(C,"login",{ip:"8.8.8.8",body:{username:"mallory",password:"password1"}})).code,429);
 // telegram link per account
 const lk=await call(B,"link");const tok=lk.body.url.split("start=")[1];
 await call(dev(),"hook",{hdr:TGH,body:{update_id:1,message:{text:"/start "+tok,chat:{id:777}}}});
 chk("B connected via bot",(await call(B,"status",{method:"GET"})).body,{connected:true});
 // a fake update without Telegram's secret is ignored (here: someone trying to disconnect B), and the webhook is re-registered with the secret
 store.delete("cfg:whv");tg.length=0;await call(dev(),"hook",{hdr:{},body:{update_id:9,message:{text:"/stop",chat:{id:777}}}});
 chk("unsigned bot update ignored",(await call(B,"status",{method:"GET"})).body,{connected:true});
 const wh=tg.find(x=>x.secret_token);chk("webhook re-registered with secret on production address",wh?[wh.secret_token===SEC,wh.url]:null,[true,"https://screenedstocks.vercel.app/api/dma?a=hook"]);
 chk("no bot message sent for a fake update",tg.filter(x=>x.chat_id).length,0);
 tg.length=0;await call(dev(),"setup",{method:"GET",hdr:{"x-forwarded-host":"evil.example"}});
 const st=tg.find(x=>x.url);chk("setup cannot point the bot elsewhere",st?st.url:null,"https://screenedstocks.vercel.app/api/dma?a=hook");
 // private prices come with your positions only
 {const ub=JSON.parse(store.get("acct:mallory")).uid;store.set("quotes:"+ub,JSON.stringify({quotes:{"NSE:SECRETCO":{price:10}}}));
  chk("your private prices come with your positions",(await call(B,"positions",{method:"GET"})).body.quotes,{"NSE:SECRETCO":{price:10}});
  chk("another account cannot see them",JSON.stringify((await call(A,"positions",{method:"GET"})).body.quotes||{}).includes("SECRETCO"),false);}

 chk("A still on its own chat",store.get("chat:"+legacy),"555");
 // linking the same chat to another account moves it (one chat <-> one account)
 const lk2=await call(A,"link");const tok2=lk2.body.url.split("start=")[1];
 await call(dev(),"hook",{hdr:TGH,body:{update_id:2,message:{text:"/start "+tok2,chat:{id:777}}}});
 chk("chat moved to A, B disconnected",[(await call(A,"status",{method:"GET"})).body.connected,(await call(B,"status",{method:"GET"})).body.connected],[true,false]);
 chk("GET cannot link",(await call(A,"link",{method:"GET"})).code,405);
 // change password invalidates other sessions
 const A2=dev();await call(A2,"login",{body:{username:"aman",password:"password1"}});
 chk("wrong current password",(await call(A,"passwd",{body:{old:"bad-bad-bad",new:"newpassword2"}})).code,401);
 chk("password changed",(await call(A,"passwd",{body:{old:"password1",new:"newpassword2"}})).body,{ok:true});
 chk("other device logged out",(await call(A2,"me",{method:"GET"})).code,401);
 chk("this device still in",(await call(A,"me",{method:"GET"})).code,200);
 chk("old password fails",(await call(dev(),"login",{body:{username:"aman",password:"password1"}})).code,401);
 chk("new password works",(await call(dev(),"login",{body:{username:"aman",password:"newpassword2"}})).code,200);
 // delete account
 chk("delete needs right password",(await call(B,"delete",{body:{password:"nope-nope"}})).code,401);
 chk("delete ok",(await call(B,"delete",{body:{password:"password1"}})).body,{ok:true});
 chk("deleted account record gone",store.has("acct:mallory"),false);
 chk("deleted data gone",[store.has("pos:"+(JSON.parse(store.get("acct:mallory")||"null")||{}).uid)],[false]);
 chk("health works with no login",(await call(dev(),"health",{method:"GET",hdr:{}})).body.bot_token,true);
 // ---- channel notes
 chk("yt needs login",(await call(dev(),"yt",{method:"GET",hdr:{}})).code,401);
 const y=await call(A,"yt",{method:"GET",hdr:{},body:{}}); 
 chk("yt empty channel -> 400",y.code,400);
 A.q=null;
 const yr=await (async()=>{let out={headers:{}};const res={setHeader(){},status(c){out.code=c;return this},json(b){out.body=b;return this}};
  await h({query:{a:"yt",channel:"https://www.youtube.com/@Some.Channel"},headers:{cookie:A.cookie,"x-forwarded-for":"1.1.1.1"},body:{},method:"GET"},res);return out})();
 chk("yt list ok",[yr.code,yr.body.channel&&yr.body.channel.title,yr.body.videos.length,yr.body.next,yr.body.videos[0].duration],[200,"Chan",2,"NP","PT1H2M3S"]);
 chk("yt used handle lookup + key",[ytc[0][0],ytc[0][1].forHandle,ytc[0][1].key],["channels","@Some.Channel","K"]);
 const nt=await call(A,"ytnotes",{body:{notes:{abcdefghijk:{title:"T",text:"hello"},"bad id":{text:"x"}}}});
 chk("notes saved",nt.body,{saved:true});
 chk("notes read back (bad ids dropped)",Object.keys((await call(A,"ytnotes",{method:"GET",hdr:{}})).body.notes),["abcdefghijk"]);
 chk("notes need POST header",(await call(A,"ytnotes",{hdr:{},body:{notes:{}}})).code,400);
 {const r=await call(dev(),"news",{method:"GET"});chk("news needs a query",r.code,400);}
 {const h2=require(process.argv[2]);let out={};const res={setHeader(){},status(c){out.code=c;return this},json(b){out.body=b;return this}};
  await h2({query:{a:"news",q:"Reliance Industries"},headers:{"x-forwarded-for":"9.9.9.9"},method:"GET"},res);
  chk("news parsed and tagged",[out.code,out.body.items.length,out.body.items[0].t,out.body.items[0].s,out.body.items[0].g,out.body.items[1].t],[200,2,"Reliance Q2 results: profit up 9%; board okays bonus","Mint",["Results","Corporate action"],"Old & news"]);
  await h2({query:{a:"news",q:"reliance industries"},headers:{"x-forwarded-for":"9.9.9.9"},method:"GET"},res);chk("news cached",global.newsCalls,1);
  await h2({query:{a:"chart",t:"RELIANCE.NS"},headers:{"x-forwarded-for":"9.9.9.9"},method:"GET"},res);
  chk("chart adjusted and nulls dropped",[out.code,out.body.c,out.body.o,out.body.dates.length,out.body.name],[200,[50.5,51],[50,50.5],2,"Reliance Industries"]);
  await h2({query:{a:"chart",t:"BAD TICKER"},headers:{},method:"GET"},res);chk("chart rejects bad ticker",out.code,400);
  {const of=global.fetch;global.fetch=async(u,o)=>{u=String(u);if(u.includes("finance.yahoo.com")){const five=u.includes("range=5d");
    const ts=five?[1760000000+86400*2,1760000000+86400*3]:[1760000000,1760000000+86400];
    return{json:async()=>({chart:{result:[{meta:{longName:"X",regularMarketPrice:120,regularMarketTime:1760000000+86400*3+3600},timestamp:ts,indicators:{quote:[{open:five?[110,112]:[100,101],high:five?[111,121]:[102,103],low:five?[109,111]:[99,100],close:five?[110,115]:[101,102],volume:[1,2]}],adjclose:[{adjclose:five?[110,115]:[101,102]}]}}]}})}}return of(u,o)};
   await h2({query:{a:"chart",t:"STALE.NS"},headers:{"x-forwarded-for":"9.9.9.8"},method:"GET"},res);
   chk("chart: newer days from the 5-day series and the live price are added",[out.code,out.body.dates.length,out.body.c,out.body.h.slice(-1)[0]],[200,4,[101,102,110,120],121]);global.fetch=of;}}
 {const h2=require(process.argv[2]);let out={};const res={setHeader(){},status(c){out.code=c;return this},json(b){out.body=b;return this}};
  const orig=global.fetch,now=Date.now();let g=0,y=0;
  global.fetch=async(url,o)=>{const u=String(url);
   if(u.startsWith("https://news.google.com/")){g++;return{ok:true,text:async()=>`<rss><item><title>Elon Musk ups ante in Starlink row, calls Ambani Prime Minister - The Hindu</title><link>https://n/1</link><pubDate>${new Date(now-3600e3).toUTCString()}</pubDate><source url="https://www.thehindu.com">The Hindu</source></item><item><title>Musk ups ante in Starlink row, calls Ambani Prime Minister</title><link>https://n/2</link><pubDate>${new Date(now-7200e3).toUTCString()}</pubDate><source url="https://www.ndtv.com">NDTV</source></item><item><title>Top 5 stocks to buy</title><link>https://n/3</link><pubDate>${new Date(now).toUTCString()}</pubDate><source url="https://www.livemint.com">Mint</source></item></rss>`}}
   if(u.startsWith("https://query1.finance.yahoo.com/")){y++;const ts=[...Array(300)].map((_,i)=>1700000000+i*86400);return{json:async()=>({chart:{result:[{meta:{regularMarketPrice:150,regularMarketTime:1760000000},timestamp:ts,indicators:{quote:[{close:ts.map((_,i)=>100+i*0.1)}]}}]}})}}
   return orig(url,o)};
  await h2({query:{a:"feed"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);
  const fb=out.body;chk("feed built (first run fetches every search + sections)",[out.code,g>90,fb.live,fb.pool,fb.themes.find(t=>t.id==="people").stories[0].n,fb.themes.find(t=>t.id==="people").stories[0].who],[200,true,true,2,2,["Elon Musk","Mukesh Ambani"]]);
  const g1=g;await h2({query:{a:"feed"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);chk("feed served from cache",g,g1);
  chk("feed carries outlet names only, no full lists",[typeof fb.themes.find(t=>t.id==="people").stories[0].also[0],fb.full,fb.stories_total],["string",undefined,1]);
  await h2({query:{a:"theme",id:"people"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);
  chk("full theme list served",[out.code,out.body.id,out.body.stories.length,out.body.stories[0].who],[200,"people",1,["Elon Musk","Mukesh Ambani"]]);
  await h2({query:{a:"theme",id:"all"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);
  chk("all-stories list carries the theme",[out.code,out.body.stories.length,!!out.body.stories[0].th],[200,1,true]);
  await h2({query:{a:"theme",id:"../x"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);chk("theme id validated",out.code,400);
  await h2({query:{a:"theme",id:"nosuch"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);chk("missing theme list -> 404",out.code,404);
  await h2({query:{a:"mkt"},headers:{"x-forwarded-for":"7.7.7.7"},method:"GET"},res);
  chk("mkt series with live last price",[out.code,out.body.series.length>20,out.body.series[0].c.slice(-1)[0]],[200,true,150]);
  global.fetch=orig;}
 console.log(f?"FAILS "+f:"ALL PASS");process.exit(0)})()
