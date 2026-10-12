/* Automatic stop loss and target for your positions.
   The rule for each strategy is chosen by exits.py (exits.json): the stop/target rule with the best average profit per trade
   after costs this year (weight 3), last year (2) and the year before (1), all rules tested on the same trades.
   The screener works the levels out after every price check (auto:<uid>, used for Telegram); this file shows them and
   works out the same levels in the browser until the screener's next check (same arithmetic as exitrules.py). */
let EXI = null, AUTO = null;
async function loadExits() {
  if (EXI !== null) return; EXI = {};
  try { const r = await fetch("/exits.json", { cache: "no-cache" }); if (r.ok) EXI = await r.json(); } catch (e) {}
  render();
}
const exRules = () => { const m = {}; if (EXI && EXI.rules) for (const k in EXI.rules) EXI.rules[k].forEach((r) => (m[r.id] = r)); return m; };
const exStrat = (id) => (EXI && EXI.strategies ? EXI.strategies.find((s) => s.id === id) : null);
const exDefault = () => (EXI && EXI.default) || "screener";
/* fallback before exits.json exists: the screener rule's library exit */
const EX_FALLBACK = { id: "fix-sp8-tp20-h40", fam: "fix", sp: 8, tp: 20, hold: 40, label: "Stop −8%, target +20%, sell after 40 trading days at the latest" };
/* which rule: best this year and the two before (as you asked), or best over every year (your setting on the panel) */
const exAll = () => !!(typeof SET !== "undefined" && SET && SET.exitAll);
/* stop distance: the same percentage for every share (default), or scaled to each share's daily move (your setting) */
const exVol = () => !!(typeof SET !== "undefined" && SET && SET.exitVol);
const exPick = (s) => (exVol() ? (exAll() ? s.chosen_vol_all : s.chosen_vol) : exAll() ? s.chosen_all : s.chosen) || s.chosen;
/* the rule's stop in words that are the same for every share using it */
function exStopWord(rid) {
  const r = exRules()[rid] || (rid === EX_FALLBACK.id ? EX_FALLBACK : null); if (!r) return "";
  return r.fam === "trail" ? `${r.t}% below high` : r.fam === "fix" ? `${r.sp}% below cost` : r.fam === "dma" ? "at the 44-DMA" : `${r.k}× ATR` + (r.fam === "chand" ? " below high" : " below cost");
}
function exChosen(sid) {
  const s = exStrat(sid) || exStrat(exDefault()), R = exRules();
  if (s && R[exPick(s).rule]) return { s, rule: R[exPick(s).rule] };
  return { s: s || null, rule: EX_FALLBACK };
}

/* ---- the rule arithmetic (mirror of exitrules.py; tested against it) ---- */
function exAtr(h, l, c) {
  const n = c.length, out = new Array(n).fill(NaN); let a = NaN, pc = NaN;
  for (let i = 0; i < n; i++) {
    const hi = h[i], lo = l[i], cl = c[i];
    if (!(hi === hi && lo === lo && cl === cl && hi != null && lo != null && cl != null)) { out[i] = a; continue; }
    const tr = pc !== pc ? hi - lo : Math.max(hi - lo, Math.abs(hi - pc), Math.abs(lo - pc));
    a = a !== a ? tr : a + (tr - a) / 14; out[i] = a; pc = cl;
  }
  return out;
}
function exSma(c, n = 44) {
  const out = new Array(c.length).fill(NaN); let s = 0, bad = 0;
  for (let i = 0; i < c.length; i++) {
    const v = c[i]; if (v == null || v !== v) bad++; else s += v;
    if (i >= n) { const u = c[i - n]; if (u == null || u !== u) bad--; else s -= u; }
    if (i >= n - 1 && !bad) out[i] = s / n;
  }
  return out;
}
const exNn = (x) => (x == null || x !== x ? -Infinity : x);
const exFmax = (a, b) => (b == null || b !== b ? a : a !== a ? b : Math.max(a, b));
function exSim(O, H, L, C, D, a, r, upto, final) {
  const f = r.fam, hold = r.hold, W = O.length, last = Math.min(hold, upto == null ? W : upto);
  let stop, tgt = Infinity;
  if (f === "fix") { stop = 1 - r.sp / 100; if (r.tp) tgt = 1 + r.tp / 100; }
  else if (f === "atr") { stop = 1 - r.k * a; if (r.m) tgt = 1 + r.m * a; }
  else if (f === "chand") stop = 1 - r.k * a;
  else if (f === "trail") stop = 1 - r.t / 100;
  else { stop = Math.max(1 - r.cat / 100, exNn(D[0])); if (r.tp) tgt = 1 + r.tp / 100; }
  let mx = -Infinity, ret = 0, kx = -1, why = -1;
  const step = (k) => {
    if (f === "chand") stop = Math.max(stop, mx - r.k * a);
    else if (f === "trail") stop = Math.max(stop, mx * (1 - r.t / 100));
    else if (f === "dma") stop = Math.max(stop, exNn(D[k]));
  };
  for (let k = 0; k < last; k++) {
    if (k > 0) { mx = exFmax(mx, C[k - 1]); step(k); }
    const o = O[k], h = H[k], l = L[k], c = C[k];
    let px = null, w = -1;
    if (o <= stop) { px = o; w = 0; }
    else if (o >= tgt) { px = o; w = 1; }
    else if (l <= stop) { px = stop; w = 0; }
    else if (h >= tgt) { px = tgt; w = 1; }
    else if (k === hold - 1) { px = c; w = 2; }
    if (w >= 0) { ret = px - 1; kx = k; why = w; break; }
  }
  if (upto != null && final && kx < 0 && last > 0) {
    mx = exFmax(mx, C[last - 1]);
    if (f === "chand" || f === "trail") step(last);
    else if (f === "dma" && last < D.length) step(last);
  }
  return { ret, k: kx, why, stop, tgt };
}
const r2 = (x) => Math.round(x * 100) / 100;
/* levels for one open position: dates/o/h/l/c oldest first; entry = the date the holding opened; ep = average cost */
function exLive(dates, o, h, l, c, entry, ep, rule, final) {
  const n = c.length; if (n < 15 || !(ep > 0)) return null;
  const A = exAtr(h, l, c), M = exSma(c, 44); let ei = dates.findIndex((d) => d >= entry);
  if (ei < 0) {
    const a = A[n - 1] / ep; if (a !== a) return null;
    const s = exSim([], [], [], [], [M[n - 1] / ep], a, rule, 0, final);
    return { sl: r2(s.stop * ep), target: isFinite(s.tgt) ? r2(s.tgt * ep) : null, days_held: 0, days_left: rule.hold, exit: null, atr: r2(A[n - 1]) };
  }
  const s0 = Math.max(ei - 1, 0), a = A[s0] / ep; if (a !== a) return null;
  const W = n - ei, D = [ei >= 1 ? M[s0] / ep : NaN];
  for (let i = ei; i < n - 1; i++) D.push(M[i] / ep);
  D.push(M[n - 1] / ep);
  const sl = (x) => x.slice(ei, n).map((v) => (v == null ? NaN : v / ep));
  const s = exSim(sl(o), sl(h), sl(l), sl(c), D, a, rule, W, final);
  const out = { sl: r2(s.stop * ep), target: isFinite(s.tgt) ? r2(s.tgt * ep) : null, days_held: W, days_left: Math.max(0, rule.hold - W), exit: null, atr: r2(A[s0]) };
  if (s.k >= 0) out.exit = { date: dates[ei + s.k], price: r2((s.ret + 1) * ep), why: ["stop", "target", "time"][s.why] };
  return out;
}

/* ---- price history for a position (shared cache with the quote panel) ---- */
const exTk = (p) => (typeof lsTicker === "function" ? lsTicker(p.symbol, p.exchange) : p.symbol + (p.exchange === "BSE" ? ".BO" : ".NS"));
const EXBUSY = {};
function exPx(p) {
  if (typeof EQ === "undefined") return null; const t = exTk(p);
  if (EQ.charts[t]) return EQ.charts[t].c ? EQ.charts[t] : null;
  if (typeof lsChartLoad === "function") lsChartLoad(p.symbol, p.exchange);
  else if (!EXBUSY[t]) { EXBUSY[t] = 1; fetch("/api/dma?a=chart&t=" + encodeURIComponent(t)).then((r) => r.json().then((j) => { EQ.charts[t] = r.ok && j.c ? j : { error: j.error || "No price history." }; })).catch(() => { EQ.charts[t] = { error: "Could not reach the price source." }; }).finally(() => render()); }
  return null;
}
/* a price for a holding the screener has not priced yet (bought after the last check, or a BSE share between hourly checks) */
function exQuote(p) {
  const C = exPx(p); if (!C || !C.c || C.c.length < 2) return null;
  const n = C.c.length, px = C.c[n - 1], m = exSma(C.c, 44)[n - 1];
  return { price: px, chg: r2((px / C.c[n - 2] - 1) * 100), pct: m === m ? r2((px / m - 1) * 100) : null, src: "chart", date: C.dates[n - 1], asof: C.asof || null };
}

/* ---- the levels a position uses ---- */
const isManSl = (p) => p.slMode === "manual" || (p.slMode == null && p.sl > 0);
const isManTg = (p) => p.tgMode === "manual" || (p.tgMode == null && p.target > 0);
function exAuto(p) {
  const L = ledger(p); if (!(L.qty > 0)) return null;
  const sid = p.strategy && exStrat(p.strategy) ? p.strategy : exDefault(), ep = r2(L.avg), k = p.exchange + ":" + p.symbol;
  const sv = AUTO && AUTO.items ? AUTO.items[k] : null;
  if (sv && sv.entry_date === L.since && Math.abs(sv.entry_price - ep) < 0.006 && (sv.strategy === sid || (!exStrat(sid) && !p.strategy)) && (sv.basis || "recent") === (exAll() ? "all" : "recent") && (sv.stop_kind || "vol") === (exVol() ? "vol" : "pct")) return Object.assign({ src: "server" }, sv);
  const ch = exChosen(sid); exPx(p); const Hh = typeof lsHist === "function" ? lsHist(p.symbol, p.exchange) : null, C = Hh && !Hh.thin ? Hh.C : exPx(p), base = { strategy: sid, strategy_name: ch.s ? ch.s.name : "Screener Buy", rule: ch.rule.id, rule_label: ch.rule.label || ch.rule.id, rule_score: ch.s ? exPick(ch.s).score : null, entry_date: L.since, entry_price: ep, src: "browser" };
  if (C && C.c) { const v = exLive(C.dates, C.o, C.h, C.l, C.c, L.since, ep, ch.rule, true); if (v) return Object.assign(base, v); }
  if (ch.rule.fam === "fix") return Object.assign(base, { sl: r2(ep * (1 - ch.rule.sp / 100)), target: ch.rule.tp ? r2(ep * (1 + ch.rule.tp / 100)) : null, exit: null, days_left: null });
  return Object.assign(base, { sl: null, target: null, exit: null, pending: true });
}
function lv(p) {
  const A = exAuto(p), ms = isManSl(p), mt = isManTg(p);
  return { sl: ms ? p.sl : A && A.sl, tg: mt ? p.target : A && A.target, slAuto: !ms, tgAuto: !mt, A };
}
/* position object with the levels in use, for code that reads p.sl / p.target */
const withLv = (p) => { const v = lv(p); return Object.assign({}, p, { sl: v.sl, target: v.tg, _slAuto: v.slAuto && v.sl != null, _tgAuto: v.tgAuto, _trail: v.tgAuto && v.tg == null && v.A && !v.A.pending, _exit: v.A && v.A.exit && ((v.A.exit.why === "stop" && v.slAuto) || (v.A.exit.why === "target" && v.tgAuto) || (v.A.exit.why === "time" && (v.slAuto || v.tgAuto))) ? v.A.exit : null }); };

/* ---- what the details panel shows ---- */
const exPc = (v, d = 1) => (v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%");
function exWhy(sid) {
  const s = exStrat(sid); if (!s) return `<p class="sub">The strategy test has not run yet, so the screener rule's standard exit is used: ${esc(EX_FALLBACK.label)}.</p>`;
  const R = exRules(), n = (EXI.rules[s.kind] || []).length, all = exAll(), vol = exVol() && !!s.chosen_vol, cur = exPick(s);
  const years = vol ? (all ? (s.chosen_vol_all || {}).years : (s.chosen_vol || {}).years) : all ? (s.chosen_all || {}).years : (s.ranking[0] || {}).years;
  const lib = s.library && s.library.rule !== cur.rule ? s.library : null;
  const yr = (s.chosen.parts || []).map((x) => { const v = (years || {})[String(x.year)], u = lib && (lib.years || {})[String(x.year)];
    return v ? `<tr><td>${x.year}${x.year === EXI.current_year ? " so far" : ""}<small>${v.n.toLocaleString("en-IN")} trades${all ? "" : " · weight " + x.weight}</small></td><td>${exPc(v.avg)}<small>${Math.round(v.win * 100)}% won · ${v.days} days</small></td>${lib ? `<td>${u ? exPc(u.avg) : "–"}${u ? `<small>${Math.round(u.win * 100)}% won · ${u.days} days</small>` : ""}</td>` : ""}</tr>` : ""; }).join("");
  const tot = all ? `<tr class="tot"><td>Every year since ${String(EXI.first_date || "").slice(0, 4)}${cur.n ? `<small>${cur.n.toLocaleString("en-IN")} trades</small>` : ""}</td><td>${exPc(cur.score, 2)}</td>${lib ? `<td>${lib.all ? exPc(lib.all.avg, 2) : "–"}</td>` : ""}</tr>`
    : `<tr class="tot"><td>Weighted score</td><td>${exPc(cur.score, 2)}</td>${lib ? `<td>${exPc(lib.score, 2)}</td>` : ""}</tr>`;
  const w = vol ? s.walk_vol || s.walk : s.walk, wa = w && w.avg ? w.avg : null;
  const seg = `<div class="seg2 exm" role="group" aria-label="How the rule is chosen"><button type="button" aria-pressed="${!all}" onclick="exBasis(0)">Best in recent years</button><button type="button" aria-pressed="${all}" onclick="exBasis(1)">Best over all years</button></div>`;
  const seg2 = s.chosen_vol ? `<div class="seg2 exm" role="group" aria-label="Stop distance"><button type="button" aria-pressed="${!vol}" onclick="exVolSet(0)">Same % for every share</button><button type="button" aria-pressed="${vol}" onclick="exVolSet(1)">Scaled to each share's daily move</button></div>` : "";
  const alt = s.chosen_vol ? (vol ? (all ? s.chosen_all : s.chosen) : all ? s.chosen_vol_all : s.chosen_vol) : null;
  const altL = alt && alt.rule !== cur.rule ? ` The best ${vol ? "same-% rule" : "rule scaled to each share's daily move"} (${esc(((R[alt.rule] || {}).label || alt.rule).replace(/, sell after.*/, ""))}) scores ${exPc(alt.score, 2)} on the same basis${vol ? "" : "; switch above if you prefer it"}.` : "";
  const wl = wa ? `<p class="sub"><b>Month-by-month check from ${w.start}</b>, choosing with only the trades finished at the time: best in recent years <b>${exPc(wa.adaptive, 2)}</b> a trade, best over all earlier years <b>${exPc(wa.longrun, 2)}</b>, standard exit ${exPc(wa.library, 2)}. ${w.distinct_picks} different rules came out on top in recent years over that time.</p>` : "";
  return `<div class="exb"><span class="sub">Stop distance</span>${seg2}</div><div class="exb"><span class="sub">Choose the rule on</span>${seg}</div>
    <div class="ov-scroll"><table class="ext"><thead><tr><th>Average profit per trade, after costs</th><th>This rule</th>${lib ? `<th>Standard exit<small>${esc((R[lib.rule] || {}).label || lib.rule).replace(/, sell after.*/, "")}</small></th>` : ""}</tr></thead>
    <tbody>${yr}${tot}</tbody></table></div>
    <p class="sub">${all ? `The rule with the best average over every year` : `The rule with the best average this year and the two before (weights 3, 2, 1)`}, among ${vol ? `all ${n} stop/target rules` : `the rules that give every share the same percentage stop`}, tested on the same ${esc(s.name)} trades (${Number(EXI.stocks || 0).toLocaleString("en-IN")} NSE shares, ${EXI.years_of_data} years).${altL} Chosen again every weekday evening.</p>${wl}`;
}
function exVolSet(v) { if (typeof SET === "undefined") return; SET.exitVol = v ? 1 : 0; savePos(); render(); }
function exBasis(v) { if (typeof SET === "undefined") return; SET.exitAll = v ? 1 : 0; savePos(); render(); }
function exPanel(p, c) {
  if (!c.open) return "";
  const v = lv(p), A = v.A, sid = p.strategy && exStrat(p.strategy) ? p.strategy : exDefault();
  const opts = (EXI && EXI.strategies ? EXI.strategies : []).map((s) => `<option value="${esc(s.id)}" ${s.id === sid ? "selected" : ""}>${esc(s.name)}</option>`).join("") || `<option value="screener" selected>Screener Buy (first day 0–5% above the 44-DMA)</option>`;
  const cell = (lbl, val, auto, field) => `<div class="exl"><span>${lbl}</span><b>${val != null ? inr(val) : A && A.pending ? "Working out…" : auto && A && field === "tg" ? "No fixed target" : "Not set"}</b><small>${auto ? (val == null && A && !A.pending && field === "tg" ? "The rule sells on its trailing stop" : "Automatic") : "Your own"}${c.px != null && val ? " · " + (field === "sl" ? ((c.px / val - 1) * 100).toFixed(1) + "% away" : ((val / c.px - 1) * 100).toFixed(1) + "% to go") : ""}</small>
    ${auto ? "" : `<button type="button" class="ent" onclick="exReset('${p.id}','${field}')">Back to automatic</button>`}</div>`;
  const ex = A && A.exit, xd = ex ? fdate(ex.date) : "";
  const xmsg = ex ? `<div class="exx ${ex.why === "target" ? "up" : ""}">${ex.why === "stop" ? `The automatic stop ${inr(ex.price)} was reached on ${xd}: the rule says sell.` : ex.why === "target" ? `The automatic target ${inr(ex.price)} was reached on ${xd}: the rule says sell.` : `Held ${A.days_held} trading days: the rule's time limit says sell at the close on ${xd}.`} Record the sale with Sell when you act on it.</div>` : "";
  const tl = A && A.days_left != null && !ex ? `<div class="exl"><span>Time limit</span><b>${A.days_left} trading day${A.days_left === 1 ? "" : "s"} left</b><small>of ${(exRules()[A.rule] || EX_FALLBACK).hold || "–"}</small></div>` : "";
  const src = A ? (A.src === "server" ? `Worked out by the screener${AUTO && AUTO.updated ? " at " + new Date(AUTO.updated).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}${AUTO && AUTO.final === false ? " (during market hours: a trailing stop moves after the close)" : ""}. Telegram alerts use these levels.` : "Worked out in your browser from the latest prices; the screener confirms them at its next check and Telegram alerts follow from then.") : "";
  return `<div class="exw"><div class="exh"><b>Stop loss and target</b><label class="exs">Strategy you used <select onchange="exSet('${p.id}',this.value)">${opts}</select></label></div>
    ${xmsg}<div class="exg">${cell("Stop loss", v.sl, v.slAuto, "sl")}${cell("Target", v.tg, v.tgAuto, "tg")}${tl}</div>
    ${A ? `<p class="sub"><b>Rule:</b> ${esc(A.rule_label || "")}${A.kept ? ". The stop stays at its earlier, higher level: stops only move up" : ""}.</p>` : ""}${(() => {   // why this share's stop sits where it does
      const R = A && (exRules()[A.rule] || null), ep = A && A.entry_price; if (!R || !ep) return "";
      if (R.fam === "trail" || R.fam === "fix") return `<p class="sub"><b>Same for every share under this strategy:</b> the stop is ${R.fam === "trail" ? `${R.t}% below the highest close since you bought (it started ${R.t}% below your cost, ${inr(ep * (1 - R.t / 100))}, and only moves up)` : `${R.sp}% below your average cost (${inr(ep * (1 - R.sp / 100))})`}. How far it is from today's price differs only by how much each share has moved since.</p>`;
      if (!A.atr || !(R.fam === "chand" || R.fam === "atr")) return "";
      const k = R.k, d = k * A.atr; return `<p class="sub"><b>For ${esc(p.symbol)}:</b> its average daily move (ATR, 14 days) was ${inr(A.atr)} on the day before you bought, ${(A.atr / ep * 100).toFixed(1)}% of your average cost. ${k}× that is ${inr(d)} (${(d / ep * 100).toFixed(1)}%), so the stop started at ${inr(ep - d)}${R.fam === "chand" ? " and trails " + inr(d) + " below the highest close since" : ""}. Other shares under the same strategy use the same rule with their own daily move, which is why their stops sit at different distances.</p>`; })()}
    ${exWhy(sid)}<p class="ix-fine">${src} Set your own stop or target with “Stop loss, target &amp; alerts”; it replaces the automatic one until you switch back.</p></div>`;
}
function exSet(id, sid) { const h = POS.find((x) => x.id === id); if (!h) return; h.strategy = sid === exDefault() ? "" : sid; savePos(); render(); }
function exReset(id, f) { const h = POS.find((x) => x.id === id); if (!h) return; if (f === "sl") { h.slMode = "auto"; h.sl = null; } else { h.tgMode = "auto"; h.target = null; } savePos(); render(); }

/* ---- Strategies page: the exit rules compared for one strategy ---- */
function exStratView(id) {
  if (EXI === null) { loadExits(); return ""; }
  const s = exStrat(id); if (!s) return "";
  const R = exRules(), cy = EXI.current_year, top = s.table.slice(0, 8), libRow = s.table.find((r) => r[0] === s.library_rule);
  if (libRow && !top.includes(libRow)) top.push(libRow);
  const row = (r, i) => { const ru = R[r[0]] || {}, on = r[0] === s.chosen.rule, lib = r[0] === s.library_rule;
    return `<tr class="${on ? "ex-on" : ""}"><td>${s.table.indexOf(r) + 1}</td><td class="l">${esc((ru.label || r[0]).replace(/, sell after (\d+) trading days at the latest/, " · $1 days"))}${on ? ' <small class="exa">Used for positions</small>' : ""}${lib ? ' <small class="exa own">Standard exit</small>' : ""}</td>
      <td><b>${exPc(r[1], 2)}</b></td><td>${exPc(r[2])}</td><td>${exPc(r[3])}</td><td>${exPc(r[4])}</td><td>${exPc(r[5])}</td><td>${r[6] ?? "–"}</td></tr>`; };
  const w = s.walk, ty = s.trades_by_year || {};
  const wy = w && w.years ? Object.entries(w.years).slice(-6).map(([y, v]) => `<tr><td>${y}</td><td>${exPc(v[0], 2)}</td><td>${exPc(v[1], 2)}</td><td>${exPc(v[2], 2)}</td><td>${(v[3] || 0).toLocaleString("en-IN")}</td></tr>`).join("") : "";
  return `<h4 class="sx-sub" style="margin-top:0">Which stop and target worked best this year</h4>
    <p class="m" style="margin-bottom:6px">${(EXI.rules[s.kind] || []).length} exit rules replayed on the same ${esc(s.name)} trades: fixed percentages, volatility (ATR) levels, trailing stops and a 44-DMA stop. Score = average profit per trade after costs, weighted 3 for ${cy} so far (${(ty[cy] || 0).toLocaleString("en-IN")} finished trades), 2 for ${cy - 1} and 1 for ${cy - 2}. The top rule sets the automatic stop and target on My Positions.</p>
    <div class="sx-w"><table class="sx2 ex-t" style="min-width:720px"><thead><tr><th>#</th><th class="l">Rule</th><th>Score</th><th>${cy} so far</th><th>${cy - 1}</th><th>${cy - 2}</th><th>All years</th><th>Days held</th></tr></thead><tbody>${top.map(row).join("")}</tbody></table></div>
    ${w ? `<h4 class="sx-sub">Does choosing on recent years help? Month-by-month check</h4><p class="m" style="margin-bottom:6px">Each month from ${w.start}, the rule was chosen with only the trades finished by then (same weighting), then used on that month's new trades. Compared with the standard exit and with the rule that was best over all earlier years. ${w.t_vs_library != null ? `Against the standard exit: better in ${w.months_better} of ${w.months} months, how sure t ${w.t_vs_library.toFixed(1)}${Math.abs(w.t_vs_library) < 2 ? " (within normal luck)" : ""}.` : ""} ${w.distinct_picks} different rules were picked over time.</p>
    <div class="sx-w"><table class="sx2" style="min-width:0"><thead><tr><th>Year</th><th>Chosen on recent years</th><th>Standard exit</th><th>Best over all earlier years</th><th>Trades</th></tr></thead><tbody>${wy}<tr class="ex-on"><td>All from ${w.start}</td><td><b>${exPc(w.avg.adaptive, 2)}</b></td><td>${exPc(w.avg.library, 2)}</td><td>${exPc(w.avg.longrun, 2)}</td><td>${w.n.toLocaleString("en-IN")}</td></tr></tbody></table></div>` : ""}
    <h4 class="sx-sub">Fixed stop and target grid (expanded test)</h4>`;
}
