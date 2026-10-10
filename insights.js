/* Insights tab: a market desk. Live market tape, top stories linked to indices and stocks, a news desk by theme,
   market tables and readings, and a page per stock. Readings apply fixed rules to public numbers and cite the NISM
   workbook section each rule paraphrases. No buy/sell verdicts, no price targets.
   Data: /api/dma?a=feed (live news), /api/dma?a=mkt (live prices), /insights.json, /fund.json, /names.json,
   /api/dma?a=chart (price history for any stock), /api/dma?a=news (headlines for one company).
   Styles live in app.css. */
const IV = { view: "overview", theme: "all", who: "", list: "top", linkF: "", stab: "summary", secPer: "rel3", secSrc: "index", shown: 30,
  feedBusy: false, feedErr: "", mktBusy: false, sym: "", ex: "NSE", open: new Set(), chart: {}, news: {}, busy: false, err: "", full: {} };
const TONE = { pos: "Supportive", neg: "Caution", neu: "Neutral" };
const TAPE = ["^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX", "INR=X", "BZ=F", "GC=F", "^TNX"];
const TAPE_NM = { "^NSEI": "Nifty 50", "^BSESN": "Sensex", "^NSEBANK": "Bank Nifty", "^INDIAVIX": "India VIX", "INR=X": "USD/INR", "BZ=F": "Brent crude", "GC=F": "Gold", "^TNX": "US 10-year" };
const ixN = (v) => Number(v || 0).toLocaleString("en-IN");

/* ===================== data loading, linking, numbers ===================== */
let AUDITI = null;
let INS = null, FUND = null, DEEPI = null, BSEU = null, LIVE = null, INAMES = null, CMATCH = null, LIVET = null;
async function loadFeed(fresh) {
  if (IV.feedBusy) return; IV.feedBusy = true; if (fresh) render();
  try {
    if (INAMES === null) { INAMES = {}; try { const r = await fetch("/names.json", { cache: "no-cache" }); if (r.ok) INAMES = await r.json(); } catch (e) {} CMATCH = inMatcher(INAMES); }
    const r = await fetch("/api/dma?a=feed" + (fresh ? "&fresh=1" : "")), j = await r.json();
    if (r.ok && j.themes) { LIVE = j; IV.feedErr = ""; } else IV.feedErr = j.error || "Live news unavailable.";
  } catch (e) { IV.feedErr = "Live news unavailable."; }
  IV.feedBusy = false; if (view_ === "ins" || view_ === "pos") render(); inSchedule();
}
function inSchedule() {   // refresh while the tab is open: every 5 minutes in market hours, hourly otherwise
  clearTimeout(LIVET); const m = LIVE && LIVE.refresh_min ? LIVE.refresh_min : 5;
  LIVET = setTimeout(() => { if (view_ === "ins" && !document.hidden) { loadFeed(); MKT = null; loadMkt(); } else inSchedule(); }, m * 60000);
}
function inMatcher(names) {
  const stop = new Set("india indian bank power energy capital finance industries global international national general united steel motors life money gold silver oil gas trade home first star sun".split(" "));
  const P = [], firsts = new Set(), esc2 = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const [sym, nm0] of Object.entries(names || {})) { const nm = Array.isArray(nm0) ? nm0[0] : nm0; if (!nm) continue;
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

async function loadIns() {
  if (INS !== null) return; INS = {};
  try { const r = await fetch("/insights.json", { cache: "no-cache" }); if (r.ok) INS = await r.json(); } catch (e) {}
  render();
}
async function loadFund() {
  if (FUND !== null) return; FUND = {};
  try { const r = await fetch("/fund.json", { cache: "no-cache" }); if (r.ok) FUND = await r.json(); } catch (e) {}
  try { const r = await fetch("/dma44_deep.json", { cache: "no-cache" }); if (r.ok) DEEPI = await r.json(); } catch (e) {}
  try { const r = await fetch("/dma44_audit.json", { cache: "no-cache" }); if (r.ok) AUDITI = await r.json(); } catch (e) {}
  render();
}

const inNum = (v, d = 1) => (v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const inPct = (v, d = 1) => { if (v == null || !isFinite(v)) return "–"; const a = Math.abs(v).toFixed(d); return (+a === 0 ? "" : v > 0 ? "+" : "−") + a + "%"; };
const inCl = (v) => (v == null ? "" : v > 0 ? "sx-pos" : v < 0 ? "sx-neg" : "");
const inAgo = (iso) => { if (!iso) return ""; const m = (Date.now() - new Date(iso)) / 6e4; return m < 60 ? Math.max(1, Math.round(m)) + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago"; };

/* ---------- linking headlines to indices, sectors and stocks (fixed keyword rules, shown on the page) ---------- */
// Short names used in headlines -> NSE symbol
const ALIAS = [["SBI", "SBIN"], ["State Bank", "SBIN"], ["L&T", "LT"], ["Larsen", "LT"], ["HUL", "HINDUNILVR"], ["Airtel", "BHARTIARTL"], ["Jio", "RELIANCE"], ["DMart", "DMART"], ["D-Mart", "DMART"],
  ["IndiGo", "INDIGO"], ["Infosys", "INFY"], ["HDFC Bank", "HDFCBANK"], ["ICICI Bank", "ICICIBANK"], ["Axis Bank", "AXISBANK"], ["Kotak", "KOTAKBANK"], ["Maruti", "MARUTI"], ["Tata Steel", "TATASTEEL"],
  ["Tata Motors", "TMPV"], ["Bajaj Finance", "BAJFINANCE"], ["Wipro", "WIPRO"], ["HCLTech", "HCLTECH"], ["HCL Tech", "HCLTECH"], ["Tech Mahindra", "TECHM"], ["ONGC", "ONGC"], ["NTPC", "NTPC"],
  ["Coal India", "COALINDIA"], ["Adani Ports", "ADANIPORTS"], ["Adani Green", "ADANIGREEN"], ["Adani Enterprises", "ADANIENT"], ["Vedanta", "VEDL"], ["Hindalco", "HINDALCO"], ["Sun Pharma", "SUNPHARMA"],
  ["Dr Reddy", "DRREDDY"], ["Cipla", "CIPLA"], ["Titan", "TITAN"], ["Asian Paints", "ASIANPAINT"], ["Nestle India", "NESTLEIND"], ["ITC", "ITC"], ["Paytm", "PAYTM"], ["Nykaa", "NYKAA"], ["Zomato", "ETERNAL"],
  ["Eternal", "ETERNAL"], ["Swiggy", "SWIGGY"], ["LIC", "LICI"], ["Vodafone Idea", "IDEA"], ["Yes Bank", "YESBANK"], ["PNB", "PNB"], ["Bank of Baroda", "BANKBARODA"], ["Ola Electric", "OLAELEC"],
  ["Hero MotoCorp", "HEROMOTOCO"], ["Bajaj Auto", "BAJAJ-AUTO"], ["Eicher", "EICHERMOT"], ["Mahindra", "M&M"], ["BEL", "BEL"], ["Bharat Electronics", "BEL"], ["HAL", "HAL"], ["Hindustan Aeronautics", "HAL"],
  ["Mazagon", "MAZDOCK"], ["IRCTC", "IRCTC"], ["IRFC", "IRFC"], ["Jio Financial", "JIOFIN"], ["Tata Power", "TATAPOWER"], ["Power Grid", "POWERGRID"], ["BPCL", "BPCL"], ["Indian Oil", "IOC"], ["HPCL", "HINDPETRO"],
  ["JSW Steel", "JSWSTEEL"], ["TCS", "TCS"], ["Reliance", "RELIANCE"], ["Ambani", "RELIANCE"], ["Adani", "ADANIENT"], ["Avenue Supermarts", "DMART"], ["Muthoot", "MUTHOOTFIN"], ["CDSL", "CDSL"], ["MCX", "MCX"], ["Angel One", "ANGELONE"]]
  .map(([a, s]) => [new RegExp("(^|[^A-Za-z])" + a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![A-Za-z])"), s]);
// Topic in the headline -> indices and stocks most exposed. Each rule says why, in a few words.
const IMPACT = [
  { rx: /\b(crude|brent|oil price|opec|diesel|petrol|fuel price)/i, why: "crude oil", idx: ["^CNXENERGY", "BZ=F"], sym: ["ONGC", "BPCL", "IOC", "HINDPETRO", "INDIGO", "ASIANPAINT"] },
  { rx: /\b(repo|rbi (policy|rate|hike|cut)|rate (hike|cut)|monetary policy|mpc|crr|liquidity)\b/i, why: "interest rates", idx: ["^NSEBANK", "NIFTY_FIN_SERVICE.NS", "^CNXREALTY", "^CNXAUTO"], sym: ["HDFCBANK", "SBIN", "BAJFINANCE"] },
  { rx: /\b(fed|federal reserve|powell|treasury yields?|us yields?)\b/i, why: "US rates and foreign money", idx: ["^NSEI", "^CNXIT", "^TNX"], sym: [] },
  { rx: /\b(rupee|forex|fpi|fii|foreign investors?)\b/i, why: "rupee and foreign flows", idx: ["INR=X", "^NSEI", "^CNXIT", "^CNXPHARMA"], sym: ["TCS", "INFY"] },
  { rx: /\b(h-1b|visa|green card)\b/i, why: "US work visas (IT services)", idx: ["^CNXIT"], sym: ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"] },
  { rx: /\btariffs?\b.*\bpharma|pharma.*\btariffs?\b|\bdrug (prices?|tariffs?)\b/i, why: "pharma tariffs", idx: ["^CNXPHARMA"], sym: ["SUNPHARMA", "DRREDDY", "CIPLA"] },
  { rx: /\b(tariffs?|trade (deal|pact|war|talks))\b/i, why: "trade and tariffs", idx: ["^NSEI", "^CNXIT", "^CNXMETAL"], sym: [] },
  { rx: /\b(starlink|satellite internet|satcom|spectrum|telecom|5g)\b/i, why: "telecom and satellite internet", idx: ["^CNXMEDIA"], sym: ["BHARTIARTL", "RELIANCE", "IDEA"] },
  { rx: /\b(steel|copper|aluminium|aluminum|zinc|iron ore|metals?)\b/i, why: "metal prices", idx: ["^CNXMETAL", "HG=F"], sym: ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL"] },
  { rx: /\bgold\b/i, why: "gold prices", idx: ["GC=F"], sym: ["TITAN", "MUTHOOTFIN"] },
  { rx: /\b(defence|defense|missile|military|war|drone|army)\b/i, why: "defence and conflict", idx: ["^CNXENERGY", "BZ=F"], sym: ["HAL", "BEL", "MAZDOCK"] },
  { rx: /\b(sebi|f&o|derivatives|demat|mutual fund|cas)\b/i, why: "market rules (brokers, exchanges, depositories)", idx: ["NIFTY_FIN_SERVICE.NS"], sym: ["CDSL", "ANGELONE", "MCX"] },
  { rx: /\b(auto sales|car sales|ev\b|electric vehicles?|two-wheeler)/i, why: "auto demand", idx: ["^CNXAUTO"], sym: ["MARUTI", "M&M", "TMPV", "BAJAJ-AUTO"] },
  { rx: /\b(real estate|housing|home loans?|property)\b/i, why: "real estate", idx: ["^CNXREALTY"], sym: ["DLF", "GODREJPROP"] },
  { rx: /\b(ai\b|artificial intelligence|nvidia|semiconductor|chips?|it services|software)\b/i, why: "technology spending", idx: ["^CNXIT", "^IXIC"], sym: ["TCS", "INFY", "HCLTECH"] },
  { rx: /\b(china|chinese)\b/i, why: "China demand", idx: ["000001.SS", "^CNXMETAL"], sym: [] },
  { rx: /\b(wall street|s&p 500|nasdaq|dow jones)\b/i, why: "US markets", idx: ["^GSPC", "^IXIC", "^NSEI"], sym: [] },
  { rx: /\b(sensex|nifty|dalal street|stock market|indian shares|markets? (rally|fall|crash))\b/i, why: "the Indian market as a whole", idx: ["^NSEI", "^BSESN"], sym: [] },
  { rx: /\b(gst|budget|fiscal deficit|tax cut|income tax)\b/i, why: "tax and government spending", idx: ["^NSEI", "^CNXFMCG", "^CNXAUTO"], sym: [] },
  { rx: /\b(monsoon|rainfall|kharif|rabi|crop)\b/i, why: "farm output and rural demand", idx: ["^CNXFMCG"], sym: ["ITC", "HINDUNILVR", "M&M"] },
  { rx: /\b(iran|israel|middle east|red sea|strait of hormuz|gulf)\b/i, why: "Middle East (crude and shipping)", idx: ["BZ=F", "^CNXENERGY"], sym: ["ONGC", "BPCL", "IOC"] },
  { rx: /\b(russia|ukraine|putin|zelensky)/i, why: "Russia-Ukraine (oil, diesel, sanctions)", idx: ["BZ=F"], sym: ["RELIANCE", "BPCL", "IOC"] },
];
const SEC_IDX = { "Technology": "^CNXIT", "Financial Services": "^NSEBANK", "Healthcare": "^CNXPHARMA", "Basic Materials": "^CNXMETAL", "Energy": "^CNXENERGY", "Real Estate": "^CNXREALTY",
  "Consumer Cyclical": "^CNXAUTO", "Consumer Defensive": "^CNXFMCG", "Communication Services": "^CNXMEDIA", "Utilities": "^CNXENERGY", "Industrials": "^CNXINFRA" };
const LINKC = new Map();
function inLinks(x) {   // -> {sym:[...], idx:[...], why:[...]}
  if (LINKC.has(x.u)) return LINKC.get(x.u);
  const t = x.t, sym = [], idx = [], why = [], add = (a, v) => { if (v && !a.includes(v)) a.push(v); };
  (CMATCH ? CMATCH(t, x.who) : []).forEach((s) => add(sym, s));
  for (const [rx, s] of ALIAS) if (rx.test(t)) add(sym, s);
  for (const r of IMPACT) if (r.rx.test(t)) { add(why, r.why); r.idx.forEach((k) => add(idx, k)); r.sym.forEach((s) => sym.length < 8 && add(sym, s)); }
  const o = { sym: sym.slice(0, 7), idx: idx.slice(0, 4), why: why.slice(0, 3) }; LINKC.set(x.u, o); return o;
}
function inPx(sym) {   // latest move for a stock: screener price (15-minute delay) if it has one, else last close from the daily update
  const q = (typeof data !== "undefined" && ((data.signals || []).find((s) => s.symbol === sym && (s.exchange || "NSE") === "NSE") || (data.quotes || {})["NSE:" + sym])) || null;
  if (q && q.chg != null) return q.chg;
  const n = INAMES && INAMES[sym]; return Array.isArray(n) ? n[2] : null;
}
function inIdxPx(k) { const L = MKT && MKT.series && MKT.series.find((x) => x.t === k); if (!L || L.c.length < 2) return null; const c = L.c; return (c[c.length - 1] / c[c.length - 2] - 1) * 100; }
function inStoryMatchesLink(x, f) { if (!f) return true; const L = inLinks(x); return f.startsWith("i:") ? L.idx.includes(f.slice(2)) : L.sym.includes(f.slice(2)); }
function inAllStories() { const N = LIVE || (INS && INS.news); if (!N || !N.themes) return []; const seen = new Set(), out = []; for (const t of N.themes) for (const s of t.stories) if (!seen.has(s.u)) { seen.add(s.u); out.push(Object.assign({ th: t.id }, s)); } return out; }
function inCountFor(f) { return inAllStories().filter((x) => inStoryMatchesLink(x, f)).length; }


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
    if (t.vs44 != null) { const zone = t.vs44 >= 0 && t.vs44 <= 5 && (t.s44 || 0) > 0; add(T, "44-day average", zone ? "pos" : t.vs44 < 0 && (t.s44 || 0) < 0 ? "neg" : "neu", `Price is ${inPct(t.vs44)} from its 44-day average, which is ${(t.s44 || 0) > 0 ? "rising" : "falling"} (${inPct(t.s44)} over 5 days).${zone ? " That is the 44-DMA buy zone (0 to 5% above a rising average)." : ""}${zone && (AUDITI || (DEEPI && DEEPI.rows)) ? inDeepLine(sym) : ""}`, "ma"); }
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
  const A = AUDITI;
  try { const n = A.groups.nse.periods.all, b = A.groups.bse.periods.all; return ` In this app's 12-year audit (${n.signals.n.toLocaleString("en-IN")} NSE trades, stop −8% / target +20%), this rule beat random stocks bought the same day by ${inPct(n.edge_vs_same_day.edge * 100, 2)} per trade on NSE (monthly t ${n.monthly_vs_same_day.t}), and ${inPct(b.edge_vs_same_day.edge * 100, 2)} on BSE-only stocks, mostly when the Nifty 50 was above its 200-day average.`; } catch (e) {}
  const D = DEEPI; try { const h = D.rows[D.head_index].r[1]; const n = h.nse.te, b = h.bse.te; return ` In this app's deep test (later period, stop −8% / target +20%), this rule beat random entries by ${inPct(n.edge * 100, 2)} per trade on NSE stocks and ${inPct(b.edge * 100, 2)} on BSE-only stocks.`; } catch (e) { return ""; }
}

async function inPick(sym, ex) {
  sym = String(sym || "").trim().toUpperCase(); if (!sym) return;
  IV.sym = sym; IV.ex = ex === "BSE" ? "BSE" : "NSE"; IV.err = ""; IV.view = "stocks"; loadFund(); render();
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


function inNewsBadge(sym, ex) {   // used in My Positions: how many live stories name this holding
  if (LIVE === null && !IV.feedBusy) { loadFeed(); return ""; }
  if (ex === "BSE") return "";
  const n = inAllStories().filter((x) => inLinks(x).sym.includes(sym)).length;
  return n ? `<button type="button" class="nw-badge" onclick="event.stopPropagation();IV.stab='news';go('ins');inPick('${esc(sym)}','NSE')" title="Open the news linked to ${esc(sym)}">${n} in the news</button>` : "";
}


/* ----- readings with a short label for the compact "market read" ----- */
function mkReadings(M, sectCov, breadth, feed) {
  const R = [], g = (k) => M[k] || {}, ob = (k, area, short, text, tone, ref) => R.push({ k, area, short, text, tone, ref }), f1 = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);
  const n = g("^NSEI"), sx = g("^BSESN");
  if (n.vs200 != null) { const up = n.vs200 > 0, ris = (n.s200 || 0) > 0, st = up && ris ? "uptrend (bull)" : !up && !ris ? "downtrend (bear)" : "mixed / sideways";
    ob("trend", "Primary trend", up && ris ? "Uptrend" : !up && !ris ? "Downtrend" : "Mixed", `Nifty 50 is ${Math.abs(n.vs200).toFixed(1)}% ${up ? "above" : "below"} its 200-day average, and that average is ${ris ? "rising" : "falling"} (${f1(n.s200 || 0)}% over 20 days). By the moving-average test the primary trend reads as ${st}.`, up && ris ? "pos" : !up && !ris ? "neg" : "neu", "trend"); }
  const ni = M._nifty || {};
  if (ni.rsi != null) { const r = ni.rsi; ob("rsi", "Momentum (RSI)", `RSI ${r.toFixed(0)}${r > 70 ? ", overbought" : r < 30 ? ", oversold" : ""}`, `Nifty 50 RSI (14) is ${r.toFixed(0)}. ` + (r > 70 ? "That is above 70, the usual overbought line." : r < 30 ? "That is below 30, the usual oversold line." : r < 44 ? "That is below the 44-45 zone that a bull market rarely falls under." : r > 55 ? "That is above the 50-55 zone that a bear market rarely rises over." : "That is in the middle band (44-55), which by itself does not separate a bull from a bear phase."), r < 44 ? "neg" : r > 55 ? "pos" : "neu", "rsi"); }
  if (ni.macd != null) ob("macd", "Momentum (MACD)", `${ni.macd > ni.msig ? "Above" : "Below"} signal, ${ni.macd > 0 ? "above" : "below"} zero`, `Nifty 50 MACD is ${ni.macd > ni.msig ? "above" : "below"} its signal line and ${ni.macd > 0 ? "above" : "below"} zero.`, ni.macd > ni.msig && ni.macd > 0 ? "pos" : ni.macd < ni.msig && ni.macd < 0 ? "neg" : "neu", "macd");
  if (n.m1 != null && sx.m1 != null) { const same = (n.m1 >= 0) === (sx.m1 >= 0); ob("dow", "Index confirmation", same ? "Nifty and Sensex agree" : "Nifty and Sensex disagree", `Over one month the Nifty 50 moved ${f1(n.m1)}% and the Sensex ${f1(sx.m1)}%: ${same ? "the two indices confirm each other" : "the two indices disagree, so the move is not confirmed"}.`, "neu", "dow"); }
  if (breadth) ob("breadth", "Breadth", `${Math.round(breadth.above200)}% above 200-day avg`, `${Math.round(breadth.above200)}% of the ${breadth.n} covered stocks were above their 200-day average and ${Math.round(breadth.above50)}% above their 50-day average at the last close.`, breadth.above200 > 60 ? "pos" : breadth.above200 < 40 ? "neg" : "neu", null);
  const vx = g("^INDIAVIX"); if (vx.last != null) ob("vix", "Volatility", `India VIX ${vx.last.toFixed(1)}`, `India VIX (expected 30-day volatility of the Nifty) is ${vx.last.toFixed(1)}, ${f1(vx.m1 || 0).replace(/\.\d$/, "")}% in a month.`, (vx.m1 || 0) > 20 ? "neg" : "neu", null);
  const b = g("BZ=F");
  if (b.m1 != null) { const x = b.m1;
    if (x >= 5) ob("crude", "Crude oil", `Brent up ${x.toFixed(1)}% in a month`, `Brent crude is up ${x.toFixed(1)}% in a month ($${b.last.toFixed(1)}). Rising crude raises input costs for users such as airlines, paints and logistics and helps oil producers; as an importer, India feels it in fuel prices and inflation.`, "neg", "commod_eq");
    else if (x <= -5) ob("crude", "Crude oil", `Brent down ${Math.abs(x).toFixed(1)}% in a month`, `Brent crude is down ${Math.abs(x).toFixed(1)}% in a month ($${b.last.toFixed(1)}). Falling crude lowers input costs for users such as airlines, paints and logistics and squeezes oil producers; for an importer like India it eases fuel prices and inflation.`, "pos", "commod_eq");
    else ob("crude", "Crude oil", `Brent ${f1(x)}% in a month`, `Brent crude moved ${f1(x)}% in a month ($${b.last.toFixed(1)}), a modest change.`, "neu", "intl"); }
  const u = g("INR=X");
  if (u.m1 != null) { const x = u.m1;
    ob("rupee", "Rupee", x >= 1 ? `Weaker by ${x.toFixed(1)}% in a month` : x <= -1 ? `Stronger by ${Math.abs(x).toFixed(1)}% in a month` : "Steady against the dollar", x >= 1 ? `The rupee weakened ${x.toFixed(1)}% against the dollar in a month (₹${u.last.toFixed(2)}). A weaker rupee makes imports (crude, capital goods) dearer and helps exporters' rupee earnings.` : x <= -1 ? `The rupee strengthened ${Math.abs(x).toFixed(1)}% against the dollar in a month (₹${u.last.toFixed(2)}). Imports get cheaper; exporters earn fewer rupees per dollar.` : `The rupee was steady against the dollar (${f1(x)}% in a month, ₹${u.last.toFixed(2)}).`, x >= 1 ? "neg" : x <= -1 ? "pos" : "neu", "cad"); }
  const t = g("^TNX"); if (t.last != null && t.m1 != null) { const bp = Math.round(t.last * t.m1 / (100 + t.m1) * 100); ob("us10y", "US 10-year yield", `${t.last.toFixed(2)}%, ${bp > 0 ? "+" : bp < 0 ? "−" : ""}${Math.abs(bp)} bp in a month`, `The US 10-year yield is ${t.last.toFixed(2)}% (${bp > 0 ? "+" : bp < 0 ? "−" : ""}${Math.abs(bp)} basis points in a month). Foreign portfolio money, which NISM calls 'hot money' that can leave at any time, watches global rates.`, "neu", "fpi"); }
  const gl = ["^GSPC", "^IXIC", "^FTSE", "^GDAXI", "^N225", "^HSI", "000001.SS"].map(g), dn = gl.filter((x) => (x.m1 || 0) <= -5).length, upn = gl.filter((x) => (x.m1 || 0) >= 5).length;
  if (dn >= 3) ob("global", "World markets", `${dn} of 7 down 5% or more`, `${dn} of 7 major world indices fell 5% or more in a month. Integrated economies mean trouble in one region spreads to others.`, "neg", "global");
  else if (upn >= 3) ob("global", "World markets", `${upn} of 7 up 5% or more`, `${upn} of 7 major world indices rose 5% or more in a month.`, "pos", "global");
  else if (gl.some((x) => x.m1 != null)) ob("global", "World markets", "No broad move this month", `Fewer than three of the seven major world indices moved 5% or more in a month.`, "neu", "global");
  const rk = (sectCov || []).filter((x) => x.rel3 != null).sort((a, b) => b.rel3 - a.rel3);
  if (rk.length >= 4) ob("sectors", "Sector leaders", `${rk[0].name} leads, ${rk[rk.length - 1].name} lags`, `Against the Nifty 50 over 3 months, the strongest sectors were ${rk.slice(0, 3).map((x) => `${x.name} (${f1(x.rel3)}%)`).join(", ")}; the weakest were ${rk.slice(-3).map((x) => `${x.name} (${f1(x.rel3)}%)`).join(", ")}.`, "neu", "rsc");
  const d = g("DX-Y.NYB"); if (d.m1 != null && Math.abs(d.m1) >= 1.5) ob("dxy", "US dollar", `Dollar index ${d.m1 > 0 ? "up" : "down"} ${Math.abs(d.m1).toFixed(1)}%`, `The US dollar index ${d.m1 > 0 ? "rose" : "fell"} ${Math.abs(d.m1).toFixed(1)}% in a month. A ${d.m1 > 0 ? "stronger dollar usually weighs on" : "weaker dollar usually supports"} dollar-priced commodities.`, "neu", "dollar");
  const au = g("GC=F"); if (au.m1 != null && Math.abs(au.m1) >= 4) ob("gold", "Gold", `${au.m1 > 0 ? "Up" : "Down"} ${Math.abs(au.m1).toFixed(1)}% in a month`, `Gold ${au.m1 > 0 ? "rose" : "fell"} ${Math.abs(au.m1).toFixed(1)}% in a month ($${au.last.toFixed(0)}). Gold is the usual hedge investors turn to when inflation worries rise.`, "neu", "macro_ind");
  const cu = g("HG=F"); if (cu.m1 != null && Math.abs(cu.m1) >= 5) ob("copper", "Copper", `${cu.m1 > 0 ? "Up" : "Down"} ${Math.abs(cu.m1).toFixed(1)}% in a month`, `Copper ${cu.m1 > 0 ? "rose" : "fell"} ${Math.abs(cu.m1).toFixed(1)}% in a month. NISM reads a fall in copper as a possible sign of slowing industrial demand, weighing on metal and infrastructure stocks${cu.m1 > 0 ? "; a rise is the opposite reading" : ""}.`, cu.m1 > 0 ? "pos" : "neg", "commod_eq");
  if (feed && feed.themes) { const cov = feed.themes.filter((x) => ["geo", "trade", "energy", "politics", "people"].includes(x.id)).map((x) => [x.name, x.day || 0, x.short || x.name]).filter((x) => x[1]).sort((a, b) => b[1] - a[1]).slice(0, 3);
    if (cov.length) ob("geo", "World news", `Busiest: ${cov[0][2]}`, `The busiest world themes in the last 24 hours: ${cov.map(([a, c]) => `${a.toLowerCase()} (${c} stories)`).join(", ")}. Conflicts in oil regions, sanctions and trade wars mainly reach Indian stocks through crude prices, the rupee and supply chains.`, "neu", "geo"); }
  return R;
}
function inReadingsNow() {
  const L = mkLive(), cov = ((INS && INS.sectors) || []).filter((x) => x.kind !== "index");
  return L ? mkReadings(L.M, cov, INS && INS.breadth, LIVE) : ((INS && INS.readings) || []).map((r) => Object.assign({ short: "" }, r));
}

/* ----- small building blocks ----- */
function inRefBtn(key, id) {
  const R = (INS && INS.refs) || {}, r = R[key]; if (!r) return "";
  const open = IV.open.has(id);
  return `<button type="button" class="ref" aria-expanded="${open}" onclick="inTog('${id}')">${esc(r.src)}</button>${open ? `<div class="ref-says">${esc(r.says)}</div>` : ""}`;
}
function inTog(id) { IV.open.has(id) ? IV.open.delete(id) : IV.open.add(id); render(); }
function inSpark(a, cls) {
  if (!a || a.length < 2) return "";
  const mn = Math.min(...a), mx = Math.max(...a), w = 100, h = 28, k = (mx - mn) || 1, n = a.length;
  const pts = a.map((v, i) => `${(i / (n - 1) * w).toFixed(1)},${(h - 3 - (v - mn) / k * (h - 6)).toFixed(1)}`).join(" ");
  return `<svg class="spk ${cls || ""}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" vector-effect="non-scaling-stroke"/></svg>`;
}
function inFmt(k, v) {
  if (v == null || !isFinite(v)) return "–";
  if (k === "^TNX") return v.toFixed(2) + "%";
  if (k === "INR=X") return "₹" + v.toFixed(2);
  if (k === "BZ=F" || k === "HG=F") return "$" + v.toFixed(2);
  if (k === "GC=F") return "$" + Math.round(v).toLocaleString("en-IN");
  if (k === "DX-Y.NYB" || k === "^INDIAVIX") return v.toFixed(2);
  return v.toLocaleString("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
}
function inSeries(k) { return MKT && MKT.series && MKT.series.find((x) => x.t === k); }
function inDay(k) { const s = inSeries(k); if (!s || s.c.length < 2) return null; const c = s.c; return k === "^TNX" ? { bp: (c[c.length - 1] - c[c.length - 2]) * 100 } : { pct: (c[c.length - 1] / c[c.length - 2] - 1) * 100 }; }
function inMove(dm) { if (!dm) return ""; if (dm.bp != null) { const b = Math.round(dm.bp); return `<span class="${b > 0 ? "neg" : b < 0 ? "pos" : ""}">${b > 0 ? "+" : b < 0 ? "−" : ""}${Math.abs(b)} bp</span>`; } return `<span class="${inCl(dm.pct)}">${inPct(dm.pct, 2)}</span>`; }

/* ----- market tape ----- */
function inTape() {
  const L = mkLive(), M = L ? L.M : {};
  const it = TAPE.map((k) => {
    const m = M[k], s = inSeries(k), dm = inDay(k), up = dm && (dm.pct != null ? dm.pct : -dm.bp) >= 0;
    return `<button type="button" class="tk" onclick="inTapeGo('${k}')" title="${esc(MK_NAMES[k] || TAPE_NM[k])}: open the linked news"><span class="tk-n">${esc(TAPE_NM[k])}</span><span class="tk-v">${m ? inFmt(k, m.last) : "–"}</span><span class="tk-c ${dm ? (k === "^TNX" || k === "^INDIAVIX" || k === "INR=X" ? "flat" : up ? "up" : "dn") : ""}">${dm ? inMove(dm).replace(/class="[^"]*"/, "") : ""}</span>${s ? inSpark(s.c.slice(-22)) : ""}</button>`;
  }).join("");
  const st = MKT ? `${MKT.market_open ? "Live, about 15 minutes delayed" : "Latest close"}. Updated ${inAgo(MKT.updated)}.` : IV.mktBusy ? "Loading prices" : "Prices unavailable";
  return `<section class="tape" aria-label="Market tape"><div class="tape-row">${it}</div><div class="tape-st">${st}</div></section>`;
}

function inTapeGo(k) { if (typeof openIndex === "function") openIndex(k); else inGo("markets"); }

/* ----- section navigation ----- */
function inSubnav() {
  const V = [["overview", "Overview"], ["news", "News"], ["markets", "Markets"], ["stocks", "Stocks"], ["method", "Method"]];
  const names = INAMES ? Object.keys(INAMES) : [];
  return `<div class="ix-nav"><div class="ix-tabs" role="tablist" aria-label="Insights sections">${V.map(([k, l]) => `<button role="tab" aria-selected="${IV.view === k}" onclick="inGo('${k}')">${l}</button>`).join("")}</div>
  <form class="ix-find" onsubmit="inPick(this.elements.q.value,'NSE');this.elements.q.value='';return false"><input id="ix-q" name="q" list="ix-syms" placeholder="Find a stock, e.g. TCS" aria-label="Find a stock" autocapitalize="characters" autocomplete="off"><datalist id="ix-syms">${names.slice(0, 900).map((s) => `<option value="${esc(s)}">`).join("")}</datalist></form></div>`;
}
function inGo(v) { IV.view = v; if (v === "stocks") loadFund(); render(); const e = $("vIns"); if (e && e.getBoundingClientRect().top < 0) window.scrollTo({ top: window.scrollY + e.getBoundingClientRect().top - 50 }); }
function inTheme(t) { IV.theme = t; IV.who = ""; IV.linkF = ""; IV.shown = 30; inGo("news"); }
function inLinkF(k) { IV.linkF = k; IV.theme = "all"; IV.shown = 30; inGo("news"); }

/* ----- one story ----- */
function inLinkChips(x, max) {
  const L = inLinks(x); if (!L.sym.length && !L.idx.length) return "";
  const idx = L.idx.slice(0, 3).map((k) => { const dm = inDay(k); return `<button type="button" class="lk-i" onclick="openIndex('${k}')" title="${esc(MK_NAMES[k] || k)}: chart, moves and linked news">${esc(MK_NAMES[k] || k)}${dm ? " " + inMove(dm) : ""}</button>`; }).join("");
  const st = L.sym.slice(0, max || 5).map((s) => { const v = inPx(s); return `<button type="button" class="lk-s" onclick="openStock('${esc(s)}','NSE')" title="${esc(s)}: price, chart and links">${esc(s)}${v != null ? ` <span class="${inCl(v)}">${inPct(v)}</span>` : ""}</button>`; }).join("");
  return `<div class="ns-l"><span class="ns-why">${L.why.length ? "Linked through " + esc(L.why.join(", ")) : "Named in the headline"}</span>${idx}${st}</div>`;
}
function inStory(x, o) {
  o = o || {}; const N = LIVE || {}, th = (N.themes || []).find((t) => t.id === x.th);
  const also = (x.also || []).map((a) => a.s || a).join(", ");
  return `<li class="ns${o.lead ? " lead" : ""}"><a class="ns-h" href="${esc(x.u)}" target="_blank" rel="noopener noreferrer">${esc(x.t)}</a>
  <div class="ns-m"><span class="ns-src">${esc(x.s || "")}</span>${x.d ? `<span>${inAgo(x.d)}</span>` : ""}${x.n > 1 ? `<span title="Also reported by ${esc(also)}">${x.n} outlets</span>` : ""}${x.who && x.who.length ? `<span>${esc(x.who.join(", "))}</span>` : ""}${th && o.theme !== false ? `<button type="button" class="ns-th" onclick="inTheme('${th.id}')">${esc(th.short || th.name)}</button>` : ""}</div>
  ${inLinkChips(x, o.lead ? 6 : 4)}</li>`;
}

/* ----- overview ----- */
function inOverview() {
  const N = LIVE, top = (N && N.top) || [];
  const news = !N ? `<p class="ix-empty">${esc(IV.feedErr || "Loading the latest headlines…")}</p>`
    : `<ol class="nsl">${top.slice(0, 1).map((x) => inStory(x, { lead: true })).join("")}${top.slice(1, 8).map((x) => inStory(x)).join("")}</ol>
       <div class="ix-more"><button class="btn sm" onclick="inGo('news')">Open the news desk</button><span class="ix-fine">${ixN(N.pool)} headlines from ${(N.themes || []).length} themes over ${N.days || 7} days, refreshed every ${N.refresh_min === 60 ? "hour" : (N.refresh_min || 5) + " minutes"}${N.market_open ? " while the market is open" : " until the market opens"}.</span></div>`;
  return `<div class="ix-grid"><div class="ix-main">
    <section class="ix-sec o1"><header class="ix-h"><h2>Top stories</h2><p>The stories carried by the most outlets in the last 48 hours, with the indices and stocks they are linked to.</p></header>${news}</section>
    ${inSectorChart(false)}</div>
    <aside class="ix-rail">${inMarketRead()}${inHoldNews()}${inMostLinked(6)}</aside></div>`;
}
const MR_TK = { trend: "^NSEI", rsi: "^NSEI", macd: "^NSEI", dow: "^BSESN", vix: "^INDIAVIX", crude: "BZ=F", rupee: "INR=X", us10y: "^TNX", gold: "GC=F", copper: "HG=F", dxy: "DX-Y.NYB", global: "^GSPC" };
function inMarketRead() {
  const R = inReadingsNow(), keys = ["trend", "rsi", "breadth", "vix", "crude", "rupee", "us10y", "global", "sectors", "geo"];
  const rows = keys.map((k) => R.find((r) => r.k === k)).filter(Boolean);
  if (!rows.length) return `<section class="ix-card o2"><h3>Market read</h3><p class="ix-empty">Loading…</p></section>`;
  return `<section class="ix-card o2"><header class="ix-ch"><h3>Market read</h3><button class="btn ghost sm" onclick="inGo('markets')">All readings</button></header>
  <ul class="mr">${rows.map((r) => { const id = "mr-" + r.k, open = IV.open.has(id); return `<li><button type="button" class="mr-row" aria-expanded="${open}" onclick="inTog('${id}')"><span class="tn ${r.tone}" title="${TONE[r.tone]}"></span><span class="mr-a">${esc(r.area)}</span><span class="mr-v">${esc(r.short || "")}</span></button>${open ? `<div class="mr-d">${esc(r.text)}${r.ref ? `<div>${inRefBtn(r.ref, id + "-r")}</div>` : ""}${MR_TK[r.k] ? `<div><button type="button" class="btn ghost sm" style="margin-left:-8px" onclick="openIndex('${MR_TK[r.k]}')">Chart of ${esc(MK_NAMES[MR_TK[r.k]] || MR_TK[r.k])}</button></div>` : ""}</div>` : ""}</li>`; }).join("")}</ul>
  <p class="ix-fine"><span class="tn pos"></span> supportive <span class="tn neg"></span> caution <span class="tn neu"></span> neutral, as the cited NISM section reads such a number. Not a forecast.</p></section>`;
}
function inShort(s) { const v = INAMES && INAMES[s], n = Array.isArray(v) ? v[0] : v || ""; return n.replace(/\s+(Limited|Ltd\.?)$/i, ""); }
function inDirectCounts() {
  const c = {}; for (const x of inAllStories()) { const L = inLinks(x); for (const s of L.sym) { if (!c[s]) c[s] = { n: 0, d: 0 }; c[s].n++; } }
  return c;
}
function inHoldNews() {
  const H = (typeof openPos === "function" ? openPos() : []).filter((p) => p.exchange !== "BSE");
  if (!H.length || !LIVE) return "";
  const c = inDirectCounts(), rows = H.map((p) => ({ s: p.symbol, n: (c[p.symbol] || {}).n || 0 })).sort((a, b) => b.n - a.n);
  return `<section class="ix-card o3"><header class="ix-ch"><h3>Your holdings in the news</h3></header><ul class="ml">${rows.map((r) => { const v = inPx(r.s); return `<li><button type="button" onclick="openStock('${esc(r.s)}','NSE')"><b>${esc(r.s)}</b><span class="ml-name">${esc(inShort(r.s))}</span><span class="${inCl(v)}">${v != null ? inPct(v) : ""}</span><span class="ml-n">${r.n ? `${r.n} ${r.n === 1 ? "story" : "stories"}` : "No news"}</span></button></li>`; }).join("")}</ul></section>`;
}
function inMostLinked(n) {
  if (!LIVE) return "";
  const c = inDirectCounts(), rows = Object.entries(c).sort((a, b) => b[1].n - a[1].n).slice(0, n || 8);
  if (!rows.length) return "";
    return `<section class="ix-card o5"><header class="ix-ch"><h3>Stocks most in the news</h3></header><ul class="ml">${rows.map(([s, o]) => { const v = inPx(s); return `<li><button type="button" onclick="openStock('${esc(s)}','NSE')" title="Price, chart, linked news and links"><b>${esc(s)}</b><span class="ml-name">${esc(inShort(s))}</span><span class="${inCl(v)}">${v != null ? inPct(v) : ""}</span><span class="ml-n">${o.n}</span></button></li>`; }).join("")}</ul></section>`;
}

/* ----- sector strength chart (relative to the Nifty 50) ----- */
function inSectorData() {
  const L = mkLive(), cov = ((INS && INS.sectors) || []).filter((x) => x.kind !== "index");
  const idx = L ? L.sidx : ((INS && INS.sectors) || []).filter((x) => x.kind === "index");
  // Yahoo only carries history for a few NSE sector indices; below six, the covered-stock medians are the better picture
  const few = idx.filter((x) => x.rel3 != null).length < 6;
  return IV.secSrc === "stocks" || few ? { rows: cov, src: "stocks", few } : { rows: idx, src: "index", few };
}
function inSectorChart(full) {
  const D = inSectorData(), k = IV.secPer, rows = D.rows.filter((x) => x[k] != null).sort((a, b) => b[k] - a[k]);
  if (!rows.length) return "";
  const mx = Math.max(...rows.map((x) => Math.abs(x[k])), 1);
  const bars = rows.map((x) => { const v = x[k], w = Math.abs(v) / mx * 40, key = x.kind === "index" ? x.k : SEC_IDX[x.name]; const nn = key && LIVE ? inCountFor("i:" + key) : 0;
    return `<li><button type="button" class="sb" onclick="${x.kind === "index" ? `openIndex('${x.k}')` : `openGroup('sec','${esc(x.name)}')`}" title="${esc(x.name)}: ${inPct(v)} against the Nifty 50${nn ? `, ${nn} linked stories` : ""}"><span class="sb-n">${esc(x.name)}${x.n ? `<small>${x.n} stocks</small>` : ""}</span><span class="sb-t"><i class="${v >= 0 ? "up" : "dn"}" style="${v >= 0 ? "left:50%" : `right:50%`};width:${w.toFixed(2)}%"></i><em style="${v >= 0 ? `left:calc(50% + ${w.toFixed(2)}% + 6px)` : `right:calc(50% + ${w.toFixed(2)}% + 6px)`}">${inPct(v)}</em></span></button></li>`; }).join("");
  const seg = (key, val, l) => `<button type="button" aria-pressed="${IV[key] === val}" onclick="IV.${key}='${val}';render()">${l}</button>`;
  return `<section class="ix-sec o4"><header class="ix-h"><h2>Sector strength</h2><p>Each sector's return minus the Nifty 50's over the same period. Bars to the right did better than the index. ${inRefBtn("rsc", "sec-rsc")}</p></header>
  <div class="ix-ctl"><div class="seg2">${seg("secPer", "rel1", "1 month")}${seg("secPer", "rel3", "3 months")}</div>${D.few ? "" : `<div class="seg2">${seg("secSrc", "index", "NSE sector indices")}${seg("secSrc", "stocks", "Covered stocks by sector")}</div>`}</div>
  <ol class="sbars"><li class="sb-ax" aria-hidden="true"><span></span><span><span>Did worse than the Nifty 50</span><span>Did better</span></span></li>${bars}</ol><p class="ix-fine">${D.src === "index" ? "NSE sector indices, live prices." : "Median return of the covered stocks in each sector (sector names from Yahoo Finance), as of the last close."} Select a sector for its companies, chart and linked news.</p></section>`;
}

/* ----- news desk ----- */
function inFullFor(id) { const F = IV.full[id]; return F && F.stories && LIVE && F.updated === LIVE.updated ? F.stories : null; }
async function inLoadFull(id) {   // every story of the last 7 days for a theme ("all" = every theme), fetched on request
  IV.full[id] = { loading: true }; render();
  try { const r = await fetch("/api/dma?a=theme&id=" + encodeURIComponent(id)), j = await r.json(); IV.full[id] = r.ok && j.stories ? j : { error: j.error || "The full list could not be loaded." }; }
  catch (e) { IV.full[id] = { error: "The full list could not be loaded." }; }
  if (IV.full[id].stories && LIVE && IV.full[id].updated !== LIVE.updated) IV.full[id].updated = LIVE.updated;   // newer than the page's copy is fine
  IV.shown += 30; render();
}
function inStoriesFor() {
  const N = LIVE; if (!N) return [];
  let list;
  if (IV.linkF) list = (inFullFor("all") || inAllStories()).filter((x) => inStoryMatchesLink(x, IV.linkF));
  else if (IV.theme === "all") list = inFullFor("all") || inAllStories();
  else { const t = (N.themes || []).find((t) => t.id === IV.theme), F = inFullFor(IV.theme); list = F ? F.map((s) => Object.assign({ th: IV.theme }, s)) : t ? t.stories.map((s) => Object.assign({ th: t.id }, s)) : []; if (IV.who) list = list.filter((x) => (x.who || []).includes(IV.who)); }
  const byDate = (a, b) => String(b.d || "").localeCompare(String(a.d || ""));
  const byRank = (a, b) => (Math.min(b.n || 1, 6) - Math.min(a.n || 1, 6)) || byDate(a, b);
  return list.slice().sort(IV.list === "latest" || IV.linkF ? byDate : byRank);
}
function inNewsView() {
  const N = LIVE;
  if (!N) return `<div class="ix-empty">${esc(IV.feedErr || "Loading the latest headlines…")}</div>`;
  const themes = (N.themes || []).filter((t) => t.total);
  const total = N.stories_total || inAllStories().length, list = inStoriesFor(), shown = list.slice(0, IV.shown);
  const lf = IV.linkF, lfName = lf ? (lf.startsWith("i:") ? MK_NAMES[lf.slice(2)] || lf.slice(2) : lf.slice(2)) : "";
  const nav = `<nav class="nd-nav" aria-label="News themes"><button type="button" aria-current="${IV.theme === "all" && !lf}" onclick="inTheme('all')"><span>All stories</span><b>${ixN(total)}</b></button>${themes.map((t) => `<button type="button" aria-current="${IV.theme === t.id && !lf}" onclick="inTheme('${t.id}')" title="${esc(t.name)}: ${t.total} stories in ${N.days} days, ${t.day} in the last 24 hours"><span>${esc(t.short || t.name)}</span><b>${ixN(t.total)}</b></button>`).join("")}<p class="nd-cap">Stories in the last ${N.days} days</p></nav>`;
  const cur = themes.find((t) => t.id === IV.theme);
  const people = cur && cur.id === "people" && N.people && N.people.length ? `<div class="nd-people">${[["", "Everyone"]].concat(N.people.map((p) => [p.name, `${p.name} (${p.n})`])).map(([k, l]) => `<button type="button" class="chip${(IV.who || "") === k ? " on" : ""}" onclick="IV.who='${esc(k)}';IV.shown=30;render()">${esc(l)}</button>`).join("")}</div>` : "";
  const head = lf ? `<div class="nd-filter"><span>Stories linked to <b>${esc(lfName)}</b></span><button class="btn sm" onclick="IV.linkF='';render()">Clear</button></div>`
    : cur ? `<div class="nd-about"><h2>${esc(cur.name)}</h2><p>${esc(cur.why)} <span class="ix-fine">Most exposed: ${esc(cur.sectors)}.</span></p>${inRefBtn(cur.ref, "th-" + cur.id)}</div>` : `<div class="nd-about"><h2>All stories</h2><p>Every story collected in the last ${N.days} days from established outlets, grouped when several outlets carry it.</p></div>`;
  const bar = `<div class="nd-bar"><div class="seg2"><button type="button" aria-pressed="${IV.list !== "latest" && !lf}" ${lf ? "disabled" : ""} onclick="IV.list='top';render()">Most reported</button><button type="button" aria-pressed="${IV.list === "latest" || !!lf}" onclick="IV.list='latest';render()">Latest</button></div>
    <span class="ix-fine">${inListNote(list, cur, lf, total)}</span><span class="nd-st"><span class="nd-live ${N.market_open ? "on" : ""}" title="${N.market_open ? "Refreshed every 5 minutes while the market is open" : "Refreshed every hour while the market is closed"}">${N.market_open ? "Live" : "Hourly"}</span><span class="ix-fine">Updated ${inAgo(N.updated)}</span><button class="btn sm" onclick="loadFeed(true)" ${IV.feedBusy ? "disabled" : ""}>${IV.feedBusy ? "Refreshing" : "Refresh"}</button></span></div>`;
  const fid = lf ? "all" : IV.theme, F = IV.full[fid], avail = lf ? null : cur ? cur.total : total, canFull = !inFullFor(fid) && (lf || avail > list.length);
  const more = list.length > IV.shown ? `<button class="btn nd-more" onclick="IV.shown+=30;render()">Show 30 more</button>`
    : canFull ? `<button class="btn nd-more" onclick="inLoadFull('${fid}')" ${F && F.loading ? "disabled" : ""}>${F && F.loading ? "Loading…" : lf ? `Search all ${N.days} days of stories` : `Load all ${ixN(avail)} stories from the last ${N.days} days`}</button>${F && F.error ? `<p class="ix-fine">${esc(F.error)}</p>` : ""}` : "";
  const items = shown.length ? `<ol class="nsl">${shown.map((x) => inStory(x, { theme: IV.theme === "all" || !!lf })).join("")}</ol>${more}` : `<p class="ix-empty">No stories here right now.</p>${more}`;
  const rail = `<aside class="nd-rail">${inMostLinked(10)}${inIdxMentions()}<section class="ix-card"><h3>How this works</h3><p class="ix-fine" style="margin:0">${esc(N.note || "")}</p><div style="margin-top:6px">${inRefBtn("emh", "n-emh")}</div><div>${inRefBtn("bias", "n-bias")}</div></section></aside>`;
  return `<div class="nd">${nav}<div class="nd-main">${head}${people}${bar}${items}</div>${rail}</div>`;
}
function inListNote(list, cur, lf, total) {
  const n = list.length, sorted = IV.list === "latest" || lf ? "newest first" : "most reported first";
  if (lf) return `${n} ${n === 1 ? "story" : "stories"}, ${sorted}`;
  const all = cur ? cur.total : total;
  return n < all ? `Top ${n} of ${ixN(all)}, ${sorted}` : `${ixN(n)} ${n === 1 ? "story" : "stories"}, ${sorted}`;
}
function inIdxMentions() {
  if (!LIVE) return "";
  const keys = ["^NSEI", "^NSEBANK", "NIFTY_FIN_SERVICE.NS", "^CNXIT", "^CNXPHARMA", "^CNXENERGY", "^CNXMETAL", "^CNXAUTO", "^CNXREALTY", "^CNXFMCG", "^CNXMEDIA", "BZ=F", "GC=F", "INR=X"];
  const rows = keys.map((k) => [k, inCountFor("i:" + k)]).filter((r) => r[1]).sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (!rows.length) return "";
  return `<section class="ix-card"><header class="ix-ch"><h3>Indices and prices in the news</h3></header><ul class="ml">${rows.map(([k, n]) => { const dm = inDay(k); return `<li><button type="button" onclick="openIndex('${k}')"><b>${esc(MK_NAMES[k] || k)}</b><span class="ml-name"></span><span>${dm ? inMove(dm) : ""}</span><span class="ml-n">${n}</span></button></li>`; }).join("")}</ul></section>`;
}

/* ----- markets ----- */
function inMarketsView() {
  const L = mkLive(), groups = L ? L.groups : (INS && INS.groups) || [];
  const pc = (v) => `<td class="${inCl(v)}">${inPct(v)}</td>`;
  const tbl = (g) => `<section class="ix-sec"><header class="ix-h"><h2>${esc(g.name)}</h2></header><div class="tw"><table class="mt"><thead><tr><th>Name</th><th>Last</th><th>Day</th><th>1 week</th><th>1 month</th><th>3 months</th><th>1 year</th><th>vs 200-day avg</th><th>From 52-week high</th><th class="c">Last 3 months</th><th>Linked news</th></tr></thead><tbody>${g.items.map((x) => { const dm = inDay(x.k), s = inSeries(x.k), n = LIVE ? inCountFor("i:" + x.k) : 0;
    return `<tr><td>${entI(x.k, "<b>" + esc(x.name) + "</b>")}</td><td>${inFmt(x.k, x.last)}</td><td>${dm ? inMove(dm) : inPct(x.d1)}</td>${pc(x.w1)}${pc(x.m1)}${pc(x.m3)}${pc(x.y1)}${pc(x.vs200)}<td>${inPct(x.hi52)}</td><td class="c">${s ? inSpark(s.c.slice(-63), "in") : inSpark(x.spark, "in")}</td><td>${n ? `<button class="btn ghost sm" onclick="inLinkF('i:${x.k}')">${n} ${n === 1 ? "story" : "stories"}</button>` : `<span class="ix-fine">None</span>`}</td></tr>`; }).join("")}</tbody></table></div></section>`;
  const R = inReadingsNow(), mp = INS && INS.market_pe, br = INS && INS.breadth;
  const stats = `<section class="ix-sec"><header class="ix-h"><h2>Breadth and valuation</h2><p>From the daily update after the close.</p></header><div class="kpis">${br ? `<div class="kpi"><span>Covered stocks above their 200-day average</span><b>${Math.round(br.above200)}%</b><small>${br.n} stocks; above the 50-day: ${Math.round(br.above50)}%</small></div>` : ""}${mp ? `<div class="kpi"><span>P/E of the ${mp.n} largest covered companies, combined</span><b>${inNum(mp.pe, 1)}</b><small>Earnings yield ${inNum(100 / mp.pe, 2)}%. Compare with the 10-year government bond yield.</small></div>` : ""}</div><div>${inRefBtn("dy", "v-dy")}</div></section>`;
  const reads = `<section class="ix-sec"><header class="ix-h"><h2>All readings</h2><p>Each line is a fixed rule applied to the live numbers. Supportive or caution is what the cited NISM section says such a reading usually indicates, not a forecast.</p></header><ul class="rl">${R.map((r, i) => `<li><span class="rl-t ${r.tone}">${TONE[r.tone]}</span><div><b>${esc(r.area)}</b><p>${esc(r.text)}</p>${r.ref ? inRefBtn(r.ref, "rl" + i) : `<span class="ix-fine">Data only; no NISM rule is attached to this number.</span>`}</div></li>`).join("")}</ul></section>`;
  return `${groups.map(tbl).join("")}<div class="ix-cols2">${inSectorChart(true)}<div>${stats}</div></div>${reads}`;
}

/* ----- method ----- */
function inMethodView() {
  const R = (INS && INS.refs) || {};
  return `<div class="ix-narrow"><section class="ix-sec"><header class="ix-h"><h2>Where the readings come from</h2><p>The rules on these pages paraphrase sections of the NISM certification workbooks. Where a number has no NISM rule (India VIX, market breadth, the 52-week range) it is shown as data only. Thresholds such as RSI 70 and 30, ADX 25, debt to equity of 1 and PEG of 1 are the ones the workbooks state.</p></header>
  <dl class="refs">${Object.values(R).map((r) => `<div><dt>${esc(r.src)}</dt><dd>${esc(r.says)}</dd></div>`).join("")}</dl></section>
  <section class="ix-sec"><header class="ix-h"><h2>How the news is collected</h2></header><p>${esc((LIVE && LIVE.note) || "Collected from Google News searches and sections, limited to established outlets.")}</p><p>Stories are linked to indices and stocks by fixed keyword rules (crude oil, interest rates, the rupee, H-1B visas, pharma tariffs and so on) and by company names in the headline. The link names the rule it used, so a link is a pointer to read further, not a judgement that the story will move the price.</p></section>
  <section class="ix-sec"><header class="ix-h"><h2>What these pages are not</h2></header><p>Under SEBI's research analyst rules (NISM Series XV, chapter 14), research reports and recommendations for others need a registered analyst, disclosures and conflict checks. These pages apply written rules to public numbers for your own use. They give no price targets or buy and sell calls, and headlines are not verified.</p></section></div>`;
}

/* ----- stocks ----- */
function inStocksView() {
  if (FUND === null) { loadFund(); return `<div class="ix-empty">Loading…</div>`; }
  const hold = (typeof openPos === "function" ? openPos() : []).map((p) => [p.symbol, p.exchange]);
  const wl = (typeof WL !== "undefined" && Array.isArray(WL) ? WL : []).map((w) => [w.symbol, w.exchange]);
  const hot = LIVE ? Object.entries(inDirectCounts()).sort((a, b) => b[1].n - a[1].n).slice(0, 8).map(([s]) => [s, "NSE"]) : [];
  const pick = (lbl, arr) => (arr.length ? `<div class="pk"><span>${lbl}</span>${arr.slice(0, 16).map(([s, e]) => `<button class="chip${IV.sym === s && IV.ex === (e || "NSE") ? " on" : ""}" onclick="inPick('${esc(s)}','${e || "NSE"}')">${esc(s)}${e === "BSE" ? " (BSE)" : ""}</button>`).join("")}</div>` : "");
  const finder = `<section class="ix-card sk-find"><form onsubmit="inPick(this.elements.q.value,this.elements.ex.value);return false" class="sk-form"><input name="q" id="in-q" list="ix-syms" placeholder="Symbol, e.g. RELIANCE" autocapitalize="characters" autocomplete="off" aria-label="Symbol"><select name="ex" aria-label="Exchange"><option${IV.ex === "NSE" ? " selected" : ""}>NSE</option><option${IV.ex === "BSE" ? " selected" : ""}>BSE</option></select><button class="btn pri">Show</button></form>${pick("Your holdings", hold)}${pick("Watchlist", wl)}${pick("Most in the news", hot)}
  <p class="ix-fine" style="margin:8px 0 0">${esc((FUND && FUND.universe) || "")} have technical and financial numbers ready${FUND && FUND.fund_updated ? ` (financials refreshed ${new Date(FUND.fund_updated).toLocaleDateString("en-IN", { day: "numeric", month: "short" })})` : ""}. Any other NSE or BSE stock gets technical numbers fetched live.</p></section>`;
  if (!IV.sym) return finder;
  const strip = `<div class="pk-strip">${pick("Holdings", hold)}${pick("Watchlist", wl)}${pick("In the news", hot.slice(0, 6))}</div>`;
  const key = IV.ex + ":" + IV.sym, pre = IV.ex === "NSE" && FUND.stocks ? FUND.stocks[IV.sym] : null, live = IV.chart[key];
  const t = pre ? pre.t : live ? live.t : null, f = IV.ex === "NSE" && FUND.fund ? FUND.fund[IV.sym] : null;
  if (!t && IV.busy) return strip + `<div class="ix-empty">Fetching ${esc(IV.sym)}…</div>`;
  if (!t && !f) return finder + `<div class="ix-empty">${esc(IV.err || "No data for " + IV.sym + ".")}</div>`;
  const mpe = INS && INS.market_pe ? INS.market_pe.pe : null, R = inStockReadings(t, f, FUND.sector_med, mpe, IV.sym), all = R.T.concat(R.F);
  const cnt = (k) => all.filter((x) => x.tone === k).length, name = inName(IV.sym);
  const tv = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent((IV.ex === "BSE" ? "BSE:" : "NSE:") + IV.sym)}`;
  const head = `<section class="sk-head"><div><h2>${esc(IV.sym)} <span class="tag ex">${IV.ex}</span></h2><p>${esc(name || "")}${f && f.sec ? `<span>${entG("sec", f.sec)}${f.ind ? " › " + entG("ind", f.ind) : ""}</span>` : ""}${f && f.mcap ? `<span>Market cap ₹${inNum(f.mcap / 1e7, 0)} crore</span>` : ""}</p></div>
   <div class="sk-px"><b>${t ? "₹" + inNum(t.p, 2) : "–"}</b><span>${t ? `<span class="${inCl(t.d1)}">${inPct(t.d1)} day</span><span class="${inCl(t.m1)}">${inPct(t.m1)} 1 month</span><span class="${inCl(t.y1)}">${inPct(t.y1)} 1 year</span>` : ""}</span><small>Close of ${esc(inDate(t && t.date))}.</small></div></section>${typeof entStockLinks === "function" ? `<div class="sk-links">${entStockLinks(IV.sym, IV.ex)}<button type="button" class="btn sm" onclick="openStock('${esc(IV.sym)}','${IV.ex}')">Interactive chart</button></div>` : ""}
   <div class="sk-tally"><span class="tn pos"></span>${cnt("pos")} supportive<span class="tn neg"></span>${cnt("neg")} caution<span class="tn neu"></span>${cnt("neu")} neutral<span class="ix-fine">A count of the readings below, not a verdict.</span></div>`;
  const tabs = [["summary", "Summary"], ["tech", "Technical"], ["fin", "Financials"], ["peers", "Peers"], ["news", "News"]];
  const tabbar = `<div class="sk-tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" aria-selected="${IV.stab === k}" onclick="IV.stab='${k}';render()">${l}</button>`).join("")}</div>`;
  const rl = (L, pre) => (L.length ? `<ul class="rl">${L.map((r, i) => `<li><span class="rl-t ${r.tone}">${TONE[r.tone]}</span><div><b>${esc(r.area)}</b><p>${esc(r.text)}</p>${r.ref ? inRefBtn(r.ref, pre + i) : ""}</div></li>`).join("")}</ul>` : `<p class="ix-empty">No readings.</p>`);
  let body = "";
  if (IV.stab === "summary") {
    const kv = (l, v, c) => `<div><span>${l}</span><b class="${c || ""}">${v}</b></div>`;
    const keys = `<div class="sk-kv">${t ? kv("vs 44-day avg", inPct(t.vs44), inCl(t.vs44)) + kv("vs 200-day avg", inPct(t.vs200), inCl(t.vs200)) + kv("RSI (14)", inNum(t.rsi, 0)) + kv("From 52-week high", inPct(t.hi52)) + kv("vs Nifty, 6 months", t.rsc != null ? inNum(t.rsc, 0) : "–") : ""}${f ? kv("P/E", f.pe > 0 ? inNum(f.pe, 1) : "–") + kv("ROE", f.roe != null ? inPct(f.roe * 100) : "–") + kv("Debt/equity", f.de != null ? inNum(f.de, 2) : "–") + kv("Revenue growth", f.revg != null ? inPct(f.revg * 100) : "–") : ""}</div>`;
    const top = all.filter((r) => r.tone !== "neu").slice(0, 6);
    const ln = inStockLinked().slice(0, 4);
    body = `${keys}<div class="sk-2"><section><h3>Readings that stand out</h3>${rl(top, "su")}</section><section><h3>Linked news</h3>${ln.length ? `<ol class="nsl sm">${ln.map((x) => inStory(x)).join("")}</ol><button class="btn ghost sm" onclick="IV.stab='news';render()">All news for ${esc(IV.sym)}</button>` : `<p class="ix-empty">No story in the live feed names ${esc(IV.sym)} right now.</p>`}</section></div>`;
  } else if (IV.stab === "tech") body = `<p class="ix-fine">From daily prices${pre ? "" : " fetched live"}. NISM's technical chapter treats these as tools to read trend and momentum, not certainties.</p>${t ? rl(R.T, "t") : `<p class="ix-empty">No price history.</p>`}`;
  else if (IV.stab === "fin") {
    const q = f && f.q && f.q.length ? `<h3>Quarterly results</h3><div class="tw"><table class="mt"><thead><tr><th>Quarter ended</th><th>Revenue (₹ crore)</th><th>Net profit (₹ crore)</th><th>Net margin</th></tr></thead><tbody>${f.q.slice().reverse().map((x) => `<tr><td>${esc(x.d)}</td><td>${x.rev == null ? "–" : inNum(x.rev / 1e7, 0)}</td><td class="${inCl(x.ni)}">${x.ni == null ? "–" : inNum(x.ni / 1e7, 0)}</td><td>${x.rev && x.ni != null ? inPct((x.ni / x.rev) * 100) : "–"}</td></tr>`).join("")}</tbody></table></div>` : "";
    body = f ? `<p class="ix-fine">Latest reported numbers from Yahoo Finance (they can lag or contain errors; check the annual report), compared with the median of covered companies in the same sector.</p>${rl(R.F, "f")}${q}` : `<p class="ix-empty">Financial numbers are collected for covered NSE stocks only.</p>`;
  } else if (IV.stab === "peers") {
    const P = f && f.sec && FUND.fund ? Object.entries(FUND.fund).filter(([s, o]) => o.sec === f.sec && (o.ind === f.ind || !f.ind) && o.mcap).sort((a, b) => b[1].mcap - a[1].mcap).slice(0, 12) : [];
    body = P.length > 1 ? `<p class="ix-fine">Same industry among covered companies, largest first. ${inRefBtn("peer", "p-peer")}</p><div class="tw"><table class="mt"><thead><tr><th>Company</th><th>Market cap (₹ cr)</th><th>P/E</th><th>P/B</th><th>ROE</th><th>Debt/equity</th><th>Op. margin</th><th>1 year</th></tr></thead><tbody>${P.map(([s, o]) => { const tt = FUND.stocks[s] && FUND.stocks[s].t; return `<tr${s === IV.sym ? ' class="on"' : ""}><td>${entS(s, "NSE")}</td><td>${inNum(o.mcap / 1e7, 0)}</td><td>${o.pe > 0 ? inNum(o.pe, 1) : "–"}</td><td>${inNum(o.pb, 2)}</td><td>${o.roe == null ? "–" : inPct(o.roe * 100)}</td><td>${inNum(o.de, 2)}</td><td>${o.opm == null ? "–" : inPct(o.opm * 100)}</td><td class="${inCl(tt && tt.y1)}">${inPct(tt && tt.y1)}</td></tr>`; }).join("")}</tbody></table></div>` : `<p class="ix-empty">No peer data for this company.</p>`;
  } else {
    const ln = inStockLinked(), secK = f && SEC_IDX[f.sec];
    const sector = secK ? inAllStories().filter((x) => !ln.includes(x) && inLinks(x).idx.includes(secK)).slice(0, 8) : [];
    const q = (name ? name.replace(/\b(limited|ltd\.?|ltd)\b/gi, "").trim() : IV.sym) + " share", N2 = IV.news[q];
    body = `<div class="sk-2"><section><h3>Linked from the live feed</h3>${ln.length ? `<ol class="nsl sm">${ln.slice(0, 15).map((x) => inStory(x)).join("")}</ol>` : `<p class="ix-empty">No story in the live feed names ${esc(IV.sym)} right now.</p>`}${sector.length ? `<h3 style="margin-top:16px">Its sector (${esc(MK_NAMES[secK])})</h3><ol class="nsl sm">${sector.map((x) => inStory(x)).join("")}</ol>` : ""}</section>
    <section><h3>Company search, last 14 days</h3>${!N2 || N2.loading ? `<p class="ix-empty">Loading…</p>` : N2.error ? `<p class="ix-empty">${esc(N2.error)}</p>` : N2.items && N2.items.length ? `<ol class="nsl sm">${N2.items.slice(0, 15).map((x) => inStory({ t: x.t, u: x.u, s: x.s, d: x.d, n: 1 }, { theme: false })).join("")}</ol>` : `<p class="ix-empty">No headlines found.</p>`}</section></div>`;
  }
  return strip + `<article class="sk">${head}${tabbar}<div class="sk-body">${body}</div></article>`;
}
function inDate(d) { if (!d) return ""; const x = new Date(String(d).slice(0, 10) + "T00:00:00"); return isNaN(x) ? String(d) : x.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); }
function inStockLinked() { return IV.sym ? inAllStories().filter((x) => inLinks(x).sym.includes(IV.sym)).sort((a, b) => String(b.d || "").localeCompare(String(a.d || ""))) : []; }

/* ----- entry point ----- */
function renderIns() {
  const el = $("vIns"); if (!el) return;
  if (INS === null) loadIns();
  if (MKT === null && !IV.mktBusy) loadMkt();
  if (LIVE === null && !IV.feedBusy) loadFeed();
  if (IV.view === "stocks" && FUND === null) loadFund();
  const a = document.activeElement, keep = a && el.contains(a) && a.id && (a.tagName === "INPUT") ? { id: a.id, v: a.value, s: a.selectionStart, e: a.selectionEnd } : null;
  const body = IV.view === "news" ? inNewsView() : IV.view === "markets" ? inMarketsView() : IV.view === "stocks" ? inStocksView() : IV.view === "method" ? inMethodView() : inOverview();
  el.innerHTML = `<div class="ix">${inTape()}${inSubnav()}<div class="ix-body">${body}</div></div>`;
  if (keep) { const n = document.getElementById(keep.id); if (n) { n.value = keep.v; n.focus(); try { n.setSelectionRange(keep.s, keep.e); } catch (e) {} } }
}



/* ---------- the same stock insights inside the Screener and My Positions rows ---------- */
const SCRT = {};   // open tab per stock
async function scrTech(sym, ex) {   // technical numbers for a stock the daily update does not cover: fetched live once
  const key = ex + ":" + sym; if (IV.chart[key] || IV.chart[key] === 0) return; IV.chart[key] = 0;
  try {
    let t = sym + ".NS";
    if (ex === "BSE") { const c = typeof entBseCode === "function" ? await entBseCode(sym) : null; t = (c || sym) + ".BO"; }
    const r = await fetch("/api/dma?a=chart&t=" + encodeURIComponent(t)), j = await r.json();
    IV.chart[key] = r.ok && j.c ? { name: j.name, t: inTech(j, INS && INS.nifty) } : { err: j.error || "No price history." };
  } catch (e) { IV.chart[key] = { err: "Could not reach the price source." }; }
  render();
}
function scrTab(k, t) { SCRT[k] = t; render(); }
function scrIns(sym, ex) {
  if (FUND === null) loadFund(); if (INS === null) loadIns(); if (LIVE === null && !IV.feedBusy) loadFeed();
  const k = ex + ":" + sym, pre = ex === "NSE" && FUND && FUND.stocks ? FUND.stocks[sym] : null, f = ex === "NSE" && FUND && FUND.fund ? FUND.fund[sym] : null;
  if (!pre && FUND) scrTech(sym, ex);
  const live = IV.chart[k], t = pre ? pre.t : live && live.t ? live.t : null;
  const mpe = INS && INS.market_pe ? INS.market_pe.pe : null, R = (t || f) ? inStockReadings(t, f, FUND && FUND.sector_med, mpe, sym) : { T: [], F: [] }, all = R.T.concat(R.F);
  const news = ex === "NSE" ? inAllStories().filter((x) => inLinks(x).sym.includes(sym)).sort((a, b) => String(b.d || "").localeCompare(String(a.d || ""))) : [];
  const tab = SCRT[k] || "read", cnt = (x) => all.filter((r) => r.tone === x).length;
  const tabs = [["read", "Key readings"], ["tech", "Technical"], ["fin", "Financials"], ["news", `News (${news.length})`], ["links", "Links"]];
  const rl = (L, p) => (L.length ? `<ul class="rl">${L.map((r, i) => `<li><span class="rl-t ${r.tone}">${TONE[r.tone]}</span><div><b>${esc(r.area)}</b><p>${esc(r.text)}</p>${r.ref ? inRefBtn(r.ref, p + k + i) : ""}</div></li>`).join("")}</ul>` : "");
  const wait = !FUND || (!pre && (live === 0 || live === undefined)) ? `<p class="ix-empty">Loading the readings…</p>` : "";
  let body = "";
  if (tab === "read") {
    const kv = (l, v, c) => `<div><span>${l}</span><b class="${c || ""}">${v}</b></div>`;
    const keys = t || f ? `<div class="sk-kv">${t ? kv("vs 200-day avg", inPct(t.vs200), inCl(t.vs200)) + kv("RSI (14)", inNum(t.rsi, 0)) + kv("ADX", inNum(t.adx, 0)) + kv("vs Nifty, 6 months", t.rsc != null ? inNum(t.rsc, 0) : "–") + kv("From 52-week high", inPct(t.hi52)) : ""}${f ? kv("P/E", f.pe > 0 ? inNum(f.pe, 1) : "–") + kv("ROE", f.roe != null ? inPct(f.roe * 100) : "–") + kv("Debt/equity", f.de != null ? inNum(f.de, 2) : "–") + kv("Revenue growth", f.revg != null ? inPct(f.revg * 100) : "–") : ""}</div>` : "";
    const top = all.filter((r) => r.tone !== "neu").slice(0, 5);
    body = wait || (all.length ? `${keys}${rl(top, "sr")}` : `<p class="ix-empty">${esc((live && live.err) || "No readings for this stock.")}</p>`);
  } else if (tab === "tech") body = wait || rl(R.T, "st") || `<p class="ix-empty">No price history.</p>`;
  else if (tab === "fin") body = f ? `<p class="ix-fine">Latest reported numbers from Yahoo Finance, compared with the median of covered companies in ${entG("sec", f.sec)}${f.ind ? " (" + entG("ind", f.ind) + ")" : ""}.</p>${rl(R.F, "sf")}` : `<p class="ix-empty">Financial numbers are collected for the ${esc((FUND && FUND.universe) || "most traded NSE stocks")}. For this one, open Screener.in from the Links tab.</p>`;
  else if (tab === "news") body = news.length ? `<ol class="nsl sm">${news.slice(0, 8).map((x) => inStory(x)).join("")}</ol>` : `<p class="ix-empty">${LIVE ? "No story in the live feed (last 7 days) names this stock." : "Loading the news feed…"}</p>`;
  else body = `${typeof entStockLinks === "function" ? `<div class="eq-links">${entStockLinks(sym, ex)}</div>` : ""}<ul class="eq-app" style="margin-top:12px">${typeof entStratToday === "function" ? entStratToday(sym, ex) : ""}</ul>`;
  return `<section class="sci" onclick="event.stopPropagation()"><div class="sci-h"><h4>Stock insights</h4>${all.length ? `<span class="sci-t"><span class="tn pos"></span>${cnt("pos")} supportive <span class="tn neg"></span>${cnt("neg")} caution <span class="tn neu"></span>${cnt("neu")} neutral</span>` : ""}<span class="grow"></span><button type="button" class="btn ghost sm" onclick="openStock('${esc(sym)}','${ex}')">Interactive chart</button><button type="button" class="btn ghost sm" onclick="go('ins');inPick('${esc(sym)}','${ex}')">Full analysis</button></div>
   <div class="sk-tabs sci-tabs" role="tablist">${tabs.map(([x, l]) => `<button type="button" role="tab" aria-selected="${tab === x}" onclick="event.stopPropagation();scrTab('${k}','${x}')">${l}</button>`).join("")}</div><div class="sci-b">${body}</div>
   <p class="ix-fine sci-f">Readings apply fixed rules from the NISM workbooks to public numbers. A count of readings, not a verdict.</p></section>`;
}
