/* Quote panel: one side panel that opens from any stock, index, sector or industry name anywhere in the app.
   Shows the price, an interactive chart with its averages, key numbers, what this app says about it
   (screener signal, strategies signalling, your holding, linked news) and links to TradingView, NSE, BSE,
   Screener.in, Google Finance and Yahoo Finance. Styles live in app.css. */
const EQ = { stack: [], range: "6m", charts: {}, busy: {}, bse: null, hover: null };

// Yahoo tickers used in the app -> TradingView symbols (checked against TradingView's own symbol names)
const TV_IDX = { "^NSEI": "NSE:NIFTY", "^BSESN": "BSE:SENSEX", "^NSEBANK": "NSE:BANKNIFTY", "^NSEMDCP50": "NSE:NIFTYMIDCAP50", "^INDIAVIX": "NSE:INDIAVIX",
  "^CNXIT": "NSE:CNXIT", "^CNXAUTO": "NSE:CNXAUTO", "^CNXFMCG": "NSE:CNXFMCG", "^CNXPHARMA": "NSE:CNXPHARMA", "^CNXMETAL": "NSE:CNXMETAL", "^CNXREALTY": "NSE:CNXREALTY",
  "^CNXENERGY": "NSE:CNXENERGY", "^CNXPSUBANK": "NSE:CNXPSUBANK", "^CNXINFRA": "NSE:CNXINFRA", "^CNXMEDIA": "NSE:CNXMEDIA", "NIFTY_FIN_SERVICE.NS": "NSE:CNXFINANCE",
  "^GSPC": "SP:SPX", "^IXIC": "NASDAQ:IXIC", "^FTSE": "TVC:UKX", "^GDAXI": "XETR:DAX", "^N225": "TVC:NI225", "^HSI": "TVC:HSI", "000001.SS": "SSE:000001",
  "INR=X": "FX_IDC:USDINR", "DX-Y.NYB": "TVC:DXY", "BZ=F": "TVC:UKOIL", "GC=F": "TVC:GOLD", "HG=F": "COMEX:HG1!", "^TNX": "TVC:US10Y" };
const INDIAN_IDX = (k) => /^\^(NSE|BSE|CNX|INDIAVIX)|NIFTY_/.test(k);

/* ---------- opening and closing ---------- */
function openStock(sym, ex) { entOpen({ t: "stock", sym: String(sym || "").toUpperCase(), ex: ex === "BSE" ? "BSE" : "NSE" }); }
function openIndex(k) { entOpen({ t: "index", k }); }
function openGroup(kind, name) { entOpen({ t: "group", kind, name }); }
function entOpen(e, replace) {
  if (replace || !EQ.stack.length) EQ.stack = [e]; else EQ.stack.push(e);
  entEnsure(); entLoad(e); entDraw(); setTimeout(() => { const b = document.querySelector(".eq-x"); if (b) b.focus(); }, 30);
}
function entBack() { EQ.stack.pop(); if (!EQ.stack.length) return entClose(); entDraw(); }
function entClose() { EQ.stack = []; const r = document.getElementById("eq"); if (r) r.hidden = true; document.documentElement.classList.remove("eq-on"); }
function entEnsure() {
  let r = document.getElementById("eq");
  if (!r) {
    r = document.createElement("div"); r.id = "eq"; r.innerHTML = `<div class="eq-bk" onclick="entClose()"></div><aside class="eq-p" role="dialog" aria-modal="true" aria-label="Details"></aside>`;
    document.body.appendChild(r);
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && EQ.stack.length) entClose(); });
  }
  r.hidden = false; document.documentElement.classList.add("eq-on");
}
/* small helpers other files use to make a name clickable */
function entS(sym, ex, label) { return `<button type="button" class="ent" onclick="event.stopPropagation();openStock('${esc(sym)}','${ex === "BSE" ? "BSE" : "NSE"}')" title="Details, chart and links for ${esc(sym)}">${label == null ? esc(sym) : label}</button>`; }
function entI(k, label) { return `<button type="button" class="ent" onclick="event.stopPropagation();openIndex('${esc(k)}')" title="Details and chart">${label == null ? esc(MK_NAMES[k] || k) : label}</button>`; }
function entG(kind, name, label) { return name ? `<button type="button" class="ent" onclick="event.stopPropagation();openGroup('${kind}','${esc(name).replace(/'/g, "\\'")}')" title="All covered companies in this ${kind === "ind" ? "industry" : "sector"}">${label == null ? esc(name) : label}</button>` : ""; }

/* ---------- data ---------- */
async function entBseCode(sym) {
  if (EQ.bse === null) { EQ.bse = {}; try { const r = await fetch("/universe_bse.csv"); if (r.ok) (await r.text()).split("\n").slice(1).forEach((ln) => { const p = ln.split(","); if (p.length >= 4) EQ.bse[p[0].trim()] = p[p.length - 1].trim(); }); } catch (e) {} }
  return EQ.bse[sym] || null;
}
async function entTicker(e) { if (e.t === "index") return e.k; if (e.ex === "BSE") { const c = await entBseCode(e.sym); return (c || e.sym) + ".BO"; } return e.sym + ".NS"; }
async function entLoad(e) {
  if (typeof INAMES !== "undefined" && INAMES === null && typeof loadFeed === "function" && !IV.feedBusy) loadFeed();
  if (typeof FUND !== "undefined" && FUND === null && typeof loadFund === "function") loadFund();
  if (typeof MKT !== "undefined" && MKT === null && typeof loadMkt === "function" && !IV.mktBusy) loadMkt();
  if (typeof STRAT !== "undefined" && STRAT === null && typeof loadStrat === "function") loadStrat();
  if (e.t === "group") return;
  const t = await entTicker(e); e.tk = t;
  if (EQ.charts[t] || EQ.busy[t]) return;
  EQ.busy[t] = true; entDraw();
  try { const r = await fetch("/api/dma?a=chart&t=" + encodeURIComponent(t)), j = await r.json(); EQ.charts[t] = r.ok && j.c ? j : { error: j.error || "No price history." }; }
  catch (err) { EQ.charts[t] = { error: "Could not reach the price source." }; }
  EQ.busy[t] = false; entDraw();
}
const entSma = (a, n) => { const o = new Array(a.length).fill(null); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) o[i] = s / n; } return o; };
function entRet(c, k) { const n = c.length; return n > k && c[n - 1 - k] ? (c[n - 1] / c[n - 1 - k] - 1) * 100 : null; }

/* ---------- interactive chart ---------- */
const ENT_RANGES = [["1m", "1M", 21], ["3m", "3M", 63], ["6m", "6M", 126], ["1y", "1Y", 252], ["2y", "2Y", 9999]];
function entChart(C, fmt, maA, maB) {
  if (!C) return `<div class="eq-ch eq-load">Loading the chart…</div>`;
  if (C.error) return `<div class="eq-ch eq-load">${esc(C.error)}</div>`;
  const N = (ENT_RANGES.find((r) => r[0] === EQ.range) || ENT_RANGES[2])[2], c = C.c, n = c.length, s0 = Math.max(0, n - N);
  const A = entSma(c, maA), B = entSma(c, maB), xs = c.slice(s0), a = A.slice(s0), b = B.slice(s0), d = C.dates.slice(s0), m = xs.length;
  const vals = xs.concat(a.filter((x) => x != null), b.filter((x) => x != null)), lo = Math.min(...vals), hi = Math.max(...vals);
  const W = 600, H = 220, L = 6, R = 58, T = 10, Bm = 22, iw = W - L - R, ih = H - T - Bm, px = (i) => L + (m < 2 ? 0 : (i / (m - 1)) * iw), py = (v) => T + ih - ((v - lo) / (hi - lo || 1)) * ih;
  const line = (arr) => arr.map((v, i) => (v == null ? null : `${px(i).toFixed(1)},${py(v).toFixed(1)}`)).filter(Boolean).join(" ");
  const up = xs[m - 1] >= xs[0], grid = [hi, (hi + lo) / 2, lo].map((v) => `<line x1="${L}" x2="${W - R}" y1="${py(v).toFixed(1)}" y2="${py(v).toFixed(1)}" class="eq-gr"/><text x="${W - R + 6}" y="${(py(v) + 4).toFixed(1)}" class="eq-ax">${fmt(v)}</text>`).join("");
  const ticks = [0, Math.floor(m / 2), m - 1].map((i, j) => `<text x="${px(i).toFixed(1)}" y="${H - 6}" class="eq-ax" text-anchor="${j === 0 ? "start" : j === 2 ? "end" : "middle"}">${esc(entD(d[i]))}</text>`).join("");
  EQ.hover = { xs, a, b, d, px, py, m, L, iw, W, fmt, maA, maB };
  const chg = (xs[m - 1] / xs[0] - 1) * 100;
  return `<div class="eq-rng" role="group" aria-label="Chart range">${ENT_RANGES.map(([k, l]) => `<button type="button" aria-pressed="${EQ.range === k}" onclick="EQ.range='${k}';entDraw()">${l}</button>`).join("")}<span class="${chg >= 0 ? "pos" : "neg"}">${inPct(chg)} over this range</span></div>
  <div class="eq-ch" onmousemove="entHover(event)" onmouseleave="entHover(null)" ontouchmove="entHover(event.touches[0])"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price chart with ${maA}-day and ${maB}-day averages">${grid}${ticks}
   <polyline points="${line(b)}" class="eq-mb"/><polyline points="${line(a)}" class="eq-ma"/><polyline points="${line(xs)}" class="eq-pl ${up ? "up" : "dn"}"/><line id="eq-hl" x1="0" x2="0" y1="${T}" y2="${T + ih}" class="eq-hl" visibility="hidden"/><circle id="eq-hd" r="3.5" class="eq-hd ${up ? "up" : "dn"}" visibility="hidden"/></svg><div class="eq-tip" id="eq-tip" hidden></div></div>
  <div class="eq-lg"><span><i class="pl ${up ? "up" : "dn"}"></i>Price</span><span><i class="ma"></i>${maA}-day average</span><span><i class="mb"></i>${maB}-day average</span></div>`;
}
function entHover(ev) {
  const H = EQ.hover, tip = document.getElementById("eq-tip"), hl = document.getElementById("eq-hl"), hd = document.getElementById("eq-hd");
  if (!H || !tip) return;
  if (!ev) { tip.hidden = true; hl.setAttribute("visibility", "hidden"); hd.setAttribute("visibility", "hidden"); return; }
  const box = tip.parentElement.getBoundingClientRect(), x = ((ev.clientX - box.left) / box.width) * H.W, i = Math.max(0, Math.min(H.m - 1, Math.round(((x - H.L) / H.iw) * (H.m - 1))));
  const X = H.px(i), Y = H.py(H.xs[i]); hl.setAttribute("x1", X); hl.setAttribute("x2", X); hl.setAttribute("visibility", "visible"); hd.setAttribute("cx", X); hd.setAttribute("cy", Y); hd.setAttribute("visibility", "visible");
  tip.hidden = false; tip.innerHTML = `<b>${esc(entD(H.d[i], true))}</b><span>Close ${H.fmt(H.xs[i])}</span>${H.a[i] != null ? `<span>${H.maA}-day ${H.fmt(H.a[i])}</span>` : ""}${H.b[i] != null ? `<span>${H.maB}-day ${H.fmt(H.b[i])}</span>` : ""}`;
  const left = (X / H.W) * box.width; tip.style.left = Math.min(box.width - 150, Math.max(0, left + 10)) + "px";
}
function entD(s, year) { if (!s) return ""; const x = new Date(String(s).slice(0, 10) + "T00:00:00"); return isNaN(x) ? s : x.toLocaleDateString("en-IN", year ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short", year: "2-digit" }); }

/* ---------- panels ---------- */
function entLinks(list) { return `<div class="eq-links">${list.filter(Boolean).map(([l, u, t]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer" title="${esc(t || "")}">${esc(l)}</a>`).join("")}</div>`; }
function entKV(rows) { return `<div class="eq-kv">${rows.filter(Boolean).map(([l, v, c]) => `<div><span>${l}</span><b class="${c || ""}">${v}</b></div>`).join("")}</div>`; }
function entNews(list, more) {
  if (typeof LIVE === "undefined" || !LIVE) return `<p class="eq-m">Loading the news feed…</p>`;
  if (!list.length) return `<p class="eq-m">No story in the live news feed (last 7 days) is linked to this right now.</p>`;
  return `<ol class="nsl sm">${list.slice(0, 4).map((x) => inStory(x, { theme: false })).join("")}</ol>${more ? `<button type="button" class="btn sm" onclick="${more}">All ${list.length} linked ${list.length === 1 ? "story" : "stories"}</button>` : ""}`;
}
function entStratToday(sym, ex) {
  if (typeof STRAT === "undefined" || !STRAT || !STRAT.states || ex !== "NSE") return "";
  const st = STRAT.states["NSE:" + sym]; if (!st) return "";
  const by = (s) => (STRAT.strategies || []).find((x) => x.id === s);
  const names = (STRAT.order || []).map((id, j) => [by(id), st[j]]).filter(([s, v]) => s && (v === "b" || v === "h"));
  if (!names.length) return `<li>No strategy in the library is signalling a buy for it today.</li>`;
  return names.map(([s, v]) => `<li><b>${esc(s.name)}</b> ${v === "b" ? "signals a buy today" : "would still be holding (bought on an earlier signal)"}, score ${(s.stars || 0).toFixed(1)} of 5.</li>`).join("");
}
function entStock(e) {
  const C = EQ.charts[e.tk], sym = e.sym, ex = e.ex, F = typeof FUND !== "undefined" && FUND && FUND.fund && ex === "NSE" ? FUND.fund[sym] : null;
  const T = typeof FUND !== "undefined" && FUND && FUND.stocks && ex === "NSE" && FUND.stocks[sym] ? FUND.stocks[sym].t : null;
  const nm = (typeof INAMES !== "undefined" && INAMES && INAMES[sym] && ex === "NSE") ? (Array.isArray(INAMES[sym]) ? INAMES[sym][0] : INAMES[sym]) : null;
  const sig = (typeof data !== "undefined" && data.signals || []).find((s) => s.symbol === sym && (s.exchange || "NSE") === ex);
  const q = sig || (typeof data !== "undefined" && (data.quotes || {})[ex + ":" + sym]) || null;
  const name = (F && F.name) || nm || (sig && sig.name) || (C && C.name) || "";
  const c = C && C.c, last = q && q.price != null ? q.price : c ? c[c.length - 1] : T ? T.p : null;
  const d1 = q && q.chg != null ? q.chg : c ? entRet(c, 1) : T ? T.d1 : null;
  const m44 = c && c.length >= 44 ? entSma(c, 44)[c.length - 1] : null, m200 = c && c.length >= 200 ? entSma(c, 200)[c.length - 1] : null;
  const ccy = (v) => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const hold = typeof openPos === "function" ? openPos().find((p) => p.symbol === sym && p.exchange === ex) : null, wl = typeof WL !== "undefined" ? WL.find((w) => w.symbol === sym && w.exchange === ex) : null;
  const news = typeof inAllStories === "function" && ex === "NSE" ? inAllStories().filter((x) => inLinks(x).sym.includes(sym)).sort((a, b) => String(b.d || "").localeCompare(String(a.d || ""))) : [];
  const y = c ? c.slice(-252) : null, code = ex === "BSE" && EQ.bse ? EQ.bse[sym] : null;
  const head = `<div class="eq-h"><div><h2>${esc(sym)} <span class="tag ex">${ex}</span></h2><p>${esc(name)}</p>${F && F.sec ? `<p class="eq-sec">${entG("sec", F.sec)}${F.ind ? ` <span aria-hidden="true">›</span> ${entG("ind", F.ind)}` : ""}</p>` : ""}</div>
   <div class="eq-px"><b>${last != null ? ccy(last) : "–"}</b><span class="${inCl(d1)}">${d1 != null ? inPct(d1, 2) + " today" : ""}</span><small>${q && q.price != null ? "Screener price, about 15 minutes delayed in market hours" : C && C.dates ? "Close of " + entD(C.dates[C.dates.length - 1], true) : ""}</small></div></div>`;
  const kv = entKV([["1 month", inPct(c ? entRet(c, 21) : T && T.m1), inCl(c ? entRet(c, 21) : T && T.m1)], ["1 year", inPct(c ? entRet(c, 252) : T && T.y1), inCl(c ? entRet(c, 252) : T && T.y1)],
    ["vs 44-day avg", m44 ? inPct((last / m44 - 1) * 100) : T ? inPct(T.vs44) : "–", m44 ? inCl(last - m44) : ""], ["vs 200-day avg", m200 ? inPct((last / m200 - 1) * 100) : T ? inPct(T.vs200) : "–", m200 ? inCl(last - m200) : ""],
    ["52-week high", y ? ccy(Math.max(...y)) : "–"], ["52-week low", y ? ccy(Math.min(...y)) : "–"], T ? ["RSI (14)", inNum(T.rsi, 0)] : null,
    F ? ["Market cap", F.mcap ? "₹" + inNum(F.mcap / 1e7, 0) + " cr" : "–"] : null, F ? ["P/E", F.pe > 0 ? inNum(F.pe, 1) : "–"] : null, F ? ["ROE", F.roe != null ? inPct(F.roe * 100) : "–"] : null, F ? ["Debt/equity", F.de != null ? inNum(F.de, 2) : "–"] : null, F ? ["Dividend yield", F.dy != null ? inPct(F.dy * 100, 2) : "–"] : null]);
  const app = `<ul class="eq-app">${sig ? `<li><b>Screener:</b> ${sig.type === "buy" ? "in the buy zone" : sig.type === "sell" ? "just crossed below" : "approaching"} its 44-day average (${inPct(sig.pct, 2)})${sig.candle ? `, ${esc(sig.candle.replace("_", " "))} candle, ${"★".repeat(sig.score || 0)}${"☆".repeat(3 - (sig.score || 0))}` : ""}.</li>` : `<li>Not on today's screener list (it is not near its 44-day average, or did not pass the price and volume filters).</li>`}
   ${entStratToday(sym, ex)}${hold ? `<li><b>You hold it.</b> ${typeof ledger === "function" ? ledger(hold).qty + " shares at an average of " + ccy(ledger(hold).avg) : ""}${hold.sl ? `, stop loss ${ccy(hold.sl)}` : ""}${hold.target ? `, target ${ccy(hold.target)}` : ""}.</li>` : ""}${wl ? `<li>On your watchlist${wl.note ? `: ${esc(wl.note)}` : ""}.</li>` : ""}</ul>`;
  const links = entStockLinks(sym, ex, e.tk);
  return entStockBody(e, head, C, ccy, kv, app, news, links, last);
}
function entStockLinks(sym, ex, tk) {
  const code = ex === "BSE" && EQ.bse ? EQ.bse[sym] : null, tvs = (ex === "BSE" ? "BSE:" : "NSE:") + sym;
  if (ex === "BSE" && EQ.bse === null) entBseCode(sym).then(() => { if (typeof render === "function") render(); });
  return entLinks([["TradingView chart", `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvs)}`, "Full interactive chart with indicators"],
    ex === "NSE" ? ["NSE quote", `https://www.nseindia.com/get-quotes/equity?symbol=${encodeURIComponent(sym)}`, "Official price, announcements and shareholding on NSE"] : null,
    code ? ["BSE quote", `https://www.bseindia.com/stock-share-price/x/${encodeURIComponent(sym.toLowerCase())}/${code}/`, "Official price and filings on BSE"] : null,
    ["Screener.in", `https://www.screener.in/company/${encodeURIComponent(ex === "BSE" && code ? code : sym)}/consolidated/`, "Ten years of financial statements, ratios and peers"],
    ["Google Finance", `https://www.google.com/finance/quote/${encodeURIComponent(ex === "BSE" && code ? code + ":BOM" : sym + ":NSE")}`, "Price and recent news"],
    ["Yahoo Finance", `https://finance.yahoo.com/quote/${encodeURIComponent(tk || (ex === "BSE" ? (code || sym) + ".BO" : sym + ".NS"))}`, "Price history and statistics"]]);
}
function entStockBody(e, head, C, ccy, kv, app, news, links, last) {
  const sym = e.sym, ex = e.ex, px = last != null ? last : 0;
  const acts = `<div class="eq-acts"><button class="btn sm pri" data-ex="${ex}" data-sym="${esc(sym)}" data-px="${px}" onclick="entClose();track(this)">＋ Add to My Positions</button><button class="btn sm" data-ex="${ex}" data-sym="${esc(sym)}" onclick="entClose();watchFrom(this)">Watch</button><button class="btn sm" onclick="entClose();go('ins');inPick('${esc(sym)}','${ex}')">Full analysis</button></div>`;
  return `${head}${entChart(C, ccy, 44, 200)}${kv}${acts}<section><h3>In this app</h3>${app}</section>
   ${ex === "NSE" ? `<section><h3>Linked news</h3>${entNews(news, `entClose();go('ins');IV.stab='news';inPick('${esc(sym)}','NSE')`)}</section>` : ""}
   <section><h3>More on other sites</h3>${links}</section>`;
}
function entIndex(e) {
  const k = e.k, C = EQ.charts[e.tk], nm = MK_NAMES[k] || k, fmt = (v) => (typeof inFmt === "function" ? inFmt(k, v) : String(v));
  const c = C && C.c, last = c ? c[c.length - 1] : null, d1 = c ? entRet(c, 1) : null;
  const m50 = c && c.length >= 50 ? entSma(c, 50)[c.length - 1] : null, m200 = c && c.length >= 200 ? entSma(c, 200)[c.length - 1] : null;
  const news = typeof inAllStories === "function" ? inAllStories().filter((x) => inLinks(x).idx.includes(k)) : [];
  // covered stocks in the sector this index stands for
  const secs = Object.entries(typeof SEC_IDX !== "undefined" ? SEC_IDX : {}).filter(([, v]) => v === k).map(([s]) => s);
  const S = secs.length && typeof FUND !== "undefined" && FUND && FUND.fund ? Object.entries(FUND.fund).filter(([, f]) => secs.includes(f.sec)).map(([s, f]) => [s, f, FUND.stocks[s] && FUND.stocks[s].t]).filter((r) => r[2]) : [];
  const mov = S.slice().sort((a, b) => (b[2].m1 || 0) - (a[2].m1 || 0));
  const row = ([s, f, t]) => `<li>${entS(s, "NSE")}<span class="eq-nm">${esc((f.name || "").replace(/\s+(Limited|Ltd\.?)$/i, ""))}</span><span class="${inCl(t.m1)}">${inPct(t.m1)}</span></li>`;
  const tv = TV_IDX[k];
  const head = `<div class="eq-h"><div><h2>${esc(nm)}</h2><p>${INDIAN_IDX(k) ? "Index" : "Market price"}${secs.length ? `, standing in for ${secs.map((s) => entG("sec", s)).join(" and ")} companies` : ""}</p></div>
   <div class="eq-px"><b>${last != null ? fmt(last) : "–"}</b><span class="${k === "^TNX" || k === "INR=X" || k === "^INDIAVIX" ? "" : inCl(d1)}">${d1 != null ? inPct(d1, 2) + " today" : ""}</span><small>${C && C.dates ? "Last price of " + entD(C.dates[C.dates.length - 1], true) : ""}</small></div></div>`;
  const kv = entKV([["1 week", inPct(c && entRet(c, 5))], ["1 month", inPct(c && entRet(c, 21)), inCl(c && entRet(c, 21))], ["3 months", inPct(c && entRet(c, 63)), inCl(c && entRet(c, 63))], ["1 year", inPct(c && entRet(c, 252)), inCl(c && entRet(c, 252))],
    ["vs 50-day avg", m50 ? inPct((last / m50 - 1) * 100) : "–"], ["vs 200-day avg", m200 ? inPct((last / m200 - 1) * 100) : "–"]]);
  const links = entLinks([tv ? ["TradingView chart", `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tv)}`, "Full interactive chart"] : null,
    ["Yahoo Finance", `https://finance.yahoo.com/quote/${encodeURIComponent(k)}`, "Price history"],
    INDIAN_IDX(k) ? ["NSE live indices", "https://www.nseindia.com/market-data/live-market-indices", "Official index values and constituents"] : null]);
  return `${head}${entChart(C, fmt, 50, 200)}${kv}
   <section><h3>Linked news</h3>${entNews(news, `entClose();go('ins');inLinkF('i:${esc(k)}')`)}</section>
   ${mov.length ? `<section><h3>Covered companies in this sector, by 1-month move</h3><p class="eq-m">${mov.length} companies. Best and worst five shown.</p><ul class="eq-list">${mov.slice(0, 5).map(row).join("")}</ul>${mov.length > 5 ? `<ul class="eq-list">${mov.slice(-5).map(row).join("")}</ul>` : ""}${secs.map((s) => `<button type="button" class="btn sm" onclick="openGroup('sec','${esc(s)}')">All ${esc(s)} companies</button>`).join(" ")}</section>` : ""}
   <section><h3>More on other sites</h3>${links}</section>`;
}
function entGroup(e) {
  if (typeof FUND === "undefined" || !FUND || !FUND.fund) return `<div class="eq-h"><div><h2>${esc(e.name)}</h2></div></div><p class="eq-m">Loading companies…</p>`;
  const key = e.kind === "ind" ? "ind" : "sec", rows = Object.entries(FUND.fund).filter(([, f]) => f[key] === e.name).map(([s, f]) => [s, f, FUND.stocks[s] && FUND.stocks[s].t]);
  const sortK = EQ.gsort || "mcap", val = (r) => (sortK === "mcap" ? r[1].mcap || 0 : sortK === "pe" ? (r[1].pe > 0 ? -r[1].pe : -1e9) : r[2] ? r[2][sortK] ?? -1e9 : -1e9);
  rows.sort((a, b) => val(b) - val(a));
  const med = (arr) => { const x = arr.filter((v) => v != null && isFinite(v)).sort((a, b) => a - b); return x.length ? x[Math.floor(x.length / 2)] : null; };
  const sec = key === "ind" && rows[0] ? rows[0][1].sec : e.name, idx = typeof SEC_IDX !== "undefined" ? SEC_IDX[sec] : null;
  const news = idx && typeof inAllStories === "function" ? inAllStories().filter((x) => inLinks(x).idx.includes(idx)) : [];
  const inds = key === "sec" ? [...new Set(rows.map((r) => r[1].ind).filter(Boolean))].sort() : [];
  const th = (k, l) => `<th><button type="button" class="eq-sort${sortK === k ? " on" : ""}" onclick="EQ.gsort='${k}';entDraw()">${l}</button></th>`;
  return `<div class="eq-h"><div><h2>${esc(e.name)}</h2><p>${key === "ind" ? `Industry in ${entG("sec", sec)}` : "Sector"}, ${rows.length} covered ${rows.length === 1 ? "company" : "companies"}</p></div></div>
   ${entKV([["Median 1-month move", inPct(med(rows.map((r) => r[2] && r[2].m1))), inCl(med(rows.map((r) => r[2] && r[2].m1)))], ["Median 1-year move", inPct(med(rows.map((r) => r[2] && r[2].y1))), inCl(med(rows.map((r) => r[2] && r[2].y1)))],
     ["Median P/E", inNum(med(rows.map((r) => (r[1].pe > 0 ? r[1].pe : null))), 1)], ["Median ROE", inPct((med(rows.map((r) => r[1].roe)) ?? NaN) * 100)], idx ? ["NSE index", entI(idx)] : null])}
   <div class="tw eq-tw"><table class="mt"><thead><tr><th>Company</th>${th("mcap", "Mkt cap (₹ cr)")}${th("d1", "Day")}${th("m1", "1 month")}${th("y1", "1 year")}${th("pe", "P/E")}</tr></thead><tbody>${rows.slice(0, 60).map(([s, f, t]) => `<tr><td>${entS(s, "NSE")}<small class="eq-nm">${esc((f.name || "").replace(/\s+(Limited|Ltd\.?)$/i, ""))}</small></td><td>${f.mcap ? inNum(f.mcap / 1e7, 0) : "–"}</td><td class="${inCl(t && t.d1)}">${inPct(t && t.d1)}</td><td class="${inCl(t && t.m1)}">${inPct(t && t.m1)}</td><td class="${inCl(t && t.y1)}">${inPct(t && t.y1)}</td><td>${f.pe > 0 ? inNum(f.pe, 1) : "–"}</td></tr>`).join("")}</tbody></table></div>
   ${rows.length > 60 ? `<p class="eq-m">Largest 60 shown.</p>` : ""}
   ${inds.length > 1 ? `<section><h3>Industries in this sector</h3><div class="eq-chips">${inds.map((i) => entG("ind", i, esc(i) + ` <small>${rows.filter((r) => r[1].ind === i).length}</small>`)).join("")}</div></section>` : ""}
   ${idx ? `<section><h3>Linked news (through ${esc(MK_NAMES[idx] || idx)})</h3>${entNews(news, `entClose();go('ins');inLinkF('i:${esc(idx)}')`)}</section>` : ""}
   <p class="eq-m">Covered companies are the most traded NSE stocks the daily update collects financials for; sector and industry names come from Yahoo Finance.</p>`;
}
function entDraw() {
  const r = document.getElementById("eq"); if (!r || !EQ.stack.length) return;
  const e = EQ.stack[EQ.stack.length - 1], p = r.querySelector(".eq-p"), sc = p.querySelector(".eq-b") ? p.querySelector(".eq-b").scrollTop : 0, same = p.dataset.k === JSON.stringify(e);
  const body = e.t === "stock" ? entStock(e) : e.t === "index" ? entIndex(e) : entGroup(e);
  p.innerHTML = `<div class="eq-top">${EQ.stack.length > 1 ? `<button type="button" class="btn ghost sm" onclick="entBack()">‹ Back</button>` : ""}<span class="grow"></span><button type="button" class="eq-x" onclick="entClose()" aria-label="Close">✕</button></div><div class="eq-b">${body}</div>`;
  p.dataset.k = JSON.stringify(e); if (same) p.querySelector(".eq-b").scrollTop = sc;
}
