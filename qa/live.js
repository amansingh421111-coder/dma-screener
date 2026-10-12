// Live check of the deployed site on real data: screenshots and numbers. Run by .github/workflows/qa.yml.
// Signs in to nothing (positions stay private); only public pages are visited.
const { chromium } = require("playwright");
const fs = require("fs");
const URL = process.env.LIVE_URL || "https://screenedstocks.vercel.app/";
(async () => {
  fs.mkdirSync("shots", { recursive: true });
  await new Promise((r) => setTimeout(r, +(process.env.QA_WAIT ?? 150000)));   // let the deploy of the same push finish first
  const b = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH, args: ["--no-sandbox"] } : {});
  const probe = [];   // the price feed itself: last days per ticker
  for (const t of ["RELIANCE.NS", "RELIANCE.BO", "500325.BO", "ADANIPORTS.NS", "ADANIPORTS.BO", "532921.BO", "TCS.BO", "INFY.BO", "HDFCBANK.BO", "CUB.BO", "KARURVYSYA.BO", "PERSISTENT.BO", "SBIN.BO", "ITC.BO"]) {
    try { const r = await fetch(URL + "api/dma?a=chart&t=" + t), j = await r.json(); probe.push(`${t} ${r.status} ${j.c ? j.c.length + " bars " + j.dates[0] + " … " + j.dates.slice(-3).join(",") + " " + j.c.slice(-3).join(",") + " asof " + j.asof : j.error}`); }
    catch (e) { probe.push(`${t} fetch failed ${e.message}`); }
  }
  const report = [], errs = [];
  // screenshot of one element; the page re-renders while prices load, so take the box and shoot the page area (never throws)
  const shot = async (p, sel, path) => { try { const box = await p.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; e.scrollIntoView(); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y + window.scrollY, width: r.width, height: Math.min(r.height, 6000) }; }, sel); if (box && box.width > 0) await p.screenshot({ path, clip: box, fullPage: true }); } catch (e) { report.push(`screenshot ${path} skipped: ${String(e.message).slice(0, 80)}`); } };
  for (const [w, scheme] of [[1000, "light"], [390, "dark"]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, serviceWorkers: "block" });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errs.push(`${w}: ${e.message}`));
    p.on("console", (m) => { if (m.type() === "error") errs.push(`${w} console: ${m.text().slice(0, 160)}`); });
    p.on("response", (r) => { if (r.status() >= 400) errs.push(`${w} ${r.status()} ${r.url().replace("https://screenedstocks.vercel.app", "").slice(0, 120)}`); });
    await p.goto(URL, { waitUntil: "networkidle" }); await p.waitForTimeout(4000);
    await p.screenshot({ path: `shots/screener_${w}.png` });
    report.push(`${w} screener liq=${JSON.stringify(await p.evaluate(() => { const c = {}; document.querySelectorAll(".lq").forEach((e) => { const k = e.textContent.trim().split(/\s/)[0]; c[k] = (c[k] || 0) + 1; }); return { pills: c, banner: (document.getElementById("mliq") || {}).textContent?.trim().slice(0, 200) || "hidden", build: (document.body.textContent.match(/Build [\d.-]+/) || [""])[0] }; }))}`);
    await p.goto(URL + "#insights", { waitUntil: "networkidle" }); await p.waitForTimeout(4000);
    await p.evaluate("IV.view='outlook';render()"); await p.waitForTimeout(6000);
    await p.screenshot({ path: `shots/outlook_${w}.png`, fullPage: true });
    report.push(`${w} outlook overflow=${await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)} fan=${!!(await p.$(".ov-fan svg"))} decileBars=${(await p.$$(".ov-bar")).length} shareRows=${(await p.$$(".ov-t tbody tr")).length} forestRows=${(await p.$$(".ov-fpt tbody tr")).length}`);
    for (const sym of ["RELIANCE", "INFY", "HDFCBANK", "NTPCGREEN", "KARURVYSYA"]) {
      await p.evaluate(`inPick('${sym}','NSE');IV.stab='company';render()`); await p.waitForTimeout(5000);
      await p.evaluate("render()"); await p.waitForTimeout(800);
      await shot(p, ".sk", `shots/co_${sym}_${w}.png`);
      const info = await p.evaluate(() => ({ desc: (document.querySelector(".co-d") || {}).textContent?.length || 0, empty: (document.querySelector(".sk .ix-empty") || {}).textContent || "",
        bars: document.querySelectorAll(".co-q rect").length, peers: document.querySelectorAll(".co-pt tbody tr").length, doing: document.querySelectorAll(".co-dt tbody tr").length,
        tiles: document.querySelectorAll(".co-tiles .ov-tile").length, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth }));
      report.push(`${w} company ${sym} ${JSON.stringify(info)}`);
    }
    await p.goto(URL + "#strategies", { waitUntil: "networkidle" }); await p.waitForTimeout(4000);
    await p.evaluate("SVIEW='list';STAB={dma44_zone:'exits'};sxTog('dma44_zone')"); await p.waitForTimeout(3000);
    await p.evaluate("render()"); await p.waitForTimeout(800);
    await p.evaluate(() => { const e = [...document.querySelectorAll("h4.sx-sub")].find((x) => x.offsetParent && /Which stop/.test(x.textContent)); if (e) e.scrollIntoView(); });
    await p.screenshot({ path: `shots/exits_${w}.png` });
    report.push(`${w} exits ${JSON.stringify(await p.evaluate(() => ({ loaded: typeof EXI !== "undefined" && !!(EXI && EXI.strategies), n: EXI && EXI.strategies ? EXI.strategies.length : 0, date: EXI && EXI.price_date, all: !!(EXI && EXI.strategies && EXI.strategies[0] && EXI.strategies[0].chosen_all), rows: document.querySelectorAll(".ex-t tbody tr").length, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth })))}`);
    await p.evaluate("openStock('INFY','NSE')"); await p.waitForTimeout(5000);
    await shot(p, ".eq-p", `shots/quote_${w}.png`);
    await p.evaluate("entClose && entClose()").catch(() => {});
    await ctx.close();
  }
  // My Positions with made-up test holdings (never anyone's real data): sign-in and saving are simulated, prices and pages are live
  try {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: "block" });
    const p = await ctx.newPage(); p.on("pageerror", (e) => errs.push(`pos: ${e.message}`));
    p.on("response", (r) => { if (r.status() >= 400) errs.push(`pos ${r.status()} ${r.url().replace("https://screenedstocks.vercel.app", "").slice(0, 120)}`); });
    const sj = await (await fetch(URL + "signals.json")).json().catch(() => ({}));
    const bseOnly = ((sj.signals || []).find((x) => x.exchange === "BSE") || {}).symbol || null;
    const T = [["ADANIPORTS", "BSE", 3, 1700], ["MBAPL", "NSE", 5, 160], ["RELIANCE", "NSE", 2, 1200]].concat(bseOnly ? [[bseOnly, "BSE", 1, 100]] : []);
    const pos = T.map(([s, e, q, px], i) => ({ id: "t" + i, symbol: s, exchange: e, sl: null, target: null, slMode: "auto", tgMode: "auto", alertMa: true, alertSl: true, alertTg: true, txns: [{ id: "x" + i, type: "buy", date: "2026-10-01", qty: q, price: px }] }));
    await p.route("**/api/dma*", (r) => { const a = new (require("url").URL)(r.request().url()).searchParams.get("a"), j = (o) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(o) });
      if (a === "me") return j({ username: "test" }); if (a === "status") return j({ connected: false });
      if (a === "positions") return j(r.request().method() === "GET" ? { positions: pos, ts: Date.now() + 1e9, watchlist: [], settings: {}, auto: null } : { saved: true });
      return r.continue(); });
    await p.goto(URL + "#positions", { waitUntil: "load" }); await p.waitForTimeout(15000);
    const rows = await p.evaluate(() => [...document.querySelectorAll("tr.hrow")].map((r) => r.innerText.replace(/\s+/g, " ").slice(0, 220)));
    report.push("pos rows " + JSON.stringify(rows));
    await p.screenshot({ path: "shots/pos_1280.png" });
    await p.evaluate(() => toggleH("t0")); await p.waitForTimeout(6000);
    report.push("pos ADANIPORTS details " + JSON.stringify(await p.evaluate(() => ({ other: (document.body.innerText.match(/Same share on NSE\s*\n?\s*[^\n]*/) || [""])[0], panel: ((document.querySelector(".exw") || {}).innerText || "").slice(0, 300) }))));
    await p.screenshot({ path: "shots/pos_detail_1280.png", fullPage: true });
    await p.evaluate(() => { go("ins"); }); await p.waitForTimeout(3000); await p.evaluate(() => inPick("ADANIPORTS", "BSE")); await p.waitForTimeout(8000);
    report.push("ins ADANIPORTS BSE " + JSON.stringify(await p.evaluate(() => [IV.ex, ((document.querySelector(".sk-head") || {}).innerText || "").replace(/\s+/g, " ").slice(0, 260)])));
    await p.screenshot({ path: "shots/ins_bse_1280.png" });
    await p.fill("#ix-q", "adani ports"); await p.waitForTimeout(800);
    report.push("search " + JSON.stringify(await p.evaluate(() => [...document.querySelectorAll("#ix-q-l .lso")].map((x) => x.innerText.replace(/\s+/g, " ")).slice(0, 4))));
    await p.screenshot({ path: "shots/search_1280.png" });
    await p.keyboard.press("Escape");
    // visible-text sweep: template leftovers, undefined, NaN, [object ...] anywhere on the page
    const junk = async (l) => { const r = await p.evaluate(() => { const t = document.body.innerText, o = []; for (const rx of [/\$\{/, /\}\./, /\bundefined\b/, /\bNaN\b/, /\[object /, /\bnull\b/, /Infinity/]) { const m = t.match(new RegExp(".{0,40}" + rx.source + ".{0,40}")); if (m) o.push(m[0].replace(/\s+/g, " ")); } return o; }); if (r.length) report.push(`JUNK ${l} ${JSON.stringify(r)}`); };
    for (const [s_, e_] of T.map((x) => [x[0], x[1]]).concat([["ADANIPORTS", "NSE"]])) {
      await p.evaluate(([s_, e_]) => inPick(s_, e_), [s_, e_]); await p.waitForTimeout(5000);
      for (const tab of ["summary", "company", "outlook", "tech", "fin", "peers", "news"]) { await p.evaluate((t) => { IV.stab = t; render(); }, tab); await p.waitForTimeout(500); await junk(`${s_} ${e_} ${tab}`); }
      report.push(`stock ${s_} ${e_} ` + JSON.stringify(await p.evaluate(() => ((document.querySelector(".sk-head") || {}).innerText || "").replace(/\s+/g, " ").slice(0, 220))));
    }
    await p.evaluate(() => go("pos")); await p.waitForTimeout(1500); await p.evaluate((ids) => { ids.forEach((i) => EXP.add(i)); render(); }, T.map((_, i) => "t" + i)); await p.waitForTimeout(8000); await junk("positions expanded");
    await p.screenshot({ path: "shots/pos_all_1280.png", fullPage: true });
    await p.evaluate(() => openStock("ADANIPORTS", "BSE")); await p.waitForTimeout(6000);
    report.push("quote panel " + JSON.stringify(await p.evaluate(() => ((document.querySelector(".eq-h") || {}).innerText || "").replace(/\s+/g, " ").slice(0, 200))));
    await p.screenshot({ path: "shots/quote_bse_1280.png" });
    await ctx.close();
  } catch (e) { report.push("POSITIONS CHECK FAILED: " + String(e && e.stack || e).slice(0, 600)); }
  fs.writeFileSync("shots/report.txt", probe.concat(report).concat(["errors:"], errs.slice(0, 40)).join("\n"));
  for (const l of report) console.log("::notice::" + l.slice(0, 900));
  console.log("::notice::errors " + errs.length + ": " + errs.slice(0, 8).join(" | ").slice(0, 900));
  await b.close();
})();
