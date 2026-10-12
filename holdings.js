/* My Positions: the holdings table.
   Sortable columns, columns that fit the screen (with your own choice saved), grouping by the strategy each share was bought under,
   subtotals and totals that line up with their columns. Every money column says what it is: Invested (what you paid),
   Current value (shares x latest price), P&L (current value - invested). */
const HC = [   // key, header, priority (1 = always shown, 4 = widest screens only), numeric, sort value, title
  ["share", "Share", 0, false, (r) => r.p.symbol, "Share, exchange and company"],
  ["strat", "Strategy", 3, false, (r) => hStratName(hSid(r.p)), "The strategy the share was bought under; it sets the automatic stop and target"],
  ["qty", "Qty", 1, true, (r) => r.c.L.qty, "Shares held"],
  ["avg", "Avg cost", 1, true, (r) => r.c.L.avg, "Average price paid per share for the shares you still hold"],
  ["ltp", "LTP", 1, true, (r) => r.c.px, "Last traded price on the exchange shown, with today's change"],
  ["day", "Today", 2, true, (r) => r.c.day, "Change in this holding's value today"],
  ["inv", "Invested", 1, true, (r) => r.c.invested, "What you paid: quantity x average cost"],
  ["val", "Current value", 1, true, (r) => r.c.value, "Quantity x last traded price"],
  ["pl", "P&L", 1, true, (r) => r.c.unreal, "Current value minus invested (not yet booked)"],
  ["ret", "Return", 3, true, (r) => r.c.unrealPct, "P&L as a percentage of what you invested"],
  ["wt", "Weight", 3, true, (r) => r.c.value, "Share of your current portfolio value"],
  ["stop", "Stop loss", 1, true, (r) => { const v = lv(r.p); return v.sl && r.c.px ? r.c.px / v.sl - 1 : null; }, "Sell level; sorted by how far the price is above it"],
  ["risk", "Risk to stop", 2, true, (r) => hRisk(r), "What you would lose from today's price if the stop is hit: quantity x (LTP - stop)"],
  ["exit", "Target / time", 3, true, (r) => { const v = lv(r.p); return v.A && v.A.days_left != null ? v.A.days_left : null; }, "Target price, and trading days left before the rule's time limit"],
  ["held", "Held", 4, true, (r) => r.c.days, "Days since this holding was opened"],
  ["status", "Status", 1, false, (r) => (r.c.st ? r.c.st[2] : -1), "What needs your attention"],
  ["act", "", 0, false, null, ""],
];
let HS = { k: "attention", d: -1, group: "none", cols: {} };
try { const s = JSON.parse(rd("dma_hold_view") || "null"); if (s && typeof s === "object") HS = Object.assign(HS, s); } catch (e) {}
const hSave = () => wr("dma_hold_view", JSON.stringify(HS));
const hSid = (p) => (p.strategy && typeof exStrat === "function" && exStrat(p.strategy) ? p.strategy : typeof exDefault === "function" ? exDefault() : "screener");
const hStratName = (sid) => { const s = typeof exStrat === "function" ? exStrat(sid) : null; return ((s && s.name) || "Screener Buy").replace(/\s*\(.*\)\s*$/, ""); };
const hRisk = (r) => { const v = lv(r.p); return v.sl && r.c.px != null ? r.c.L.qty * Math.max(0, r.c.px - v.sl) : null; };
const hLevel = () => { const w = document.documentElement.clientWidth; return w < 1000 ? 1 : w < 1250 ? 2 : w < 1500 ? 3 : 4; };
let HLV = 0, HW = 0, HRT = null;
const HDROP = new Set();   // columns left out because they do not fit this screen (never the core ones, never ones you switched on)
addEventListener("resize", () => { clearTimeout(HRT); HRT = setTimeout(() => { const w = document.documentElement.clientWidth; if (w !== HW && typeof view_ !== "undefined" && view_ === "pos") { HDROP.clear(); render(); } }, 120); });
const hOn = (c) => (c[2] === 0 ? true : HS.cols[c[0]] != null ? HS.cols[c[0]] : !HDROP.has(c[0]) && c[2] <= hLevel());
const HCORE = new Set(["share", "ltp", "inv", "val", "pl", "stop", "act"]);
/* after drawing: if the table is wider than the screen, leave out the least important optional column and draw again */
function hFit() {
  const w = document.querySelector("#plist .htw"), t = w && w.querySelector("table"); HW = document.documentElement.clientWidth;
  if (!t || !w.offsetWidth || t.scrollWidth <= w.clientWidth + 1) return;
  const next = ["held", "exit", "wt", "ret", "strat", "day", "risk", "status", "avg"].find((k) => HS.cols[k] == null && !HDROP.has(k) && hOn(HC.find((x) => x[0] === k)));
  if (next) { HDROP.add(next); render(); }
}
function hSort(k) { if (HS.k === k) HS.d = -HS.d; else { HS.k = k; HS.d = k === "share" || k === "strat" ? 1 : -1; } hSave(); render(); }
function hGroup(g) { HS.group = g; hSave(); render(); }
function hCol(k, on) { HS.cols[k] = on; hSave(); render(); }
function hColsReset() { HS.cols = {}; HDROP.clear(); hSave(); render(); }
function hSorted(rows) {
  if (HS.k === "attention" || !HC.find((c) => c[0] === HS.k)) return sortRows(rows, false);
  const f = HC.find((c) => c[0] === HS.k)[4], d = HS.d;
  return rows.slice().sort((a, b) => { const x = f(a), y = f(b);
    if (x == null && y == null) return a.p.symbol.localeCompare(b.p.symbol); if (x == null) return 1; if (y == null) return -1;   // blanks last either way
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * d || a.p.symbol.localeCompare(b.p.symbol); });
}
/* one cell */
function hCell(k, r, tv, showRet) {
  const { p, c } = r, L = c.L, q = c.q, v = lv(p);
  switch (k) {
    case "share": return `<td class="hs" onclick="toggleH('${p.id}')"><div class="hs1">${entS(p.symbol, p.exchange, "<b>" + esc(p.symbol) + "</b>")}${exTag(p.exchange)}${typeof inNewsBadge === "function" ? inNewsBadge(p.symbol, p.exchange) : ""}</div><small>${esc(pName(p, q))}</small>${(() => { const sc = !hOn(HC[1]) && HS.group !== "strategy", st = !hOn(HC.find((x) => x[0] === "status")); return sc || st ? `<div class="hs2">${sc ? `<span class="hst">${esc(hStratName(hSid(p)))}</span>` : ""}${st ? `<span class="tag ${c.st[1]}">${c.st[0]}</span>` : ""}</div>` : ""; })()}</td>`;
    case "strat": return `<td><span class="hst" title="${esc(v.A ? v.A.rule_label || "" : "")}">${esc(hStratName(hSid(p)))}</span></td>`;
    case "qty": return `<td class="n">${L.qty}${!hOn(HC.find((x) => x[0] === "avg")) ? `<small>@ ${inr(L.avg)}</small>` : ""}</td>`;   // average cost under the quantity when its own column does not fit
    case "avg": return `<td class="n">${inr(L.avg)}</td>`;
    case "ltp": return `<td class="n">${c.px != null ? `<b>${inr(c.px)}</b><small><span class="${q && q.chg != null ? pcl(q.chg) : ""}">${q && q.chg != null ? sg(q.chg) + "%" : ""}</span> · <span title="Exchange and time of this price: a time means today in market hours (checked every 15 minutes), a date means that day's closing price">${pxSrc(p, q)}</span></small>` : "<small>Loading price…</small>"}</td>`;
    case "day": return `<td class="n">${c.day != null ? `<span class="${pcl(c.day)}">${mny(c.day)}</span>` : "–"}</td>`;
    case "inv": return `<td class="n">${inr(c.invested)}</td>`;
    case "val": return `<td class="n">${c.px != null ? `<b>${inr(c.value)}</b>` : `<span title="No price yet: shown at cost">${inr(c.value)}*</span>`}</td>`;
    case "pl": return `<td class="n">${c.unreal == null ? "–" : `<b class="${pcl(c.unreal)}">${mny(c.unreal)}</b>${showRet ? `<small class="${pcl(c.unreal)}">${sg(+c.unrealPct.toFixed(2))}%</small>` : ""}`}</td>`;
    case "ret": return `<td class="n">${pcs(c.unrealPct)}</td>`;
    case "wt": return `<td class="n">${tv ? (c.value / tv * 100).toFixed(1) + "%" : "–"}</td>`;
    case "stop": return `<td class="n">${v.sl ? `${inr(v.sl)}<small>${v.slAuto ? `<span class="exa" title="${esc(v.A ? "Automatic: " + (v.A.rule_label || "") : "")}">Auto</span> ` : `<span class="exa own">Yours</span> `}${c.px != null ? ((c.px / v.sl - 1) * 100).toFixed(1) + "% away" : ""}</small>` : v.A && v.A.pending ? "<small>Working out…</small>" : "–"}</td>`;
    case "risk": { const x = hRisk(r); return `<td class="n">${x != null ? `${inr(x)}<small>${c.value ? (x / c.value * 100).toFixed(1) + "% of value" : ""}</small>` : "–"}</td>`; }
    case "exit": { const tg = v.tg, A = v.A; return `<td class="n">${tg ? inr(tg) + (c.px ? `<small>${((tg / c.px - 1) * 100).toFixed(1)}% to go</small>` : "") : A && !A.pending && v.tgAuto ? "Trailing stop" : "–"}${A && A.days_left != null && !A.exit ? `<small>${A.days_left} day${A.days_left === 1 ? "" : "s"} left</small>` : ""}</td>`; }
    case "held": return `<td class="n">${held(c.days)}</td>`;
    case "status": return `<td><span class="tag ${c.st[1]}" style="margin:0">${c.st[0]}</span></td>`;
    case "act": return `<td class="ac"><button class="btn sm pri" onclick="openForm('buy','${p.id}')">Buy</button><button class="btn sm" onclick="openForm('sell','${p.id}')">Sell</button><button class="btn sm hx" onclick="toggleH('${p.id}')" aria-expanded="${EXP.has(p.id)}" aria-label="${EXP.has(p.id) ? "Hide" : "Show"} details for ${esc(p.symbol)}" title="Details">${EXP.has(p.id) ? "▴" : "▾"}</button></td>`;
  }
  return "<td></td>";
}
/* the table, with optional strategy groups */
function hTable(oc, T) {
  HLV = hLevel();
  const cols = HC.filter(hOn), showRet = !cols.some((c) => c[0] === "ret"), n = cols.length;
  const avgIn = !cols.some((c) => c[0] === "avg");
  const th = cols.map(([k, l, , num, f, t]) => f ? `<th class="${num ? "n" : ""}" aria-sort="${HS.k === k ? (HS.d > 0 ? "ascending" : "descending") : "none"}" title="${esc(t)}"><button type="button" onclick="hSort('${k}')">${k === "qty" && avgIn ? "Qty · avg" : l}${HS.k === k ? `<i>${HS.d > 0 ? "▲" : "▼"}</i>` : ""}</button></th>` : `<th></th>`).join("");
  const sum = (rows) => { const s = { inv: 0, val: 0, pl: 0, day: 0, risk: 0, priced: 0, dayBase: 0 }; rows.forEach((r) => { s.inv += r.c.invested; s.val += r.c.value; if (r.c.unreal != null) s.pl += r.c.unreal; if (r.c.day != null) { s.day += r.c.day; s.dayBase += r.c.value - r.c.day; } const x = hRisk(r); if (x != null) s.risk += x; }); return s; };
  const agg = (s, label, cls, extra) => `<tr class="${cls}">${cols.map(([k]) => {
    if (k === "share") return `<td class="hs">${label}${extra || ""}</td>`;
    if (k === "inv") return `<td class="n">${inr(s.inv)}</td>`;
    if (k === "val") return `<td class="n"><b>${inr(s.val)}</b></td>`;
    if (k === "pl") return `<td class="n"><b class="${pcl(s.pl)}">${mny(s.pl)}</b>${showRet && s.inv ? `<small class="${pcl(s.pl)}">${sg(+(s.pl / s.inv * 100).toFixed(2))}%</small>` : ""}</td>`;
    if (k === "ret") return `<td class="n">${s.inv ? pcs(s.pl / s.inv * 100) : ""}</td>`;
    if (k === "day") return `<td class="n">${s.dayBase ? `<span class="${pcl(s.day)}">${mny(s.day)}</span>` : ""}</td>`;
    if (k === "risk") return `<td class="n">${s.risk ? inr(s.risk) + `<small>${s.val ? (s.risk / s.val * 100).toFixed(1) + "% of value" : ""}</small>` : ""}</td>`;
    if (k === "wt") return `<td class="n">${T.val ? (s.val / T.val * 100).toFixed(1) + "%" : ""}</td>`;
    return "<td></td>"; }).join("")}</tr>`;
  const rowsHtml = (rows) => rows.map((r) => `<tr class="hrow${EXP.has(r.p.id) ? " open" : ""}">${cols.map(([k]) => hCell(k, r, T.val, showRet)).join("")}</tr>${EXP.has(r.p.id) ? `<tr class="exp"><td colspan="${n}">${pdetail(r.p, r.c)}${typeof scrIns === "function" ? scrIns(r.p.symbol, r.p.exchange) : ""}</td></tr>` : ""}`).join("");
  let body;
  if (HS.group === "strategy") {
    const G = new Map(); hSorted(oc).forEach((r) => { const k = hSid(r.p); if (!G.has(k)) G.set(k, []); G.get(k).push(r); });
    body = [...G.entries()].sort((a, b) => sum(b[1]).val - sum(a[1]).val).map(([sid, rows]) => {
      const A = lv(rows[0].p).A, s = typeof exStrat === "function" ? exStrat(sid) : null;
      const why = `<small class="hgr">${A && A.rule_label ? `One exit rule for every share bought under this strategy: ${esc(A.rule_label.replace(/, sell after (\d+) trading days at the latest/, ", sold after $1 trading days at most"))}` : ""}${A && /ATR/.test(A.rule_label || "") && rows.length > 1 ? ". ATR is each share's own average daily move, so the same rule gives each share a different distance" : ""}</small>`;
      return agg(sum(rows), `<b>${esc(hStratName(sid))}</b><small>${rows.length} holding${rows.length > 1 ? "s" : ""}</small>`, "hgrp") + `<tr class="hgrn"><td colspan="${n}">${why}</td></tr>` + rowsHtml(rows);
    }).join("");
  } else body = rowsHtml(hSorted(oc));
  return `<div class="ptable"><div class="tw htw"><table class="pt ht"><thead><tr>${th}</tr></thead><tbody>${body}${agg(T, "Total", "tot", `<small>${oc.length} holding${oc.length > 1 ? "s" : ""}</small>`)}</tbody></table></div></div>`;
}
/* toolbar above the table: group, columns, download */
function hTools() {
  const chk = HC.filter((c) => c[2] > 0).map((c) => `<label><input type="checkbox" ${hOn(c) ? "checked" : ""} onchange="hCol('${c[0]}',this.checked)"> ${c[1]}</label>`).join("");
  return `<div class="htools"><span class="seg2 hseg" role="group" aria-label="Group holdings"><button type="button" aria-pressed="${HS.group !== "strategy"}" onclick="hGroup('none')">All holdings</button><button type="button" aria-pressed="${HS.group === "strategy"}" onclick="hGroup('strategy')">By strategy</button></span>
    <details class="hcols"><summary class="btn sm">Columns</summary><div class="hcolp">${chk}<button type="button" class="ent" onclick="hColsReset()">Fit to screen</button></div></details>
    <button type="button" class="btn sm" onclick="hCsv()">Download CSV</button>${HS.k !== "attention" ? `<button type="button" class="ent" onclick="HS.k='attention';hSave();render()">Clear sort</button>` : ""}</div>`;
}
function hCsv() {
  const rows = POS.map((p) => ({ p, c: calc(p) })).filter((x) => x.c.open), tv = rows.reduce((a, r) => a + r.c.value, 0);
  const H = ["Symbol", "Exchange", "Company", "Strategy", "Qty", "Avg cost", "LTP", "Price as of", "Invested", "Current value", "P&L", "Return %", "Today", "Weight %", "Stop loss", "Stop type", "Risk to stop", "Target", "Days left", "Status", "First bought"];
  const q = (x) => { const s = x == null ? "" : String(x); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }, r2 = (x) => (x == null ? "" : Math.round(x * 100) / 100);
  const lines = [H.join(",")].concat(rows.map((r) => { const { p, c } = r, v = lv(p); return [p.symbol, p.exchange, pName(p, c.q), hStratName(hSid(p)), c.L.qty, r2(c.L.avg), r2(c.px), pxSrc(p, c.q), r2(c.invested), r2(c.value), r2(c.unreal), r2(c.unrealPct), r2(c.day), tv ? r2(c.value / tv * 100) : "", r2(v.sl), v.slAuto ? "automatic" : "yours", r2(hRisk(r)), r2(v.tg), v.A ? v.A.days_left : "", c.st ? c.st[0] : "", c.L.since].map(q).join(","); }));
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = "holdings-" + todayStr() + ".csv"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
