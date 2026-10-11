/* Candle patterns: results of candles.py (20 textbook patterns, each in three settings) shown as a view inside the Strategies tab.
   Bullish patterns are judged as buys against stocks bought on the same day; bearish patterns as warnings over the next 10 days.
   Data: /candles.json. Styles: app.css (cd-*). Uses esc(), $(), render(), openStock(), ii-style popovers from index.html. */
let CDL = null;
const CD = { side: "all", open: new Set(), sort: "verdict" };
async function loadCdl() {
  if (CDL !== null) return; CDL = {};
  try { const r = await fetch("/candles.json", { cache: "no-cache" }); if (r.ok) CDL = await r.json(); } catch (e) {}
  render();
}
const CD_V = {   // verdict -> label, class, sort order
  works: ["Works", "cd-works", 0], weak: ["A little", "cd-weak", 1], none: ["No edge", "cd-none", 2], worse: ["Opposite", "cd-worse", 3], few: ["Too rare", "cd-few", 4],
};
const CD_VB = { works: "Works as a warning", weak: "A little", none: "No edge", worse: "Opposite", few: "Too rare" };
const cdP = (v, d = 2) => (v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%");

/* small drawings of each pattern: grey candles show the move before it, coloured ones the pattern itself. [open, high, low, close] on a 0-100 scale */
const CD_ART = {
  hammer: [[78, 80, 66, 68], [66, 68, 54, 56], [46, 50, 26, 49]],
  invhammer: [[78, 80, 66, 68], [66, 68, 54, 56], [46, 66, 45, 49]],
  bull_engulf: [[80, 82, 68, 70], [64, 66, 54, 56], [56, 58, 48, 50], [48, 66, 46, 64]],
  piercing: [[82, 84, 72, 74], [72, 74, 62, 64], [66, 67, 46, 48], [42, 60, 40, 58]],
  bull_harami: [[82, 84, 72, 74], [72, 74, 62, 64], [66, 67, 40, 42], [48, 55, 46, 53]],
  morning_star: [[84, 86, 74, 76], [74, 76, 66, 68], [68, 69, 48, 50], [44, 47, 38, 42], [46, 64, 45, 62]],
  soldiers: [[34, 36, 26, 28], [30, 46, 29, 45], [42, 58, 41, 57], [54, 72, 53, 71]],
  dragonfly: [[78, 80, 66, 68], [66, 68, 54, 56], [52, 53, 30, 52]],
  doji_low: [[78, 80, 66, 68], [66, 68, 54, 56], [48, 56, 40, 48]],
  bull_marubozu: [[46, 48, 40, 42], [42, 44, 36, 40], [38, 72, 37, 71]],
  tweezer_bot: [[80, 82, 68, 70], [66, 68, 56, 58], [58, 60, 40, 44], [44, 58, 40, 56]],
  three_inside_up: [[84, 86, 74, 76], [74, 76, 66, 68], [68, 69, 44, 46], [50, 58, 48, 56], [56, 72, 55, 70]],
  shooting_star: [[22, 34, 20, 32], [34, 46, 32, 44], [54, 74, 51, 51]],
  hanging_man: [[22, 34, 20, 32], [34, 46, 32, 44], [54, 55, 34, 51]],
  bear_engulf: [[20, 32, 18, 30], [36, 46, 34, 44], [44, 52, 42, 50], [52, 54, 34, 36]],
  dark_cloud: [[18, 28, 16, 26], [28, 38, 26, 36], [34, 56, 33, 54], [60, 62, 40, 42]],
  bear_harami: [[18, 28, 16, 26], [28, 38, 26, 36], [34, 60, 33, 58], [52, 54, 45, 47]],
  evening_star: [[16, 26, 14, 24], [26, 34, 24, 32], [32, 52, 31, 50], [56, 62, 53, 58], [54, 55, 36, 38]],
  crows: [[66, 74, 64, 72], [70, 71, 54, 55], [58, 59, 42, 43], [46, 47, 28, 29]],
  gravestone: [[22, 34, 20, 32], [34, 46, 32, 44], [48, 70, 47, 48]],
};
function cdArt(pid, k) {
  const C = CD_ART[pid] || [], n = C.length, w = 12, gap = 6, W = n * (w + gap) + gap, H = 56;
  const lo = Math.min(...C.map((x) => x[2])), hi = Math.max(...C.map((x) => x[1])), y = (v) => (4 + (hi - v) / (hi - lo || 1) * (H - 8)).toFixed(1);
  const prior = n - k;
  return `<svg class="cd-art" style="--w:${W}px" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">${C.map(([o, h, l, c], i) => {
    const x = gap + i * (w + gap), cx = x + w / 2, top = Math.max(o, c), bot = Math.min(o, c), cls = i < prior ? "cd-pr" : c >= o ? "cd-up" : "cd-dn";
    return `<g class="${cls}"><line x1="${cx}" x2="${cx}" y1="${y(h)}" y2="${y(l)}"/><rect x="${x}" y="${y(top)}" width="${w}" height="${Math.max(1.5, y(bot) - y(top)).toFixed(1)}" rx="1.5"/></g>`; }).join("")}</svg>`;
}
function cdRules() {
  const by = {}; for (const r of CDL.rules || []) (by[r.pattern] = by[r.pattern] || []).push(r);
  return by;
}
function cdBest(L) { return L.slice().sort((a, b) => CD_V[a.verdict][2] - CD_V[b.verdict][2])[0]; }
function cdCell(r) {
  if (!r) return `<td class="cd-c">–</td>`;
  const te = r.test || {}, mt = r.monthly_test || {}, lab = r.side === "bear" && r.verdict === "works" ? "Works" : CD_V[r.verdict][0];
  return `<td class="cd-c"><span class="cd-v ${CD_V[r.verdict][1]}">${lab}</span><span class="cd-n">${te.edge != null ? cdP(te.edge) : "–"}<small>${mt.t != null ? "how sure " + mt.t + ", " : ""}${te.n ? Number(te.n).toLocaleString("en-IN") + " trades" : "no trades"}</small></span></td>`;
}
function cdYears(r) {
  const Y = Object.entries(r.years || {}).filter(([y, v]) => v.n >= 30 && v.edge != null);
  if (!Y.length) return "";
  const mx = Math.max(...Y.map(([, v]) => Math.abs(v.edge)), 0.005);
  return `<div class="cd-yrs" role="img" aria-label="Edge by year">${Y.map(([y, v]) => { const good = r.side === "bear" ? v.edge < 0 : v.edge > 0, hgt = Math.abs(v.edge) / mx * 30;
    return `<span title="${y}: ${cdP(v.edge)} against the same-day control, ${v.n} trades" class="${+y >= CDL.split_year ? "t" : ""}"><i class="${good ? "g" : "b"}" style="height:${hgt.toFixed(1)}px;${v.edge >= 0 ? "bottom:32px" : "top:32px"}"></i><b>${y.slice(2)}</b></span>`; }).join("")}</div>`;
}
function cdDetail(p, L) {
  const ctx = CDL.contexts || {};
  return `<tr class="cd-d"><td colspan="6"><div class="cd-dw">
    <p class="cd-txt">${esc(p.text)}</p>
    <div class="cd-sets">${L.map((r) => { const te = r.test || {}, tr = r.train || {}, h10 = r.hold10 || {}, ex = r.exit;
      return `<div class="cd-set"><h4>${esc(ctx[r.ctx] || r.ctx)} <span class="cd-v ${CD_V[r.verdict][1]}">${r.side === "bear" && r.verdict === "works" ? "Works" : CD_V[r.verdict][0]}</span></h4>
        <p class="cd-why">${esc(r.why)}.</p>
        <dl class="cd-dl"><div><dt>Trades from ${CDL.split_year}</dt><dd>${te.n ? Number(te.n).toLocaleString("en-IN") : "–"} <small>about ${r.per_year} a year</small></dd></div>
          <div><dt>${r.side === "bear" ? "Stock's 10-day return" : "Average profit per trade"}</dt><dd>${cdP(te.avg)} <small>win ${te.win != null ? Math.round(te.win * 100) + "%" : "–"}</small></dd></div>
          <div><dt>Same-day control</dt><dd>${cdP(te.ctrl)}</dd></div>
          <div><dt>Difference</dt><dd class="${te.edge > 0 ? "sx-pos" : te.edge < 0 ? "sx-neg" : ""}">${cdP(te.edge)}</dd></div>
          <div><dt>Before ${CDL.split_year}</dt><dd>${cdP(tr.edge)} <small>${tr.n ? Number(tr.n).toLocaleString("en-IN") + " trades" : ""}</small></dd></div>
          ${r.side === "bull" ? `<div><dt>Exit used</dt><dd>${ex.time_only ? "Sell after 10 days" : `−${ex.stop}% stop, +${ex.target}% target, 10 days`}</dd></div><div><dt>Simply holding 10 days</dt><dd>${cdP(h10.edge)} <small>vs control</small></dd></div>` : `<div><dt>Exit used</dt><dd>Sell after 10 days</dd></div>`}</dl>
        ${cdYears(r)}
        ${r.today_n ? `<div class="cd-today"><span>At the last close (${r.today_n}):</span> ${r.today.slice(0, 24).map((s) => `<button type="button" class="ent" onclick="openStock('${esc(s)}','NSE')">${esc(s)}</button>`).join(" ")}${r.today_n > 24 ? ` and ${r.today_n - 24} more` : ""}</div>` : ""}</div>`; }).join("")}</div></div></td></tr>`;
}
function cdView() {
  if (CDL === null) { loadCdl(); return `<div class="empty">Loading the candle pattern test…</div>`; }
  if (!CDL.rules || !CDL.rules.length) return `<div class="empty">The candle pattern test has not finished yet. It runs every Sunday and whenever the test changes.</div>`;
  const by = cdRules(), P = (CDL.patterns || []).filter((p) => CD.side === "all" || p.side === CD.side);
  const cnt = { works: 0, weak: 0, none: 0, worse: 0, few: 0 }, pc = { works: 0, weak: 0, none: 0, worse: 0, few: 0 };
  for (const r of CDL.rules) cnt[r.verdict]++;
  for (const p of CDL.patterns) { const b = cdBest(by[p.id] || []); if (b) pc[b.verdict]++; }
  const rows = P.map((p) => ({ p, L: by[p.id] || [] })).sort((a, b) => CD.sort === "name" ? a.p.name.localeCompare(b.p.name) : (CD_V[cdBest(a.L).verdict][2] - CD_V[cdBest(b.L).verdict][2]) || ((cdBest(b.L).test || {}).n || 0) - ((cdBest(a.L).test || {}).n || 0));
  const ctxHead = (side) => (side === "bear" ? ["On its own", "After a run-up", "In a downtrend"] : ["On its own", "In an uptrend", "At a rising 44-DMA"]);
  const heads = CD.side === "bear" ? ctxHead("bear") : CD.side === "bull" ? ctxHead("bull") : ["On its own", "In context 1", "In context 2"];
  const body = rows.map(({ p, L }) => { const id = p.id, open = CD.open.has(id), today = L.reduce((s, r) => s + (r.today_n || 0), 0);
    return `<tr class="cd-r${open ? " on" : ""}" onclick="CD.open.has('${id}')?CD.open.delete('${id}'):CD.open.add('${id}');render()" aria-expanded="${open}">
      <td class="cd-pn">${cdArt(id, p.candles)}<div><b>${esc(p.name)}</b><small class="${p.side === "bull" ? "cd-bull" : "cd-bear"}">${p.side === "bull" ? "Bullish, tested as a buy" : "Bearish, tested as a warning"}</small></div></td>
      ${CDL.contexts && L.length ? [0, 1, 2].map((i) => cdCell(L[i])).join("") : ""}<td class="cd-c cd-td">${today ? `<b>${today}</b><small>stocks</small>` : `<span class="cd-mute">–</span>`}</td></tr>${open ? cdDetail(p, L) : ""}`; }).join("");
  const seg = (v, l) => `<button aria-pressed="${CD.side === v}" onclick="CD.side='${v}';render()">${l}</button>`;
  const nR = CDL.rules.length, luck = Math.max(1, Math.round(nR * 0.05 * 0.5));
  return `<div class="cd">
    <div class="cd-head"><div class="cd-sum">
      <p class="cd-lede">Of <b>${CDL.patterns.length}</b> classic candle patterns, each tested in 3 settings on ${Number(CDL.stocks).toLocaleString("en-IN")} NSE stocks since ${CDL.first_date.slice(0, 4)}, the best setting of each:</p>
      <div class="cd-tiles">${["works", "weak", "none", "worse", "few"].filter((k) => pc[k] || k !== "few").map((k) => `<div class="cd-tile ${CD_V[k][1]}"><b>${pc[k]}</b><span>${k === "works" ? "work" : k === "weak" ? "help a little" : k === "none" ? "no edge" : k === "worse" ? "do the opposite" : "too rare to judge"}</span></div>`).join("")}</div>
      <p class="ix-fine">Across all ${nR} pattern-and-setting versions: ${cnt.works} work, ${cnt.weak} help a little, ${cnt.none} show no edge, ${cnt.worse} did the opposite, ${cnt.few} were too rare. With ${nR} versions tested, about ${luck} could pass by luck alone, so a lone pass is weak evidence.</p></div>
      <details class="cd-how"><summary>How this was tested</summary><p>Signal at the close of the pattern's last candle, bought at the next day's open. Only days when the stock was ₹${CDL.filters.min_price}+ and traded at least ₹50 lakh a day count; trades crossing an unadjusted split or bad price are set aside; ${CDL.cost_pct}% costs per round trip. Each trade is compared with other stocks bought on the <b>same day</b> with the same exit, so a rising market does not make a pattern look good. Bullish patterns: the stop and target (or simply selling after 10 days) were chosen on ${CDL.first_date.slice(0, 4)}–${CDL.split_year - 1} and judged on ${CDL.split_year} onwards. Bearish patterns are judged as warnings: did the stock do worse than the control over the next 10 days? “Works” needs a consistent difference month after month from ${CDL.split_year} (how sure 2 or more) and the same direction before ${CDL.split_year}. Updated every Sunday.</p></details></div>
    <div class="sx-bar"><div class="sx-seg">${seg("all", "All")}${seg("bull", "Bullish (buy)")}${seg("bear", "Bearish (warning)")}</div><span class="sp"></span>
      <label class="cd-sort">Order <select onchange="CD.sort=this.value;render()"><option value="verdict"${CD.sort === "verdict" ? " selected" : ""}>Best result first</option><option value="name"${CD.sort === "name" ? " selected" : ""}>Name</option></select></label></div>
    <div class="cd-scroll"><table class="cd-t"><thead><tr><th>Pattern</th>${heads.map((h) => `<th>${h}<small>vs same-day control</small></th>`).join("")}<th>Last close</th></tr></thead><tbody>${body}</tbody></table></div>
    ${CD.side === "all" ? `<p class="ix-fine">In context, bullish patterns: 1 = in an uptrend (above a rising 200-day average), 2 = touching a rising 44-day average. Bearish patterns: 1 = after a run-up of 8% or more in 10 days, 2 = in a downtrend. Select a pattern for the numbers, year by year, and the stocks showing it at the last close.</p>` : ""}
    <p class="ix-fine">Prices up to ${esc(CDL.price_date || "")}. A pattern showing up is a shape on a chart, not advice to buy or sell.</p></div>`;
}
