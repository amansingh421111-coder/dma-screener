// Live check of the deployed site on real data: screenshots and numbers. Run by .github/workflows/qa.yml.
// Signs in to nothing (positions stay private); only public pages are visited.
const { chromium } = require("playwright");
const fs = require("fs");
const URL = "https://screenedstocks.vercel.app/";
(async () => {
  fs.mkdirSync("shots", { recursive: true });
  await new Promise((r) => setTimeout(r, 150000));   // let the deploy of the same push finish first
  const b = await chromium.launch();
  const report = [], errs = [];
  for (const [w, scheme] of [[1000, "light"], [390, "dark"]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, serviceWorkers: "block" });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errs.push(`${w}: ${e.message}`));
    p.on("console", (m) => { if (m.type() === "error") errs.push(`${w} console: ${m.text().slice(0, 160)}`); });
    await p.goto(URL + "#insights", { waitUntil: "networkidle" }); await p.waitForTimeout(4000);
    await p.evaluate("IV.view='outlook';render()"); await p.waitForTimeout(6000);
    await p.screenshot({ path: `shots/outlook_${w}.png`, fullPage: true });
    report.push(`${w} outlook overflow=${await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)} fan=${!!(await p.$(".ov-fan svg"))} decileBars=${(await p.$$(".ov-bar")).length} shareRows=${(await p.$$(".ov-t tbody tr")).length} forestRows=${(await p.$$(".ov-fpt tbody tr")).length}`);
    for (const sym of ["RELIANCE", "INFY", "TCS", "NTPCGREEN", "HDFCBANK"]) {
      await p.evaluate(`inPick('${sym}','NSE');IV.stab='outlook';render()`); await p.waitForTimeout(5000);
      await p.evaluate("render()"); await p.waitForTimeout(800);
      const el = await p.$(".sk"); if (el) await el.screenshot({ path: `shots/${sym}_${w}.png` });
      const info = await p.evaluate((s) => {
        const C = EQ.charts[s + ".NS"], r = typeof soRow === "function" ? soRow(s) : null;
        const fan = document.querySelector(".ov-fan svg"), labs = fan ? [...fan.querySelectorAll(".ov-lab")].map((t) => t.textContent) : [];
        return { px: C && C.c ? C.c[C.c.length - 1] : (C && C.error) || null, n: C && C.c ? C.c.length : 0, beta: C && C.c ? +ovBeta(C).toFixed(2) : null,
          est: r && r.o ? r.o.slice(0, 2) : null, labs, fanW: fan ? fan.getAttribute("width") : null, boxW: fan ? fan.parentElement.clientWidth : null,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
      }, sym);
      report.push(`${w} ${sym} ${JSON.stringify(info)}`);
    }
    await p.evaluate("openStock('INFY','NSE')"); await p.waitForTimeout(5000);
    const q = await p.$(".eq-p"); if (q) await q.screenshot({ path: `shots/quote_${w}.png` });
    await p.evaluate("entClose && entClose()").catch(() => {});
    await ctx.close();
  }
  fs.writeFileSync("shots/report.txt", report.concat(["errors:"], errs.slice(0, 40)).join("\n"));
  for (const l of report) console.log("::notice::" + l.slice(0, 900));
  console.log("::notice::errors " + errs.length + ": " + errs.slice(0, 8).join(" | ").slice(0, 900));
  await b.close();
})();
