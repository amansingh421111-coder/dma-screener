// Live-site check: loads screenedstocks.vercel.app in Chromium, opens the outlook views, saves screenshots and a JSON report.
const { chromium } = require("playwright"); const fs = require("fs");
const URL = "https://screenedstocks.vercel.app/";
const OUT = "qa/out"; fs.mkdirSync(OUT, { recursive: true });
const report = { when: new Date().toISOString(), runs: [] };
async function run(name, w, scheme, steps) {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
  const p = await ctx.newPage(); const errs = [];
  p.on("pageerror", (e) => errs.push("pageerror: " + e.message)); p.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
  await p.goto(URL + "#insights", { waitUntil: "networkidle", timeout: 60000 }); await p.waitForTimeout(4000);
  const r = { name, w, scheme, shots: [], checks: {} };
  for (const s of steps) {
    await p.evaluate(s.js); await p.waitForTimeout(s.wait || 6000);
    if (s.check) r.checks[s.id] = await p.evaluate(s.check);
    const file = `${OUT}/${name}-${s.id}.png`;
    if (s.sel) { const el = await p.$(s.sel); if (el) await el.screenshot({ path: file }); else r.checks[s.id + "_missing"] = s.sel; }
    else await p.screenshot({ path: file, fullPage: true });
    r.shots.push(file);
  }
  r.overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  r.errors = errs; report.runs.push(r); await b.close();
}
const stock = (sym) => ({ id: "stock-" + sym, js: `go('ins');inPick('${sym}','NSE');IV.stab='outlook';render()`, wait: 9000, sel: ".sk",
  check: `(()=>{const C=EQ.charts['${sym}.NS'];const r=soRow('${sym}');return {hasChart:!!(C&&C.c),points:C&&C.c?C.c.length:0,last:C&&C.c?C.c[C.c.length-1]:null,beta:C&&C.c?+ovBeta(C).toFixed(3):null,row:r?{o:r.o,n:r.n,sec:r.sec}:null,fanText:(document.querySelector('.ov-fan')||{}).textContent||'',fanW:(document.querySelector('.ov-fan svg')||{getAttribute:()=>null}).getAttribute('width'),boxW:(document.querySelector('.ov-fan')||{}).clientWidth}})()` });
(async () => {
  const steps = [
    { id: "outlook", js: "go('ins');IV.view='outlook';render()", wait: 9000, check: "({fc:!!(FC&&FC.nifty),so:!!(SO&&SO.s),fanW:(document.querySelector('.ov-fan svg')||{getAttribute:()=>null}).getAttribute('width'),box:(document.querySelector('.ov-fan')||{}).clientWidth,rows:document.querySelectorAll('.ov-t tbody tr').length,dec:document.querySelectorAll('.ov-bar').length,nifty:INS&&INS.nifty?INS.nifty.close.slice(-1)[0]:null,cone:FC&&FC.nifty?FC.nifty.h['63'].level:null})" },
    stock("RELIANCE"), stock("INFY"), stock("NTPCGREEN"), stock("TCS"), stock("HDFCBANK"),
    { id: "quote-INFY", js: "openStock('INFY','NSE')", wait: 7000, sel: ".eq-p", check: "({svgW:(document.querySelector('.eq-ch svg')||{getAttribute:()=>null}).getAttribute('width'),box:(document.querySelector('.eq-ch')||{}).clientWidth})" },
  ];
  await run("desk1280", 1280, "light", steps);
  await run("tab1000", 1000, "light", steps);
  await run("phone390", 390, "dark", steps);
  fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report.runs.map((r) => ({ name: r.name, overflow: r.overflow, errors: r.errors.slice(0, 5), checks: r.checks })), null, 1).slice(0, 6000));
})();
