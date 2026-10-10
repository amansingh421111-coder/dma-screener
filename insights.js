/* Insights tab: market and stock readings tied to the NISM workbook sections they come from.
   Data: /insights.json (market, sectors, world, headlines), /fund.json (covered stocks: technical + financial numbers),
   /api/dma?a=chart (price history for any other stock), /api/dma?a=news (live headlines for one company).
   Readings describe numbers and what the cited NISM text says such numbers usually indicate. No buy/sell verdicts. */
(function () {
  const css = `
.in-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:4px 0 12px}.in-head h2{margin:0;font-size:20px}.in-head p{margin:4px 0 0;color:var(--mute);font-size:13.5px;max-width:860px}
.in-tabs{display:flex;gap:6px;flex-wrap:wrap}.chip.on,.chip[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.in-box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}.in-box h3{margin:0 0 4px;font-size:15.5px}.in-box>p.m{margin:0 0 10px}
.in-eic{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}.in-eic div{border:1px solid var(--line);border-radius:10px;padding:8px 10px;background:var(--card);font-size:13px}.in-eic b{display:block;font-size:13.5px}
.in-r{list-style:none;margin:0;padding:0}.in-r li{display:grid;grid-template-columns:118px 1fr;gap:10px;padding:9px 0;border-top:1px solid var(--line);font-size:14px;line-height:1.45}.in-r li:first-child{border-top:0}
.in-tone{font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:99px;text-align:center;align-self:start;white-space:nowrap}.in-tone.pos{background:var(--buy-bg);color:var(--buy)}.in-tone.neg{background:var(--sell-bg);color:var(--sell)}.in-tone.neu{background:var(--line);color:var(--mute)}
.in-area{font-size:11.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em;display:block;margin-bottom:2px}
.in-ref{display:inline-block;margin-top:4px;font-size:12px;color:var(--accent);background:none;border:0;padding:0;cursor:pointer;text-align:left;font:inherit;font-size:12px}
.in-says{margin-top:5px;font-size:12.5px;color:var(--mute);border-left:3px solid var(--line);padding:4px 0 4px 9px}
.in-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}.in-t{border:1px solid var(--line);border-radius:10px;padding:9px 11px;background:var(--card)}
.in-t .nm{font-size:12.5px;color:var(--mute)}.in-t .v{font-size:17px;font-weight:700;margin:2px 0}.in-t .ch{font-size:12px;display:flex;gap:8px;flex-wrap:wrap}.in-t svg{display:block;width:100%;height:30px;margin-top:4px}
.in-news{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}.in-n{list-style:none;margin:0;padding:0}.in-n li{padding:8px 0;border-top:1px solid var(--line);font-size:13.5px;line-height:1.4}.in-n li:first-child{border-top:0}
.in-n a{color:var(--ink);text-decoration:none;font-weight:500}.in-n a:hover{text-decoration:underline}.in-n .mt{font-size:12px;color:var(--mute);margin-top:2px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.in-tag{font-size:11px;padding:1px 7px;border-radius:99px;background:var(--line);color:var(--mute)}
.in-note{font-size:12.5px;color:var(--mute);background:var(--bg);border-radius:8px;padding:8px 10px;margin-bottom:10px}
.in-search{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}.in-search input{flex:1;min-width:180px;width:auto}.in-search select{width:auto;flex:0 0 auto}.in-search .btn{flex:0 0 auto}.in-quick{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 2px}
.in-sh{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}.in-sh h3{font-size:19px;margin:0}.in-sh .px{font-size:20px;font-weight:700}
.in-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}
.in-tally{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.in-lv{font-size:13px;color:var(--mute)}
.nw-sec{margin-top:14px}.nw-live{display:inline-flex;align-items:center;gap:5px;font-weight:700;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin-right:6px}.nw-live:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--mute)}.nw-live.on{color:var(--buy)}.nw-live.on:before{background:var(--buy);box-shadow:0 0 0 3px var(--buy-bg)}
.nw-rf{font:inherit;font-size:12px;margin-left:6px;border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:6px;padding:1px 8px;cursor:pointer}
.nw-seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:4px}.nw-seg button{font:inherit;font-size:12.5px;border:0;background:var(--card);color:var(--mute);padding:5px 11px;cursor:pointer}.nw-seg button[aria-pressed=true]{background:var(--accent);color:#fff;font-weight:600}.nw-lbl{font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin-bottom:4px}
.nw-list{list-style:none;margin:0;padding:0}.nw-row{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)}.nw-row:first-child{border-top:0}
.nw-num{flex:0 0 22px;font-size:15px;font-weight:700;color:var(--mute);text-align:right;line-height:1.35}.nw-body{min-width:0;flex:1}
.nw-t{color:var(--ink);text-decoration:none;font-size:14.5px;font-weight:600;line-height:1.35}.nw-t:hover{text-decoration:underline}
.nw-meta{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:3px;font-size:12px;color:var(--mute)}.nw-meta>span+span:before{content:"·";margin-right:10px;opacity:.6}.nw-sub{margin-top:1px;opacity:.9}.nw-src{font-weight:600;color:var(--ink);opacity:.8}
.nw-cos{display:inline-flex;gap:4px}.nw-co{font:inherit;font-size:11.5px;font-weight:600;border:1px solid var(--line);background:var(--bg);color:var(--accent);border-radius:6px;padding:0 6px;cursor:pointer}
.nw-tabs{display:flex;gap:2px;overflow-x:auto;border-bottom:1px solid var(--line);scrollbar-width:thin}.nw-tab{font:inherit;font-size:13px;white-space:nowrap;background:none;border:0;border-bottom:2px solid transparent;color:var(--mute);padding:8px 10px;cursor:pointer}
.nw-tab span{font-size:11.5px;opacity:.7;margin-left:3px}.nw-tab[aria-selected=true]{color:var(--ink);border-bottom-color:var(--accent);font-weight:600}
.nw-panel{padding-top:10px}.nw-why{font-size:13px;background:var(--bg);border-radius:8px;padding:9px 11px;margin-bottom:6px;line-height:1.45}
.nw-people{display:flex;gap:4px;flex-wrap:wrap;margin:8px 0 2px}.nw-pp{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;padding:3px 9px;cursor:pointer}.nw-pp.on{border-color:var(--accent);color:var(--accent);font-weight:600}
.nw-foot{margin-top:12px;font-size:12px;color:var(--mute);border-top:1px solid var(--line);padding-top:9px;line-height:1.5}
@media(max-width:600px){.nw-num{flex-basis:16px;font-size:13.5px}.nw-t{font-size:14px}.in-r li{grid-template-columns:1fr;gap:4px}.in-r li .in-tone{justify-self:start}.in-eic{grid-template-columns:1fr}.in-cols{grid-template-columns:1fr}.in-news{grid-template-columns:1fr}}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
})();

let INS = null, FUND = null, DEEPI = null, BSEU = null, LIVE = null, INAMES = null, CMATCH = null, LIVET = null;
async function loadFeed(fresh) {
  if (IV.feedBusy) return; IV.feedBusy = true; if (fresh) render();
  try {
    if (INAMES === null) { INAMES = {}; try { const r = await fetch("/names.json", { cache: "no-cache" }); if (r.ok) INAMES = await r.json(); } catch (e) {} CMATCH = inMatcher(INAMES); }
    const r = await fetch("/api/dma?a=feed" + (fresh ? "&fresh=1" : "")), j = await r.json();
    if (r.ok && j.themes) { LIVE = j; IV.feedErr = ""; } else IV.feedErr = j.error || "Live news unavailable.";
  } catch (e) { IV.feedErr = "Live news unavailable."; }
  IV.feedBusy = false; if (view_ === "ins") render(); inSchedule();
}
function inSchedule() {   // refresh while the tab is open: every 5 minutes in market hours, hourly otherwise
  clearTimeout(LIVET); const m = LIVE && LIVE.refresh_min ? LIVE.refresh_min : 5;
  LIVET = setTimeout(() => { if (view_ === "ins" && !document.hidden) { loadFeed(); MKT = null; loadMkt(); } else inSchedule(); }, m * 60000);
}
function inMatcher(names) {
  const stop = new Set("india indian bank power energy capital finance industries global international national general united steel motors life money gold silver oil gas trade home first star sun".split(" "));
  const P = [], firsts = new Set(), esc2 = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const [sym, nm] of Object.entries(names || {})) {
    const base = nm.replace(/\b(limited|ltd\.?|company|corporation|corp\.?|co\.|inc\.?|\(india\)|india)\b/gi, "").replace(/^[\s.,&-]+|[\s.,&-]+$/g, "").replace(/\s+/g, " ");
    const w = base.split(" ").filter(Boolean); let c = w.length >= 3 && w.slice(0, 2).join(" ").length < 9 ? w.slice(0, 3).join(" ") : w.length >= 2 ? w.slice(0, 2).join(" ") : base;
    if (/ (of|&|and)$/.test(c)) c = w.slice(0, 3).join(" ");
    if (c.length >= 5 && !stop.has(c.toLowerCase()) && !/ (of|&|and)$/.test(c)) P.push([sym, new RegExp("\\b" + esc2(c) + "\\b")]);
    if (sym.length >= 3 && /^[A-Z]+$/.test(sym) && !stop.has(sym.toLowerCase())) P.push([sym, new RegExp("\\b" + sym + "\\b")]);
    const generic = w.length >= 2 && /^(industries|enterprises|group|holdings|ventures)$/i.test(w[1]);
    if (generic && w[0].length >= 5 && /^[A-Z]/.test(w[0]) && !firsts.has(w[0])) { firsts.add(w[0]); P.push([sym, new RegExp("\\b" + esc2(w[0]) + "\\b(?! (Power|Capital|Infra|Home|Retail|Securities|Finance))")]); }
  }
  return (t, who) => { const h = []; for (const [s, r] of P) if (!h.includes(s) && r.test(t)) h.push(s);
    for (const [n, s] of (LIVE && LIVE.owners) || []) if ((who || []).includes(n) && names[s] && !h.includes(s)) h.push(s); return h.slice(0, 4); };
}
const IV = { theme: "", who: "", list: "top", allTheme: false, feedBusy: false, feedErr: "", tab: "market", sym: "", ex: "NSE", open: new Set(), nf: { market: "", global: "" }, chart: {}, news: {}, busy: false, err: "" };
async function loadIns() {
  if (INS !== null) return; INS = {};
  try { const r = await fetch("/insights.json", { cache: "no-cache" }); if (r.ok) INS = await r.json(); } catch (e) {}
  render();
}
async function loadFund() {
  if (FUND !== null) return; FUND = {};
  try { const r = await fetch("/fund.json", { cache: "no-cache" }); if (r.ok) FUND = await r.json(); } catch (e) {}
  try { const r = await fetch("/dma44_deep.json", { cache: "no-cache" }); if (r.ok) DEEPI = await r.json(); } catch (e) {}
  render();
}
const inNum = (v, d = 1) => (v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const inPct = (v, d = 1) => (v == null || !isFinite(v) ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%");
const inCl = (v) => (v == null ? "" : v > 0 ? "sx-pos" : v < 0 ? "sx-neg" : "");
const inAgo = (iso) => { if (!iso) return ""; const m = (Date.now() - new Date(iso)) / 6e4; return m < 60 ? Math.max(1, Math.round(m)) + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago"; };
const TONE = { pos: "Supportive", neg: "Caution", neu: "Neutral" };
function inRefBtn(key, id) {
  const R = (INS && INS.refs) || {}, r = R[key]; if (!r) return "";
  const open = IV.open.has(id);
  return `<button type="button" class="in-ref" onclick="inTog('${id}')">${esc(r.src)} ${open ? "▴" : "▾"}</button>${open ? `<div class="in-says">What it says: ${esc(r.says)}</div>` : ""}`;
}
function inTog(id) { IV.open.has(id) ? IV.open.delete(id) : IV.open.add(id); render(); }
function inReadings(list, pre) {
  if (!list.length) return `<p class="m">No readings.</p>`;
  return `<ul class="in-r">${list.map((x, i) => `<li><span class="in-tone ${x.tone}">${TONE[x.tone] || "Neutral"}</span><div>${x.area ? `<span class="in-area">${esc(x.area)}</span>` : ""}${x.html || esc(x.text)}${x.ref ? `<div>${inRefBtn(x.ref, pre + i)}</div>` : x.src ? `<div class="in-lv">${esc(x.src)}</div>` : `<div class="in-lv">Data only; no NISM rule is attached to this number.</div>`}</div></li>`).join("")}</ul>`;
}
function inSpark(a) {
  if (!a || a.length < 2) return ""; const mn = Math.min(...a), mx = Math.max(...a), w = 100, h = 30, k = (mx - mn) || 1;
  const pts = a.map((v, i) => `${(i / (a.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / k * (h - 4)).toFixed(1)}`).join(" ");
  const up = a[a.length - 1] >= a[0];
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="${up ? "var(--buy)" : "var(--sell)"}" stroke-width="1.6" points="${pts}" vector-effect="non-scaling-stroke"/></svg>`;
}
function inTile(x) {
  const lv = x.k === "^TNX" ? inNum(x.last, 2) + "%" : x.k === "INR=X" ? "₹" + inNum(x.last, 2) : inNum(x.last, x.last < 100 ? 2 : 0);
  return `<div class="in-t"><div class="nm">${esc(x.name)}</div><div class="v">${lv}</div><div class="ch"><span class="${inCl(x.d1)}">Day ${inPct(x.d1)}</span><span class="${inCl(x.m1)}">1M ${inPct(x.m1)}</span><span class="${inCl(x.y1)}">1Y ${inPct(x.y1)}</span></div>
  <div class="ch" style="margin-top:2px"><span class="sx-mut">${x.vs200 == null ? "" : (x.vs200 >= 0 ? "Above" : "Below") + " 200-day avg (" + inPct(x.vs200) + ")"}</span></div>${inSpark(x.spark)}</div>`;
}
function inNewsList(items) {
  const shown = (items || []).slice(0, 25);
  return shown.length ? `<ol class="nw-list">${shown.map((x) => inStoryRow({ t: x.t, u: x.u, s: x.s, d: x.d, n: 1, tag: (x.g || []).join(" · ") })).join("")}</ol>` : `<p class="m">No headlines in the last 14 days.</p>`;
}
function inNF(k, t) { IV.nf[k] = t; render(); }
function inStoryRow(x, num) {
  const also = x.also && x.also.length ? x.also.map((a) => a.s).join(", ") : "";
  const cos = x.co && x.co.length ? x.co : CMATCH ? CMATCH(x.t, x.who) : [];
  const co = cos.map((c) => `<button type="button" class="nw-co" onclick="inPick('${esc(c)}','NSE')">${esc(c)}</button>`).join("");
  return `<li class="nw-row">${num ? `<span class="nw-num">${num}</span>` : ""}<div class="nw-body"><a class="nw-t" href="${esc(x.u)}" target="_blank" rel="noopener noreferrer">${esc(x.t)}</a>
  <div class="nw-meta"><span class="nw-src">${esc(x.s || "")}</span>${x.d ? `<span>${inAgo(x.d)}</span>` : ""}${x.n > 1 ? `<span title="${esc(also)}">${x.n} outlets</span>` : ""}</div>${x.tag || (x.who && x.who.length) || co ? `<div class="nw-meta nw-sub">${x.tag ? `<span>${esc(x.tag)}</span>` : ""}${x.who && x.who.length ? `<span>${esc(x.who.join(", "))}</span>` : ""}${co ? `<span class="nw-cos">${co}</span>` : ""}</div>` : ""}</div></li>`;
}
function inNewsPro(N0) {
  if (LIVE === null && !IV.feedBusy) loadFeed();
  const N = LIVE || N0; if (!N || !N.themes) return `<div class="in-box"><h3>Market-moving news</h3><p class="m">${esc(IV.feedErr || "Loading live headlines…")}</p></div>`;
  const th = N.themes.filter((t) => t.stories.length), cur = th.find((t) => t.id === IV.theme) || th[0], nm = Object.fromEntries(N.themes.map((t) => [t.id, t.name]));
  const lst = IV.list === "latest" ? N.latest || [] : N.top || [];
  const top = lst.map((x, i) => inStoryRow(Object.assign({}, x, { tag: nm[x.th] }), IV.list === "latest" ? 0 : i + 1)).join("");
  let stories = cur ? cur.stories : [], more = "";
  if (cur && cur.id === "people" && IV.who) stories = stories.filter((x) => (x.who || []).includes(IV.who));
  const people = cur && cur.id === "people" && N.people && N.people.length ? `<div class="nw-people">${[["", "Everyone"]].concat(N.people.map((p) => [p.name, `${p.name} (${p.n != null ? p.n : p.stories.length})`])).map(([k, l]) => `<button type="button" class="nw-pp${(IV.who || "") === k ? " on" : ""}" onclick="IV.who='${esc(k)}';IV.allTheme=false;render()">${esc(l)}</button>`).join("")}</div>` : "";
  if (!IV.allTheme && stories.length > 12) { more = `<button type="button" class="btn sm" style="margin-top:8px" onclick="IV.allTheme=true;render()">Show all ${stories.length}${cur.total > stories.length ? " of " + cur.total : ""}</button>`; stories = stories.slice(0, 12); }
  const status = N.live ? `<span class="nw-live${N.market_open ? " on" : ""}">${N.market_open ? "Live" : "Market closed"}</span> Updated ${inAgo(N.updated)} · refreshes every ${N.refresh_min === 60 ? "hour" : N.refresh_min + " minutes"}${N.market_open ? " during market hours" : " until the market opens"} · ${N.pool || 0} headlines from the last ${N.days} days <button type="button" class="nw-rf" onclick="loadFeed(true)" ${IV.feedBusy ? "disabled" : ""}>${IV.feedBusy ? "Refreshing…" : "Refresh"}</button>` : `Updated ${inAgo(N.updated)} (saved copy; live news unavailable${IV.feedErr ? ": " + esc(IV.feedErr) : ""})`;
  return `<div class="in-box nw"><div class="nw-hd"><div><h3>Market-moving news</h3><p class="m" style="margin:2px 0 0">${status}</p></div></div>
  <div class="nw-sec"><div class="nw-seg"><button type="button" aria-pressed="${IV.list !== "latest"}" onclick="IV.list='top';render()">Most widely reported (48 h)</button><button type="button" aria-pressed="${IV.list === "latest"}" onclick="IV.list='latest';render()">Latest</button></div><ol class="nw-list">${top || `<li class="m">No stories.</li>`}</ol></div>
  <div class="nw-sec"><div class="nw-lbl">By theme</div><div class="nw-tabs" role="tablist">${th.map((t) => `<button role="tab" aria-selected="${t === cur}" class="nw-tab" onclick="IV.theme='${t.id}';IV.who='';IV.allTheme=false;render()" title="${esc(t.name)}">${esc(t.short || t.name)} <span>${t.total || t.stories.length}</span></button>`).join("")}</div>
  ${cur ? `<div class="nw-panel"><div class="nw-why"><div><b>${esc(cur.name)}: how it reaches share prices.</b> ${esc(cur.why)}</div><div class="in-lv" style="margin-top:3px">Most exposed: ${esc(cur.sectors)}</div><div>${inRefBtn(cur.ref, "th-" + cur.id)}</div></div>${people}<ol class="nw-list">${stories.map((x) => inStoryRow(x)).join("")}</ol>${more}</div>` : ""}</div>
  <div class="nw-foot">${esc(N.note || "")} ${inRefBtn("emh", "n-emh")} ${inRefBtn("bias", "n-bias")}</div></div>`;
}
function inNewsNote() {
  return `<div class="in-note">Headlines are collected automatically and tagged by keywords; they are not checked or summarised. Two NISM points worth keeping in mind: news that is already public is quickly reflected in prices (semi-strong efficiency), and reading only the headlines that agree with you is confirmation bias. ${inRefBtn("emh", "n-emh")} ${inRefBtn("bias", "n-bias")}</div>`;
}

function renderIns() {
  const el = $("vIns"); if (!el) return;
  if (INS === null) { loadIns(); el.innerHTML = `<div class="empty">Loading…</div>`; return; }
  const tabs = `<div class="in-tabs"><button class="chip" aria-pressed="${IV.tab === "market"}" onclick="inTab('market')">Market</button><button class="chip" aria-pressed="${IV.tab === "stock"}" onclick="inTab('stock')">A stock</button><button class="chip" aria-pressed="${IV.tab === "src"}" onclick="inTab('src')">Where the readings come from</button></div>`;
  const head = `<div class="in-head"><div><h2>Market and stock insights</h2><p>Numbers, headlines and rule-based readings. Every reading names the NISM workbook section its rule comes from; tap the reference to see what that section says. This is a personal research aid, not a research report or a recommendation.${INS.updated ? ` Market data updated ${new Date(INS.updated).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })} IST.` : ""}</p></div>${tabs}</div>`;
  if (!INS.groups) { el.innerHTML = head + `<div class="empty">No market data yet. It is built by the “insights” workflow on GitHub (weekday mornings and evenings).</div>`; return; }
  el.innerHTML = head + (IV.tab === "market" ? inMarket() : IV.tab === "stock" ? inStock() : inSources());
  const tb = el.querySelector('.nw-tab[aria-selected="true"]'); if (tb) tb.parentElement.scrollLeft = Math.max(0, tb.offsetLeft - 24);
}
function inTab(t) { IV.tab = t; if (t === "stock") loadFund(); render(); }

function inMarket() {
  if (MKT === null && !IV.mktBusy) loadMkt();
  const I = INS, L = mkLive(), cov = (I.sectors || []).filter((x) => x.kind !== "index");
  const R = L ? mkReadings(L.M, cov, I.breadth, LIVE) : I.readings || [];
  const groupsSrc = L ? L.groups : I.groups || [], secSrc = L ? cov.concat(L.sidx) : I.sectors || [];
  const asOf = L ? `Live prices (about 15 minutes delayed), updated ${inAgo(MKT.updated)}; they refresh every ${MKT.market_open ? "5 minutes during market hours" : "hour while the market is closed"}.` : `Prices from the last scheduled update (${inAgo(I.updated)}).`;
  const eic = `<div class="in-eic"><div><b>1. Economy and the world</b>Rates, currency, crude, global markets and politics</div><div><b>2. Sectors</b>Which industries are leading or lagging the Nifty 50</div><div><b>3. Companies</b>Open “A stock” for one company's readings</div></div>`;
  const read = `<div class="in-box"><h3>Readings now</h3><p class="m">${asOf} Each line is a fixed rule applied to the numbers below. “Supportive” or “Caution” is what the cited NISM text says such a reading usually indicates, not a forecast.</p>${inReadings(R, "m")}</div>`;
  const grp = groupsSrc.map((g) => `<div class="in-box"><h3>${esc(g.name)}</h3><div class="in-grid">${g.items.map(inTile).join("")}</div></div>`).join("");
  const sec = secSrc.slice().sort((a, b) => (b.rel3 ?? -99) - (a.rel3 ?? -99));
  const secT = sec.length ? `<div class="in-box"><h3>Sectors against the Nifty 50</h3><p class="m">Relative strength: a sector's return minus the Nifty 50's over the same period; above zero means it did better than the index. “Covered stocks” rows use the median return of the covered companies in that sector (sector names from Yahoo Finance); “index” rows are NSE sector indices. ${inRefBtn("rsc", "s-rsc")}</p><div class="sx-w"><table class="sx2" style="min-width:620px"><thead><tr><th>Sector</th><th>Based on</th><th>1 month</th><th>3 months</th><th>vs Nifty, 1 month</th><th>vs Nifty, 3 months</th><th>Above 200-day average</th></tr></thead><tbody>${sec.map((x) => `<tr><td>${esc(x.name)}</td><td class="sx-mut">${x.kind === "index" ? "NSE index" : x.n + " covered stocks"}</td><td class="${inCl(x.m1)}">${inPct(x.m1)}</td><td class="${inCl(x.m3)}">${inPct(x.m3)}</td><td class="${inCl(x.rel1)}">${inPct(x.rel1)}</td><td class="${inCl(x.rel3)}">${inPct(x.rel3)}</td><td>${x.kind === "index" ? (x.vs200 == null ? "–" : (x.vs200 >= 0 ? "Yes, " : "No, ") + inPct(x.vs200)) : inNum(x.above200, 0) + "% of stocks"}</td></tr>`).join("")}</tbody></table></div></div>` : "";
  const mp = I.market_pe, br = I.breadth;
  const val = `<div class="in-box"><h3>Valuation and breadth</h3><div class="in-grid">${mp ? `<div class="in-t"><div class="nm">P/E of the ${mp.n} largest covered companies (combined)</div><div class="v">${inNum(mp.pe, 1)}</div><div class="ch">Earnings yield ${inNum(100 / mp.pe, 2)}%</div></div>` : ""}${br ? `<div class="in-t"><div class="nm">Covered stocks above their 200-day average</div><div class="v">${inNum(br.above200, 0)}%</div><div class="ch">Above 50-day: ${inNum(br.above50, 0)}% · ${br.n} stocks</div></div>` : ""}</div>
  <p class="m" style="margin-top:8px">NISM compares equity earnings or dividend yields with bond yields: when equity yields are well above bond yields, equities are cheap, and in bull markets they fall below bond yields. Compare the earnings yield above with the current 10-year government bond yield. ${inRefBtn("dy", "v-dy")}</p></div>`;
  return eic + read + inNewsPro(I.news) + grp + secT + val;
}

function inSources() {
  const R = (INS && INS.refs) || {};
  return `<div class="in-box"><h3>Where the readings come from</h3><p class="m">The rules on this page paraphrase these sections of the NISM certification workbooks you provided. Where a number has no NISM rule (India VIX, market breadth, the 52-week range), the page shows it as data only. Thresholds such as RSI 70/30, ADX 25, debt/equity 1 and PEG 1 are the ones the workbooks state.</p>
  <ul class="in-r">${Object.entries(R).map(([k, r]) => `<li><span class="in-tone neu">${esc(k)}</span><div><b>${esc(r.src)}</b><div class="in-says" style="border:0;padding-left:0">${esc(r.says)}</div></div></li>`).join("")}</ul></div>
  <div class="in-box"><h3>What this page is not</h3><p class="m" style="margin:0">Under SEBI's Research Analyst rules (NISM Series XV, Chapter 14), research reports and recommendations for others need a registered analyst, disclosures and conflict checks. This page only applies written rules to public numbers for your own use; it gives no price targets or buy/sell calls, and headlines are not verified.</p></div>`;
}


/* ---------- live market tiles and readings (same rules as insights.py, recomputed in the browser) ---------- */
let MKT = null;
const MK_NAMES = { "^NSEI": "Nifty 50", "^BSESN": "Sensex", "^NSEBANK": "Nifty Bank", "^NSEMDCP50": "Nifty Midcap 50", "^INDIAVIX": "India VIX", "^GSPC": "S&P 500 (US)", "^IXIC": "Nasdaq (US)",
  "^FTSE": "FTSE 100 (UK)", "^GDAXI": "DAX (Germany)", "^N225": "Nikkei 225 (Japan)", "^HSI": "Hang Seng (Hong Kong)", "000001.SS": "Shanghai Composite (China)", "INR=X": "US dollar in rupees",
  "DX-Y.NYB": "US dollar index", "BZ=F": "Brent crude ($ a barrel)", "GC=F": "Gold ($ an ounce)", "HG=F": "Copper ($ a pound)", "^TNX": "US 10-year bond yield (%)",
  "^CNXIT": "IT", "^CNXAUTO": "Auto", "^CNXFMCG": "FMCG", "^CNXPHARMA": "Pharma", "^CNXMETAL": "Metal", "^CNXREALTY": "Realty", "^CNXENERGY": "Energy", "^CNXPSUBANK": "PSU banks", "^CNXINFRA": "Infrastructure", "^CNXMEDIA": "Media", "NIFTY_FIN_SERVICE.NS": "Financial services" };
const MK_GROUPS = [["India", ["^NSEI", "^BSESN", "^NSEBANK", "^NSEMDCP50", "^INDIAVIX"]], ["World markets", ["^GSPC", "^IXIC", "^FTSE", "^GDAXI", "^N225", "^HSI", "000001.SS"]], ["Currency, commodities and rates", ["INR=X", "DX-Y.NYB", "BZ=F", "GC=F", "HG=F", "^TNX"]]];
async function loadMkt() {
  if (IV.mktBusy) return; IV.mktBusy = true;
  try { const r = await fetch("/api/dma?a=mkt"), j = await r.json(); if (r.ok && j.series) MKT = j; } catch (e) {}
  IV.mktBusy = false; if (view_ === "ins") render();
}
function mkStats(c) {
  const n = c.length, L = c[n - 1], r2 = (x) => (x == null || !isFinite(x) ? null : Math.round(x * 10000) / 10000), ret = (k) => (n > k && c[n - 1 - k] ? r2((L / c[n - 1 - k] - 1) * 100) : null);
  const m50 = inSma(c, 50), m200 = inSma(c, 200), y = c.slice(-252);
  return { last: r2(L), d1: ret(1), w1: ret(5), m1: ret(21), m3: ret(63), y1: ret(252), vs50: n >= 50 ? r2((L / m50[n - 1] - 1) * 100) : null, vs200: n >= 200 ? r2((L / m200[n - 1] - 1) * 100) : null,
    s200: n >= 221 ? r2((m200[n - 1] / m200[n - 21] - 1) * 100) : null, hi52: r2((L / Math.max(...y) - 1) * 100), lo52: r2((L / Math.min(...y) - 1) * 100), spark: c.slice(-60) };
}
function mkLive() {   // returns {M, groups, sectors} from the live series, or null
  if (!MKT || !MKT.series) return null;
  const M = {}; for (const x of MKT.series) if (x.c && x.c.length > 30) M[x.t] = Object.assign(mkStats(x.c), { date: x.d });
  const ns = MKT.series.find((x) => x.t === "^NSEI");
  if (ns) { const c = ns.c, up = [null], dn = [null]; for (let i = 1; i < c.length; i++) { const d = c[i] - c[i - 1]; up.push(Math.max(d, 0)); dn.push(Math.max(-d, 0)); }
    const au = inEma(up, 14, 1 / 14), ad = inEma(dn, 14, 1 / 14), e12 = inEma(c, 12), e26 = inEma(c, 26), mc = c.map((_, i) => e12[i] - e26[i]), sg = inEma(mc, 9), n = c.length;
    M._nifty = { rsi: ad[n - 1] ? 100 - 100 / (1 + au[n - 1] / ad[n - 1]) : null, macd: mc[n - 1], msig: sg[n - 1] }; }
  const groups = MK_GROUPS.map(([name, ks]) => ({ name, items: ks.filter((k) => M[k]).map((k) => Object.assign({ k, name: MK_NAMES[k] }, M[k])) }));
  const N = M["^NSEI"] || {};
  const sidx = Object.keys(MK_NAMES).filter((k) => k.startsWith("^CNX") || k === "NIFTY_FIN_SERVICE.NS" || k === "^NSEBANK").filter((k) => M[k]).map((k) => ({ k, name: k === "^NSEBANK" ? "Banks" : MK_NAMES[k], kind: "index", m1: M[k].m1, m3: M[k].m3, vs200: M[k].vs200,
    rel1: M[k].m1 != null && N.m1 != null ? M[k].m1 - N.m1 : null, rel3: M[k].m3 != null && N.m3 != null ? M[k].m3 - N.m3 : null }));
  return { M, groups, sidx };
}
function mkReadings(M, sectCov, breadth, feed) {
  const R = [], g = (k) => M[k] || {}, ob = (area, text, tone, ref) => R.push({ area, text, tone, ref }), f1 = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);
  const n = g("^NSEI"), sx = g("^BSESN");
  if (n.vs200 != null) { const up = n.vs200 > 0, ris = (n.s200 || 0) > 0, st = up && ris ? "uptrend (bull)" : !up && !ris ? "downtrend (bear)" : "mixed / sideways";
    ob("Trend", `Nifty 50 is ${Math.abs(n.vs200).toFixed(1)}% ${up ? "above" : "below"} its 200-day average, and that average is ${ris ? "rising" : "falling"} (${f1(n.s200 || 0)}% over 20 days). By the moving-average test the primary trend reads as ${st}.`, up && ris ? "pos" : !up && !ris ? "neg" : "neu", "trend"); }
  if (n.m1 != null && sx.m1 != null) ob("Trend", `Over one month the Nifty 50 moved ${f1(n.m1)}% and the Sensex ${f1(sx.m1)}%: ${(n.m1 >= 0) === (sx.m1 >= 0) ? "the two indices confirm each other" : "the two indices disagree, so the move is not confirmed"}.`, "neu", "dow");
  const ni = M._nifty || {};
  if (ni.rsi != null) { const r = ni.rsi; ob("Momentum", `Nifty 50 RSI (14) is ${r.toFixed(0)}. ` + (r > 70 ? "That is above 70, the usual overbought line." : r < 30 ? "That is below 30, the usual oversold line." : r < 44 ? "That is below the 44-45 zone that a bull market rarely falls under." : r > 55 ? "That is above the 50-55 zone that a bear market rarely rises over." : "That is in the middle band (44-55), which by itself does not separate a bull from a bear phase."), r < 44 ? "neg" : r > 55 ? "pos" : "neu", "rsi"); }
  if (ni.macd != null) ob("Momentum", `Nifty 50 MACD is ${ni.macd > ni.msig ? "above" : "below"} its signal line and ${ni.macd > 0 ? "above" : "below"} zero.`, ni.macd > ni.msig && ni.macd > 0 ? "pos" : ni.macd < ni.msig && ni.macd < 0 ? "neg" : "neu", "macd");
  if (breadth) ob("Breadth", `${Math.round(breadth.above200)}% of the ${breadth.n} covered stocks were above their 200-day average and ${Math.round(breadth.above50)}% above their 50-day average at the last close.`, breadth.above200 > 60 ? "pos" : breadth.above200 < 40 ? "neg" : "neu", null);
  const rk = (sectCov || []).filter((x) => x.rel3 != null).sort((a, b) => b.rel3 - a.rel3);
  if (rk.length >= 4) ob("Sectors", `Against the Nifty 50 over 3 months, the strongest sectors were ${rk.slice(0, 3).map((x) => `${x.name} (${f1(x.rel3)}%)`).join(", ")}; the weakest were ${rk.slice(-3).map((x) => `${x.name} (${f1(x.rel3)}%)`).join(", ")}.`, "neu", "rsc");
  const b = g("BZ=F");
  if (b.m1 != null) { const x = b.m1;
    if (x >= 5) ob("Commodities", `Brent crude is up ${x.toFixed(1)}% in a month ($${b.last.toFixed(1)}). Rising crude raises input costs for users such as airlines, paints and logistics and helps oil producers; as an importer, India feels it in fuel prices and inflation.`, "neg", "commod_eq");
    else if (x <= -5) ob("Commodities", `Brent crude is down ${Math.abs(x).toFixed(1)}% in a month ($${b.last.toFixed(1)}). Falling crude lowers input costs for users such as airlines, paints and logistics and squeezes oil producers; for an importer like India it eases fuel prices and inflation.`, "pos", "commod_eq");
    else ob("Commodities", `Brent crude moved ${f1(x)}% in a month ($${b.last.toFixed(1)}), a modest change.`, "neu", "intl"); }
  const u = g("INR=X");
  if (u.m1 != null) { const x = u.m1;
    ob("Currency", x >= 1 ? `The rupee weakened ${x.toFixed(1)}% against the dollar in a month (₹${u.last.toFixed(2)}). A weaker rupee makes imports (crude, capital goods) dearer and helps exporters' rupee earnings.` : x <= -1 ? `The rupee strengthened ${Math.abs(x).toFixed(1)}% against the dollar in a month (₹${u.last.toFixed(2)}). Imports get cheaper; exporters earn fewer rupees per dollar.` : `The rupee was steady against the dollar (${f1(x)}% in a month, ₹${u.last.toFixed(2)}).`, x >= 1 ? "neg" : x <= -1 ? "pos" : "neu", "cad"); }
  const d = g("DX-Y.NYB"); if (d.m1 != null && Math.abs(d.m1) >= 1.5) ob("Currency", `The US dollar index ${d.m1 > 0 ? "rose" : "fell"} ${Math.abs(d.m1).toFixed(1)}% in a month. A ${d.m1 > 0 ? "stronger dollar usually weighs on" : "weaker dollar usually supports"} dollar-priced commodities.`, "neu", "dollar");
  const au = g("GC=F"); if (au.m1 != null && Math.abs(au.m1) >= 4) ob("Commodities", `Gold ${au.m1 > 0 ? "rose" : "fell"} ${Math.abs(au.m1).toFixed(1)}% in a month ($${au.last.toFixed(0)}). Gold is the usual hedge investors turn to when inflation worries rise.`, "neu", "macro_ind");
  const cu = g("HG=F"); if (cu.m1 != null && Math.abs(cu.m1) >= 5) ob("Commodities", `Copper ${cu.m1 > 0 ? "rose" : "fell"} ${Math.abs(cu.m1).toFixed(1)}% in a month. NISM reads a fall in copper as a possible sign of slowing industrial demand, weighing on metal and infrastructure stocks${cu.m1 > 0 ? "; a rise is the opposite reading" : ""}.`, cu.m1 > 0 ? "pos" : "neg", "commod_eq");
  const t = g("^TNX"); if (t.last != null && t.m1 != null) ob("Global rates", `The US 10-year yield is ${t.last.toFixed(2)}% (${f1(t.last * t.m1 / (100 + t.m1) * 100).replace(".0", "")} basis points in a month). Foreign portfolio money, which NISM calls 'hot money' that can leave at any time, watches global rates.`, "neu", "fpi");
  const gl = ["^GSPC", "^IXIC", "^FTSE", "^GDAXI", "^N225", "^HSI", "000001.SS"].map(g), dn = gl.filter((x) => (x.m1 || 0) <= -5).length, upn = gl.filter((x) => (x.m1 || 0) >= 5).length;
  if (dn >= 3) ob("Global", `${dn} of 7 major world indices fell 5% or more in a month. Integrated economies mean trouble in one region spreads to others.`, "neg", "global");
  else if (upn >= 3) ob("Global", `${upn} of 7 major world indices rose 5% or more in a month.`, "pos", "global");
  const vx = g("^INDIAVIX"); if (vx.last != null) ob("Volatility", `India VIX (expected 30-day volatility of the Nifty) is ${vx.last.toFixed(1)}, ${f1(vx.m1 || 0).replace(/\.\d$/, "")}% in a month.`, (vx.m1 || 0) > 20 ? "neg" : "neu", null);
  if (feed && feed.themes) { const cov = feed.themes.filter((x) => ["geo", "trade", "energy", "politics", "people"].includes(x.id)).map((x) => [x.name, x.day || 0]).filter((x) => x[1]).sort((a, b) => b[1] - a[1]).slice(0, 3);
    if (cov.length) ob("Geopolitics", `The busiest world themes in the last 24 hours: ${cov.map(([a, c]) => `${a.toLowerCase()} (${c} stories)`).join(", ")}. Conflicts in oil regions, sanctions and trade wars mainly reach Indian stocks through crude prices, the rupee and supply chains.`, "neu", "geo"); }
  return R;
}

/* ---------- technical numbers computed in the browser (same formulas as insights.py) ---------- */
function inSma(a, n) { const o = new Array(a.length).fill(null); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
function inEma(a, n, alpha) { const k = alpha || 2 / (n + 1), o = new Array(a.length).fill(null); let e = null; for (let i = 0; i < a.length; i++) { const x = a[i]; if (x == null || !isFinite(x)) { o[i] = e; continue; } e = e == null ? x : k * x + (1 - k) * e; o[i] = e; } return o; }
function inTech(S, nifty) {
  const c = S.c, h = S.h, l = S.l, v = S.v, n = c.length; if (n < 60) return null;
  const L = (a) => a[a.length - 1], r2 = (x) => (x == null || !isFinite(x) ? null : Math.round(x * 100) / 100), ret = (k) => (n > k && c[n - 1 - k] ? r2((c[n - 1] / c[n - 1 - k] - 1) * 100) : null);
  const o = { p: r2(c[n - 1]), d1: ret(1), m1: ret(21), m3: ret(63), m6: ret(126), y1: ret(252), date: L(S.dates) };
  for (const k of [20, 44, 50, 200]) { const m = inSma(c, k); o["vs" + k] = n >= k ? r2((c[n - 1] / m[n - 1] - 1) * 100) : null; }
  const m44 = inSma(c, 44), m200 = inSma(c, 200);
  o.s44 = n >= 50 ? r2((m44[n - 1] / m44[n - 6] - 1) * 100) : null; o.s200 = n >= 221 ? r2((m200[n - 1] / m200[n - 21] - 1) * 100) : null;
  const up = [null], dn = [null]; for (let i = 1; i < n; i++) { const d = c[i] - c[i - 1]; up.push(Math.max(d, 0)); dn.push(Math.max(-d, 0)); }
  const au = inEma(up, 14, 1 / 14), ad = inEma(dn, 14, 1 / 14); o.rsi = ad[n - 1] ? r2(100 - 100 / (1 + au[n - 1] / ad[n - 1])) : null;
  const e12 = inEma(c, 12), e26 = inEma(c, 26), macd = c.map((_, i) => e12[i] - e26[i]), sig = inEma(macd, 9);
  o.macd = r2(macd[n - 1]); o.msig = r2(sig[n - 1]); o.mup = macd[n - 1] > macd[n - 2]; o.sup = sig[n - 1] > sig[n - 2];
  const tr = [], pdm = [], mdm = []; for (let i = 0; i < n; i++) { if (i === 0) { tr.push(h[0] - l[0]); pdm.push(0); mdm.push(0); continue; } const u = h[i] - h[i - 1], d = l[i - 1] - l[i]; pdm.push(u > d && u > 0 ? u : 0); mdm.push(d > u && d > 0 ? d : 0); tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1]))); }
  const atrW = inEma(tr, 14, 1 / 14), pS = inEma(pdm, 14, 1 / 14), mS = inEma(mdm, 14, 1 / 14), pdi = pS.map((x, i) => (100 * x) / atrW[i]), mdi = mS.map((x, i) => (100 * x) / atrW[i]);
  const dx = pdi.map((x, i) => (x + mdi[i] ? (100 * Math.abs(x - mdi[i])) / (x + mdi[i]) : null)), adx = inEma(dx, 14, 1 / 14);
  if (n > 40) { o.adx = r2(adx[n - 1]); o.pdi = r2(pdi[n - 1]); o.mdi = r2(mdi[n - 1]); o.adxup = adx[n - 1] > adx[n - 6]; }
  const e13 = L(inEma(c, 13)), e21 = L(inEma(c, 21)), e34 = L(inEma(c, 34)), p = c[n - 1];
  o.ema = p > e13 && e13 > e21 && e21 > e34 ? "up" : p < e13 && e13 < e21 && e21 < e34 ? "down" : "mixed";
  const last252 = c.slice(-252); o.hi52 = r2((p / Math.max(...last252) - 1) * 100); o.lo52 = r2((p / Math.min(...last252) - 1) * 100);
  const pv = v.slice(-21, -1), av = pv.reduce((s, x) => s + x, 0) / pv.length; o.volx = av ? r2(v[n - 1] / av) : null;
  let ob = 0; const obv = c.map((x, i) => (i === 0 ? 0 : (ob += Math.sign(x - c[i - 1]) * v[i]))); const o20 = inSma(obv, 20); o.obv = obv[n - 1] > o20[n - 1];
  const atr = inSma(tr, 14); o.atr = r2((atr[n - 1] / p) * 100);
  o.lo20 = r2(Math.min(...l.slice(-20))); o.hi20 = r2(Math.max(...h.slice(-20)));
  if (nifty && nifty.dates) {
    const map = new Map(nifty.dates.map((d, i) => [d, nifty.close[i]])); let lastN = null; const nn = S.dates.map((d) => { const x = map.get(d); if (x != null) lastN = x; return lastN; });
    const rr = (k) => (n > k && nn[n - 1 - k] && nn[n - 1] ? r2((c[n - 1] / nn[n - 1] / (c[n - 1 - k] / nn[n - 1 - k])) * 100) : null);
    o.rsc = rr(126); o.rsc1y = rr(252);
  }
  return o;
}

/* ---------- readings for one stock ---------- */
function inStockReadings(t, f, sm, mpe, sym) {
  const T = [], F = [], add = (L, area, tone, text, ref) => L.push({ area, tone, text, ref });
  if (t) {
    if (t.vs200 != null) { const up = t.vs200 > 0, ris = (t.s200 || 0) > 0; add(T, "Trend", up && ris ? "pos" : !up && !ris ? "neg" : "neu", `Price is ${Math.abs(t.vs200).toFixed(1)}% ${up ? "above" : "below"} its 200-day average, which is ${ris ? "rising" : "falling"}${t.s200 != null ? ` (${inPct(t.s200)} over 20 days)` : ""}: the long-term trend reads as ${up && ris ? "up" : !up && !ris ? "down" : "mixed"}.`, "trend"); }
    if (t.vs44 != null) { const zone = t.vs44 >= 0 && t.vs44 <= 5 && (t.s44 || 0) > 0; add(T, "44-day average", zone ? "pos" : t.vs44 < 0 && (t.s44 || 0) < 0 ? "neg" : "neu", `Price is ${inPct(t.vs44)} from its 44-day average, which is ${(t.s44 || 0) > 0 ? "rising" : "falling"} (${inPct(t.s44)} over 5 days).${zone ? " That is the 44-DMA buy zone (0 to 5% above a rising average)." : ""}${zone && DEEPI && DEEPI.rows ? inDeepLine(sym) : ""}`, "ma"); }
    if (t.ema) add(T, "Averages 13/21/34", t.ema === "up" ? "pos" : t.ema === "down" ? "neg" : "neu", t.ema === "up" ? "Price is above the 13-day EMA, which is above the 21-day, which is above the 34-day: the uptrend order." : t.ema === "down" ? "Price is below the 13-day EMA, below the 21-day, below the 34-day: the downtrend order." : "The 13/21/34-day EMAs are not in a clean up or down order.", "ma");
    if (t.rsi != null) { const r = t.rsi; add(T, "RSI (14)", r > 70 ? "neg" : r < 30 ? "pos" : r >= 55 ? "pos" : r < 44 ? "neg" : "neu", `RSI is ${r.toFixed(0)}: ${r > 70 ? "above 70, usually called overbought (it can stay there in strong uptrends)" : r < 30 ? "below 30, usually called oversold (it can stay there in strong downtrends)" : r >= 55 ? "above the 50-55 zone that RSI rarely exceeds in a bear phase" : r < 44 ? "below the 44-45 zone that RSI rarely falls under in a bull phase" : "in the 44-55 middle band"}.`, "rsi"); }
    if (t.macd != null) add(T, "MACD", t.macd > t.msig && t.mup && t.sup ? "pos" : t.macd < t.msig && !t.mup && !t.sup ? "neg" : "neu", `MACD is ${t.macd > t.msig ? "above" : "below"} its signal line and ${t.macd > 0 ? "above" : "below"} zero; MACD is ${t.mup ? "rising" : "falling"} and the signal line ${t.sup ? "rising" : "falling"}.`, "macd");
    if (t.adx != null) add(T, "ADX", t.adx >= 25 && t.adxup ? (t.pdi > t.mdi ? "pos" : "neg") : "neu", `ADX is ${t.adx.toFixed(0)} (${t.adxup ? "rising" : "falling"}), +DI ${t.pdi.toFixed(0)} vs −DI ${t.mdi.toFixed(0)}: ${t.adx < 25 ? "a weak or no trend; crossovers are unreliable at this level" : t.adxup ? `a strong trend, ${t.pdi > t.mdi ? "upward" : "downward"} by the DI lines` : "a trend that is losing strength"}.`, "adx");
    if (t.obv != null) add(T, "Volume", t.obv ? "pos" : "neg", `On-balance volume is ${t.obv ? "above" : "below"} its 20-day average${t.volx != null ? `; today's volume was ${t.volx.toFixed(1)}× the 20-day average` : ""}.`, "obv");
    if (t.rsc != null) add(T, "Against the Nifty 50", t.rsc >= 100 ? "pos" : "neg", `Relative strength over 6 months is ${t.rsc.toFixed(0)} (100 = same as the Nifty 50)${t.rsc1y != null ? `, over 1 year ${t.rsc1y.toFixed(0)}` : ""}: it has ${t.rsc >= 100 ? "outperformed" : "underperformed"} the index.`, "rsc");
    if (t.hi20 != null) add(T, "Levels", "neu", `Recent range: 20-day low ₹${inNum(t.lo20, 2)}, 20-day high ₹${inNum(t.hi20, 2)}. Averages act as moving support and resistance: 44-day ₹${inNum(t.p / (1 + (t.vs44 || 0) / 100), 2)}, 200-day ${t.vs200 != null ? "₹" + inNum(t.p / (1 + t.vs200 / 100), 2) : "–"}. 52-week high ${inPct(t.hi52)} away, 52-week low ${inPct(t.lo52)}. Typical daily range (ATR) ${inNum(t.atr, 1)}% of price.`, "sr");
  }
  if (f) {
    const sec = f.sec, M = (sm && sec && sm[sec]) || {}, fin = /financial/i.test(sec || ""), vs = (a, b) => (a == null || b == null ? "" : a > b ? "above" : "below");
    if (f.pe != null && f.pe > 0) { const hi = (M.pe && f.pe > M.pe) && (!mpe || f.pe > mpe), lo = (M.pe && f.pe < M.pe) && (!mpe || f.pe < mpe); add(F, "Valuation: P/E", hi ? "neg" : lo ? "pos" : "neu", `Trailing P/E ${inNum(f.pe, 1)}${M.pe ? ` vs the ${esc(sec)} median ${inNum(M.pe, 1)} (${M.n} companies)` : ""}${mpe ? ` and the large-cap combined P/E ${inNum(mpe, 1)}` : ""}: ${hi ? "above both, which by itself reads as expensive unless higher growth or lower risk justifies it" : lo ? "below both, which by itself reads as cheap unless lower growth or higher risk explains it" : "mixed against the comparisons"}.${f.fpe ? ` Forward P/E ${inNum(f.fpe, 1)}.` : ""}`, "pe"); }
    else add(F, "Valuation: P/E", "neu", "No meaningful P/E (losses or missing earnings). P/E and EV/EBITDA cannot be used when profit is negative; EV/Sales is the fallback" + (f.evs ? ` (EV/Sales ${inNum(f.evs, 1)})` : "") + ".", "ev");
    if (f.pe > 0 && f.epsg != null && f.epsg > 0) { const peg = f.pe / (f.epsg * 100); add(F, "Valuation: PEG", peg < 1 ? "pos" : "neu", `PEG ${inNum(peg, 2)} using the latest quarterly earnings growth of ${inPct(f.epsg * 100)} as the growth rate (a rough proxy). ${peg < 1 ? "Below 1, the rule-of-thumb level for undervalued." : "At or above 1."}`, "peg"); }
    if (f.evebitda != null && f.evebitda > 0 && !fin) add(F, "Valuation: EV/EBITDA", M.evebitda ? (f.evebitda > M.evebitda ? "neg" : "pos") : "neu", `EV/EBITDA ${inNum(f.evebitda, 1)}${M.evebitda ? `, ${vs(f.evebitda, M.evebitda)} the sector median ${inNum(M.evebitda, 1)}` : ""}.`, "ev");
    if (f.pb != null) add(F, "Valuation: P/B", "neu", `Price to book ${inNum(f.pb, 2)}${M.pb ? ` (sector median ${inNum(M.pb, 2)})` : ""}${f.roe != null ? `, with ROE ${inPct(f.roe * 100)}` : ""}.`, "pb");
    if (f.roe != null) add(F, "Return on equity", M.roe != null ? (f.roe > M.roe ? "pos" : "neg") : f.roe > 0 ? "neu" : "neg", `ROE ${inPct(f.roe * 100)}${f.roe_src ? ` (worked out as ${esc(f.roe_src)})` : ""}${M.roe != null ? `, ${vs(f.roe, M.roe)} the sector median ${inPct(M.roe * 100)}` : ""}.`, "roe");
    if (f.roe != null && f.de != null && !fin && M.roe != null && f.roe > M.roe && f.de > 1) add(F, "DuPont check", "neg", `ROE is above the sector median while debt/equity is ${inNum(f.de, 2)}: part of the ROE may come from leverage rather than margins or efficiency, which brings higher risk.`, "dupont");
    if (f.opm != null || f.npm != null) add(F, "Margins", M.opm != null && f.opm != null ? (f.opm > M.opm ? "pos" : "neg") : "neu", `Operating margin ${inPct((f.opm || 0) * 100)}${M.opm != null ? ` (sector median ${inPct(M.opm * 100)})` : ""}, net margin ${inPct((f.npm || 0) * 100)}${M.npm != null ? ` (sector median ${inPct(M.npm * 100)})` : ""}.`, "margin");
    if (f.de != null && !fin) add(F, "Debt to equity", f.de <= 1 ? "pos" : "neg", `Debt/equity ${inNum(f.de, 2)}: ${f.de <= 1 ? "within" : "above"} the conservative benchmark of 1.${M.de != null ? ` Sector median ${inNum(M.de, 2)}.` : ""}`, "de");
    else if (fin) add(F, "Debt to equity", "neu", "This is a financial company; its borrowings and deposits are its raw material, so the debt/equity benchmark of 1 does not apply.", "de");
    if (f.icr != null && !fin) add(F, "Interest coverage", f.icr < 1 ? "neg" : "pos", `EBIT covers interest ${inNum(f.icr, 1)} times${f.fy ? ` (year to ${f.fy})` : ""}${f.icr < 1 ? ": earnings do not cover interest" : ""}.`, "icr");
    if (f.cr != null && !fin) add(F, "Current ratio", f.cr >= 1 ? "pos" : "neu", `Current ratio ${inNum(f.cr, 2)}${f.cr < 1 ? ": current liabilities exceed current assets, which is not always a red flag (some companies run on customers' money)" : ": current assets exceed current liabilities"}.`, "cr");
    if (f.revg != null || f.epsg != null) add(F, "Growth", (f.revg || 0) > 0 && (f.epsg == null || f.epsg > 0) ? "pos" : (f.revg || 0) < 0 && (f.epsg || 0) < 0 ? "neg" : "neu", `Latest quarter vs a year earlier: revenue ${inPct((f.revg ?? NaN) * 100)}, earnings ${inPct((f.epsg ?? NaN) * 100)}. Past growth is a fact; future growth is an assumption.`, "growth");
    if (f.dy != null) add(F, "Dividend yield", "neu", `Trailing dividend yield ${inPct(f.dy * 100, 2)}${f.payout != null ? `, payout ${inPct(f.payout * 100, 0)} of profit` : ""}.`, "dy");
    if (f.ins != null) add(F, "Ownership", "neu", `Insiders (promoters and management) hold about ${inPct(f.ins * 100, 0)}${f.inst != null ? ` and institutions ${inPct(f.inst * 100, 0)}` : ""}. Promoter pledges are not in this data; check the latest shareholding filing on the exchange.`, "promoter");
    if (f.beta != null) add(F, "Market risk", "neu", `Beta ${inNum(f.beta, 2)}: it has tended to move ${f.beta > 1 ? "more" : "less"} than the market.`, "beta");
  }
  return { T, F };
}
function inDeepLine() {
  const D = DEEPI; try { const h = D.rows[D.head_index].r[1]; const n = h.nse.te, b = h.bse.te; return ` In this app's deep test (later period, stop −8% / target +20%), this rule beat random entries by ${inPct(n.edge * 100, 2)} per trade on NSE stocks and ${inPct(b.edge * 100, 2)} on BSE-only stocks.`; } catch (e) { return ""; }
}

async function inPick(sym, ex) {
  sym = String(sym || "").trim().toUpperCase(); if (!sym) return;
  IV.sym = sym; IV.ex = ex === "BSE" ? "BSE" : "NSE"; IV.err = ""; IV.tab = "stock"; loadFund(); render();
  const key = IV.ex + ":" + sym, inF = FUND && FUND.stocks && IV.ex === "NSE" && FUND.stocks[sym];
  if (!inF && !IV.chart[key]) {
    IV.busy = true; render();
    try {
      let t = sym + ".NS";
      if (IV.ex === "BSE") {
        if (!BSEU) { BSEU = {}; try { const r = await fetch("/universe_bse.csv"); if (r.ok) (await r.text()).split("\n").slice(1).forEach((ln) => { const p = ln.split(","); if (p.length >= 4) BSEU[p[0].trim()] = p[p.length - 1].trim(); }); } catch (e) {} }
        t = (BSEU[sym] || sym) + ".BO";
      }
      let r = await fetch("/api/dma?a=chart&t=" + encodeURIComponent(t)), j = await r.json();
      if (!r.ok && IV.ex === "BSE" && BSEU[sym]) { r = await fetch("/api/dma?a=chart&t=" + encodeURIComponent(sym + ".BO")); j = await r.json(); }
      if (!r.ok) throw new Error(j.error || "No price history.");
      IV.chart[key] = { name: j.name, t: inTech(j, INS && INS.nifty) };
    } catch (e) { IV.err = e.message; }
    IV.busy = false;
  }
  inLoadNews(sym); render();
}
async function inLoadNews(sym) {
  const name = inName(sym), q = (name ? name.replace(/\b(limited|ltd\.?|ltd)\b/gi, "").trim() : sym) + " share";
  if (IV.news[q]) return;
  IV.news[q] = { loading: true }; render();
  try { const r = await fetch("/api/dma?a=news&q=" + encodeURIComponent(q)), j = await r.json(); IV.news[q] = r.ok ? j : { error: j.error || "News unavailable." }; }
  catch (e) { IV.news[q] = { error: "News unavailable." }; }
  render();
}
function inName(sym) {
  const s = FUND && FUND.stocks && FUND.stocks[sym]; if (s && s.n) return s.n;
  const f = FUND && FUND.fund && FUND.fund[sym]; if (f && f.name) return f.name;
  const k = IV.ex + ":" + sym; if (IV.chart[k] && IV.chart[k].name) return IV.chart[k].name;
  const q = (typeof data !== "undefined" && data.signals || []).find((x) => x.symbol === sym); return q && q.name || null;
}

function inStock() {
  if (FUND === null) { loadFund(); return `<div class="empty">Loading…</div>`; }
  const syms = Object.keys((FUND && FUND.stocks) || {});
  const hold = (typeof openPos === "function" ? openPos() : []).map((p) => [p.symbol, p.exchange]);
  const wl = (typeof WL !== "undefined" && Array.isArray(WL) ? WL : []).map((w) => [w.symbol, w.exchange]);
  const quick = (lbl, arr) => (arr.length ? `<div class="in-quick"><span class="in-lv" style="align-self:center">${lbl}:</span>${arr.slice(0, 20).map(([s, e]) => `<button class="chip" aria-pressed="${IV.sym === s && IV.ex === (e || "NSE")}" onclick="inPick('${esc(s)}','${e || "NSE"}')">${esc(s)}${e === "BSE" ? " (BSE)" : ""}</button>`).join("")}</div>` : "");
  const box = `<div class="in-box"><div class="in-search"><input id="in-q" list="in-syms" placeholder="Type a symbol, e.g. RELIANCE" autocapitalize="characters" autocomplete="off" onkeydown="if(event.key==='Enter')inPick(this.value,document.getElementById('in-ex').value)"><datalist id="in-syms">${syms.slice(0, 1200).map((s) => `<option value="${esc(s)}">`).join("")}</datalist><select id="in-ex" aria-label="Exchange"><option${IV.ex === "NSE" ? " selected" : ""}>NSE</option><option${IV.ex === "BSE" ? " selected" : ""}>BSE</option></select><button class="btn pri" onclick="inPick(document.getElementById('in-q').value,document.getElementById('in-ex').value)">Show</button></div>
  ${quick("My holdings", hold)}${quick("Watchlist", wl)}<p class="m" style="margin:6px 0 0">${esc((FUND && FUND.universe) || "")} have technical and financial numbers ready${FUND && FUND.fund_updated ? ` (financials from ${new Date(FUND.fund_updated).toLocaleDateString("en-IN", { day: "numeric", month: "short" })})` : ""}. Any other NSE or BSE stock gets technical numbers fetched live.</p></div>`;
  if (!IV.sym) return box + `<div class="empty">Pick a stock to see its readings.</div>`;
  const key = IV.ex + ":" + IV.sym, pre = IV.ex === "NSE" && FUND.stocks ? FUND.stocks[IV.sym] : null, live = IV.chart[key];
  const t = pre ? pre.t : live ? live.t : null, f = IV.ex === "NSE" && FUND.fund ? FUND.fund[IV.sym] : null;
  if (!t && IV.busy) return box + `<div class="empty">Fetching ${esc(IV.sym)}…</div>`;
  if (!t && !f) return box + `<div class="empty">${esc(IV.err || "No data for " + IV.sym + ".")}</div>`;
  const mpe = INS && INS.market_pe ? INS.market_pe.pe : null, R = inStockReadings(t, f, FUND.sector_med, mpe, IV.sym), all = R.T.concat(R.F);
  const cnt = (k) => all.filter((x) => x.tone === k).length, name = inName(IV.sym);
  const tvs = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent((IV.ex === "BSE" ? "BSE:" : "NSE:") + IV.sym)}`;
  const head = `<div class="in-box"><div class="in-sh"><div><h3>${esc(IV.sym)} <span class="tag ex">${IV.ex}</span></h3><div class="in-lv">${esc(name || "")}${f && f.sec ? ` · ${esc(f.sec)}${f.ind ? " / " + esc(f.ind) : ""}` : ""}${f && f.mcap ? ` · market cap ₹${inNum(f.mcap / 1e7, 0)} crore` : ""}</div></div><div style="text-align:right"><div class="px">${t ? "₹" + inNum(t.p, 2) : "–"}</div><div class="in-lv">${t ? `<span class="${inCl(t.d1)}">${inPct(t.d1)} day</span> · <span class="${inCl(t.m1)}">${inPct(t.m1)} 1M</span> · <span class="${inCl(t.y1)}">${inPct(t.y1)} 1Y</span> · close of ${esc(t.date || "")}` : ""}</div></div></div>
   <div class="in-tally"><span class="sx-chip g">${cnt("pos")} supportive</span><span class="sx-chip r">${cnt("neg")} caution</span><span class="sx-chip">${cnt("neu")} neutral</span><span class="in-lv" style="align-self:center">readings below; this is a count, not a verdict · <a href="${tvs}" target="_blank" rel="noopener noreferrer">Chart on TradingView</a></span></div></div>`;
  const tech = `<div class="in-box"><h3>Technical readings</h3><p class="m">From daily prices${pre ? "" : " fetched live"}. NISM's technical chapter treats these as tools to read trend and momentum, not certainties.</p>${t ? inReadings(R.T, "t") : `<p class="m">No price history.</p>`}</div>`;
  const fin = `<div class="in-box"><h3>Financial readings</h3><p class="m">From the latest reported numbers (Yahoo Finance, which can lag or contain errors; check the annual report). Compared with the median of covered companies in the same sector, as NISM's peer-comparison section suggests.</p>${f ? inReadings(R.F, "f") : `<p class="m">Financial numbers are only collected for covered NSE stocks (${esc(((FUND && FUND.universe) || "").replace(/^The /, "the "))}).</p>`}</div>`;
  const qt = f && f.q && f.q.length ? `<div class="in-box"><h3>Quarterly results</h3><div class="sx-w"><table class="sx2" style="min-width:420px"><thead><tr><th>Quarter ended</th><th>Revenue (₹ crore)</th><th>Net profit (₹ crore)</th><th>Net margin</th></tr></thead><tbody>${f.q.slice().reverse().map((x) => `<tr><td>${esc(x.d)}</td><td>${x.rev == null ? "–" : inNum(x.rev / 1e7, 0)}</td><td class="${inCl(x.ni)}">${x.ni == null ? "–" : inNum(x.ni / 1e7, 0)}</td><td>${x.rev && x.ni != null ? inPct((x.ni / x.rev) * 100) : "–"}</td></tr>`).join("")}</tbody></table></div></div>` : "";
  let peers = "";
  if (f && f.sec && FUND.fund) {
    const P = Object.entries(FUND.fund).filter(([s, o]) => o.sec === f.sec && (o.ind === f.ind || !f.ind) && o.mcap).sort((a, b) => b[1].mcap - a[1].mcap).slice(0, 10);
    if (P.length > 1) peers = `<div class="in-box"><h3>Peers (${esc(f.ind || f.sec)})</h3><p class="m">Same industry among covered companies, largest first. ${inRefBtn("peer", "p-peer")}</p><div class="sx-w"><table class="sx2" style="min-width:640px"><thead><tr><th>Company</th><th>Market cap (₹ cr)</th><th>P/E</th><th>P/B</th><th>ROE</th><th>Debt/equity</th><th>Op. margin</th><th>1 year</th></tr></thead><tbody>${P.map(([s, o]) => { const tt = FUND.stocks[s] && FUND.stocks[s].t; return `<tr${s === IV.sym ? ' class="on"' : ""}><td><a href="#insights" onclick="inPick('${esc(s)}','NSE');return false">${esc(s)}</a></td><td>${inNum(o.mcap / 1e7, 0)}</td><td>${o.pe > 0 ? inNum(o.pe, 1) : "–"}</td><td>${inNum(o.pb, 2)}</td><td>${o.roe == null ? "–" : inPct(o.roe * 100)}</td><td>${inNum(o.de, 2)}</td><td>${o.opm == null ? "–" : inPct(o.opm * 100)}</td><td class="${inCl(tt && tt.y1)}">${inPct(tt && tt.y1)}</td></tr>`; }).join("")}</tbody></table></div></div>`;
  }
  const q = (name ? name.replace(/\b(limited|ltd\.?|ltd)\b/gi, "").trim() : IV.sym) + " share", N = IV.news[q];
  const news = `<div class="in-box"><h3>Recent headlines</h3>${inNewsNote()}${!N || N.loading ? `<p class="m">Loading headlines…</p>` : N.error ? `<p class="m">${esc(N.error)}</p>` : `<p class="m">Search: “${esc(N.q)}” · ${esc(N.source || "")}</p>${inNewsList(N.items)}`}</div>`;
  return box + head + `<div class="in-cols">${tech}${fin}</div>` + qt + peers + news;
}
