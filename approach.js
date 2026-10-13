/* Approaching tab: what history says about shares 0-2% below their 44-DMA (approach.json, built by approach.py).
   Everything shown is a past result: the share of past cases that closed back above the average, what they made, and how the
   ranking did on years it was not fitted on. No opinion is added. */
let APX = null, APOPEN = false;
async function apLoad() {
  if (APX !== null) return; APX = {};
  try { const r = await fetch("/approach.json", { cache: "no-cache" }); if (r.ok) APX = await r.json(); } catch (e) {}
  if (typeof render === "function") render();
}
const apOn = () => typeof sec !== "undefined" && sec === "range" && (tab === "near" || tab === "all");
const apPc = (v, d = 1) => (v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%");
const apP = (v) => (v == null ? "–" : Math.round(v * 100) + "%");
function apFor(s) {
  if (!APX || !APX.today || s.type !== "near") return null;
  if (!APX._m) { APX._m = {}; APX.today.forEach((x) => (APX._m[x.key] = x)); }
  return APX._m["NSE:" + s.symbol] || null;
}
const apDec = (x) => (APX && x ? (APX.deciles_cross || {})[String(x.decx)] : null);
/* which fifth of past cases a value falls in, and how that fifth did from 2020 on */
function apFifth(f, v) {
  const F = APX && APX.factors && APX.factors[f]; if (!F || v == null) return null;
  const r = F.rows.find((r, i) => v <= r.hi || i === F.rows.length - 1); return r ? { b: r.b, late: r.late, early: r.early, F } : null;
}
const AP_SHOW = {
  fromhi: (v) => `${(Math.abs(v) * 100).toFixed(1)}% below its 52-week high`,
  slope: (v) => `44-DMA ${v >= 0 ? "up" : "down"} ${(Math.abs(v) * 100).toFixed(1)}% in 10 days`,
  vs200: (v) => `${(Math.abs(v) * 100).toFixed(1)}% ${v >= 0 ? "above" : "below"} its 200-DMA`,
  r126: (v) => `6-month return better than ${Math.round(v * 100)}% of shares`,
  dist: (v) => `${(Math.abs(v) * 100).toFixed(2)}% below its 44-DMA`,
  volx: (v) => `volume ${v.toFixed(1)}× its 20-day average`,
  liq: (v) => `about ₹${(Math.pow(10, v)).toFixed(Math.pow(10, v) >= 10 ? 0 : 1)} Cr traded a day`,
  stars: (v) => `${v} of 3 stars`,
  rsi: (v) => `RSI ${v.toFixed(0)}`,
};
/* the table cell: chance of a close above the 44-DMA within 10 days, and the tenth of the tested ranking */
function apCell(s) {
  const x = apFor(s); if (!x) return `<td class="apc"><span class="sub">${s.type === "near" ? (ex(s) === "BSE" ? "BSE only: not scored" : APX && APX.today ? "Not scored" : "–") : "–"}</span></td>`;
  const d = apDec(x), c = x.decx >= 8 ? "hi" : x.decx <= 3 ? "lo" : "";
  return `<td class="apc" title="${d ? `Rank ${x.decx} of 10. Past cases with this rank: ${apP(d.crossed)} closed above the 44-DMA within 10 days; average 20-day result ${apPc(d.r20)}` : ""}"><b class="apb ${c}">${apP(x.p_cross)}</b><small>rank ${x.decx}/10${x.checks != null ? ` · trend ${x.checks}/4` : ""}</small></td>`;
}
const apVal = (s) => { const x = apFor(s); return x ? x.p_cross : null; };
/* details row: similar past cases and the trend checks */
function apDetail(s) {
  const x = apFor(s); if (!x) return "";
  const d = apDec(x), rows = ["fromhi", "slope", "vs200", "r126", "dist", "volx", "liq", "stars"].map((f) => {
    const v = x.x[f], q = apFifth(f, v); if (v == null || !q || !q.late) return "";
    return `<tr><td class="l">${esc(APX.names[f])}</td><td class="l">${esc((AP_SHOW[f] || String)(v))}</td><td>${q.b} of 5</td><td>${apPc(q.late.r20)}</td><td>${apP(q.late.crossed)}</td><td>${apPc(q.late.excess)}</td></tr>`; }).join("");
  return `<div class="apd"><b>Outlook from past cases</b>
    <p>${esc(s.symbol)} ranks <b>${x.decx} of 10</b> on the tested ranking (10 = most likely to close back above the 44-DMA within 10 trading days; the model puts it at ${apP(x.p_cross)}).${d ? ` Past cases with the same rank, tested on years the ranking had not seen (${d.n.toLocaleString("en-IN")} cases): <b>${apP(d.crossed)}</b> closed above within 10 days, held 20 days they made <b>${apPc(d.r20)}</b> on average (median ${apPc(d.med20)}), ${apP(d.win)} ended in profit, ${apP(d.q5)} touched +5% before −5%, and the worst tenth lost ${(Math.abs(d.bad10)*100).toFixed(1)}% or more.` : ""}</p>
    ${x.checks != null && APX.checks ? (() => { const k = (APX.checks[String(x.checks)] || {}).late; return `<p>Trend checks passed: <b>${x.checks} of 4</b> (near its 52-week high, 44-DMA rising, above its 200-DMA, 6-month return in the top 40% of shares).${k ? ` Since 2020, approaching shares passing ${x.checks} of 4 made ${apPc(k.r20)} on average over 20 days, ${apP(k.win)} in profit.` : ""}</p>`; })() : ""}
    <div class="ov-scroll"><table class="apt"><thead><tr><th class="l">Check</th><th class="l">${esc(s.symbol)} on ${esc(typeof fdate === "function" ? fdate(APX.price_date) : APX.price_date)}</th><th>Fifth of past cases</th><th>That fifth: avg 20 days</th><th>Closed above in 10 days</th><th>Vs other shares that day</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="sub">Fifths from 1 (lowest value) to 5 (highest); results are from 2020 on. Past results, not a forecast for this share.</p></div>`;
}
/* the summary above the Approaching list */
function apPanel() {
  if (!apOn()) return "";
  if (APX === null) { apLoad(); return ""; }
  if (!APX.base) return "";
  const B = APX.base.test || APX.base.all, A = APX.base.all, y0 = String(APX.first_date || "").slice(0, 4), ty = APX.settings.test_from;
  const tile = (l, v, sub) => `<div class="apk"><span>${l}</span><b>${v}</b><small>${sub}</small></div>`;
  const F = Object.entries(APX.factors || {}).map(([k, f]) => ({ k, f, e: f.spread_early, l: f.spread_late })).filter((z) => z.e != null && z.l != null);
  const held = (z) => Math.sign(z.e) === Math.sign(z.l) && Math.abs(z.e) >= 0.003 && Math.abs(z.l) >= 0.003;
  F.sort((a, b) => (held(b) - held(a)) || Math.abs(b.l) - Math.abs(a.l));
  const fr = F.map((z) => { const r = z.f.rows, lo = r[0].late, hi = r[4].late;
    return `<tr class="${held(z) ? "ap-held" : ""}"><td class="l">${esc(z.f.name)}</td><td>${apPc(lo.r20)}<small>${apP(lo.win)} profit</small></td><td>${apPc(hi.r20)}<small>${apP(hi.win)} profit</small></td><td><b>${apPc(z.l)}</b></td><td>${apPc(z.e)}</td><td class="l">${held(z) ? (z.l > 0 ? "Higher did better, in both periods" : "Lower did better, in both periods") : "Not consistent"}</td></tr>`; }).join("");
  const D = APX.deciles_cross || {}, dr = Object.keys(D).sort((a, b) => b - a).map((k) => { const v = D[k];
    return `<tr class="${+k >= 8 ? "ap-held" : ""}"><td>${k}</td><td>${apP(v.crossed)}</td><td>${apPc(v.r10)}</td><td>${apPc(v.r20)}</td><td>${apP(v.win)}</td><td>${apP(v.q5)}</td><td>${apPc(v.bad10)}</td><td>${v.n.toLocaleString("en-IN")}</td></tr>`; }).join("");
  const today = (APX.today || []).length, top = (APX.today || []).filter((x) => x.decx >= 8).length;
  const same = typeof data !== "undefined" && data.price_date && APX.price_date !== data.price_date ? ` Ranked on closes of ${esc(APX.price_date)}; the list above may be newer.` : "";
  return `<section class="appn"><div class="aph"><div><h3>Approaching: what ${y0}–${String(APX.price_date).slice(0, 4)} history says</h3>
    <p>Every time an NSE share closed 0–2% below its 44-DMA (${A.n.toLocaleString("en-IN")} cases, at most one per share every 5 days, ${APX.stocks.toLocaleString("en-IN")} shares), bought at the next day's open after ${APX.settings.cost_pct}% costs.</p></div></div>
    <div class="apks">${tile("Closed above the 44-DMA within 10 days", apP(A.crossed), `half of those within ${A.days} days`)}${tile("Average result after 20 days", apPc(A.r20), `median ${apPc(A.med20)} · ${apP(A.win)} ended in profit`)}${tile("Touched +5% before −5%", apP(A.q5), "within 10 trading days")}${tile("Waiting for the cross, then buying", apPc(A.wait), "average over 20 days: about the same as buying early")}</div>
    <p class="apn">Most approaching shares do get back above the 44-DMA, and quickly, but crossing it is not the same as making money: on average the gain after 20 days was small and fewer than half ended in profit. The ranking below separates them better than any single number.${same}</p>
    <details class="apx" ${APOPEN ? "open" : ""} ontoggle="APOPEN=this.open"><summary>How the ranking did, and which checks mattered (tap to open)</summary>
    <h4>The ranking, tested on ${ty}–${String(APX.price_date).slice(0, 4)} only</h4>
    <p class="sub">Each year the ranking was fitted on earlier years only, then used on that year. Rank 10 = the tenth it rated most likely to close back above the 44-DMA within 10 days. Today: ${today} approaching NSE shares ranked, ${top} in ranks 8–10.</p>
    <div class="ov-scroll"><table class="apt"><thead><tr><th>Rank</th><th>Closed above in 10 days</th><th>Avg 10 days</th><th>Avg 20 days</th><th>Ended in profit (20 days)</th><th>+5% before −5%</th><th>Worst tenth (20 days)</th><th>Cases</th></tr></thead><tbody>${dr}</tbody></table></div>
    ${APX.checks ? `<h4>Trend checks: shares in an uptrend that dipped to the 44-DMA</h4>
    <p class="sub">Four checks that did better in both ${y0}–2019 and 2020 on: within the top 40% for nearness to the 52-week high, 44-DMA rising (top 40%), price above its 200-DMA, 6-month return in the top 40% of all shares. Chosen from the tables below, which cover all years, so this is not a fair test like the ranking above; it shows that the pattern held in both periods.</p>
    <div class="ov-scroll"><table class="apt"><thead><tr><th>Checks passed</th><th>Closed above in 10 days</th><th>Avg 20 days, from 2020</th><th>Ended in profit</th><th>+5% before −5%</th><th>Avg 20 days, ${y0}–2019</th><th>Cases</th></tr></thead><tbody>${Object.keys(APX.checks).sort((a, b) => b - a).map((k) => { const c = APX.checks[k], L = c.late || {}, E = c.early || {};
      return `<tr class="${+k >= 3 ? "ap-held" : ""}"><td>${k} of 4</td><td>${apP(L.crossed)}</td><td>${apPc(L.r20)}</td><td>${apP(L.win)}</td><td>${apP(L.q5)}</td><td>${apPc(E.r20)}</td><td>${((c.all || {}).n || 0).toLocaleString("en-IN")}</td></tr>`; }).join("")}</tbody></table></div>` : ""}
    ${APX.both ? (() => { const b = APX.both, r = (l, v) => v ? `<tr><td class="l">${l}</td><td>${apP(v.crossed)}</td><td>${apPc(v.r20)}</td><td>${apP(v.win)}</td><td>${apP(v.q5)}</td><td>${apPc(v.bad10)}</td><td>${v.n.toLocaleString("en-IN")}</td></tr>` : "";
      return `<h4>Ranking and trend checks together (${ty} on)</h4><div class="ov-scroll"><table class="apt"><thead><tr><th class="l">Group</th><th>Closed above in 10 days</th><th>Avg 20 days</th><th>Ended in profit</th><th>+5% before −5%</th><th>Worst tenth</th><th>Cases</th></tr></thead><tbody>${r("Rank 8–10 and 3–4 trend checks", b.top_and_trend)}${r("Rank 8–10, fewer trend checks", b.top_only)}${r("Rank 1–7, 3–4 trend checks", b.trend_only)}${r("Neither", b.neither)}</tbody></table></div>`; })() : ""}
    <h4>Each check on its own: lowest fifth against highest fifth</h4>
    <p class="sub">Average 20-day result from 2020 on; “Gap” is how much better the highest fifth did than the lowest against other shares bought the same day (so the market's own move is taken out), from 2020 on and in ${y0}–2019. Highlighted rows held in both periods.</p>
    ${x.checks != null && APX.checks ? (() => { const k = (APX.checks[String(x.checks)] || {}).late; return `<p>Trend checks passed: <b>${x.checks} of 4</b> (near its 52-week high, 44-DMA rising, above its 200-DMA, 6-month return in the top 40% of shares).${k ? ` Since 2020, approaching shares passing ${x.checks} of 4 made ${apPc(k.r20)} on average over 20 days, ${apP(k.win)} in profit.` : ""}</p>`; })() : ""}
    <div class="ov-scroll"><table class="apt"><thead><tr><th class="l">Check</th><th>Lowest fifth</th><th>Highest fifth</th><th>Gap from 2020</th><th>Gap ${y0}–2019</th><th class="l">Reading</th></tr></thead><tbody>${fr}</tbody></table></div>
    <p class="sub">Past results on daily closes; they describe what happened to similar cases, not what a share will do. Results, news and the market's direction are not in these numbers.</p></details></section>`;
}
