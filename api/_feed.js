// Live market-moving news. Collected from Google News (search results and the Business / World / India / Technology
// sections), limited to established outlets, grouped when several outlets carry the same story, and sorted into themes.
// A pool of headlines is kept for 7 days and topped up on every refresh, so coverage builds up instead of being one snapshot.
// Refresh: every 5 minutes while the Indian market is open (Mon-Fri 09:00-15:30 IST), hourly otherwise.
const CFG = require("./_newscfg.json");
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36";
const RX = (s) => new RegExp(s, "i");
const JUNK = RX(CFG.junk), MARKET = RX(CFG.market);
const THEMES = CFG.themes.map((t) => ({ ...t, kwR: RX(t.kw), needR: t.need ? RX(t.need) : null }));
const PEOPLE = CFG.people.map(([n, r]) => [n, RX(r)]);
const STOP = new Set("the and for with from after over amid says said will its this that into than what how why are has have was were been new more about".split(" "));

function marketOpen(d = new Date()) {
  const ist = new Date(d.getTime() + 330 * 60000), wd = ist.getUTCDay(), m = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  return wd >= 1 && wd <= 5 && m >= 9 * 60 && m <= 15 * 60 + 30;
}
const unesc = (s) => String(s || "").replace(/<!\[CDATA\[|\]\]>/g, "").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&nbsp;/g, " ").trim();
const dom = (u) => { const m = String(u || "").match(/^https?:\/\/([^/]+)/i); let d = m ? m[1].toLowerCase() : ""; return d.startsWith("www.") ? d.slice(4) : d; };
function srcName(d) {
  if (CFG.sources[d]) return CFG.sources[d];
  for (const k of Object.keys(CFG.sources)) if (d.endsWith("." + k)) return CFG.sources[k];
  return null;
}
function parse(xml, origin) {
  const out = [], now = Date.now();
  for (const it of String(xml).match(/<item\b[\s\S]*?<\/item>/gi) || []) {
    const g = (k) => { const m = it.match(new RegExp(`<${k}\\b[^>]*>([\\s\\S]*?)</${k}>`, "i")); return m ? m[1] : ""; };
    const sm = it.match(/<source\b[^>]*url="([^"]+)"[^>]*>([\s\S]*?)<\/source>/i);
    let t = unesc(g("title")); const u = unesc(g("link")), src = sm ? unesc(sm[2]) : "", d0 = dom(sm ? sm[1] : "");
    if (src && t.endsWith(" - " + src)) t = t.slice(0, -src.length - 3);
    let ts = Date.parse(unesc(g("pubDate"))); if (isNaN(ts)) continue;
    if (ts > now + 600000) ts -= 330 * 60000;                       // Indian time labelled as UTC
    const name = srcName(d0);
    if (!t || !/^https?:\/\//.test(u) || !name || JUNK.test(t)) continue;
    out.push({ t: t.slice(0, 220), u: u.slice(0, 600), s: name, d: ts, o: origin });
  }
  return out;
}
async function get(url, ms = 7000) {
  const ac = new AbortController(), tm = setTimeout(() => ac.abort(), ms);
  try { const r = await fetch(url, { headers: { "user-agent": UA }, signal: ac.signal }); return r.ok ? await r.text() : ""; }
  catch (e) { return ""; } finally { clearTimeout(tm); }
}
async function pool(tasks, n) { const out = []; let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < tasks.length) { const k = i++; out[k] = await tasks[k](); } })); return out; }
const qurl = (q, days) => "https://news.google.com/rss/search?" + new URLSearchParams({ q: `${q} when:${days}d`, hl: "en-IN", gl: "IN", ceid: "IN:en" });
const surl = (sec, gl) => `https://news.google.com/rss/headlines/section/topic/${sec}?` + new URLSearchParams({ hl: gl === "IN" ? "en-IN" : "en-US", gl, ceid: `${gl}:en` });

// every refresh fetches the sections plus one third of the searches (rotating), so a full pass takes three refreshes
function batch(k) {
  const all = []; THEMES.forEach((t) => t.q.forEach((q) => all.push([t.id, q])));
  return k === "all" ? all : all.filter((_, i) => i % 3 === k % 3);
}
const toks = (t) => new Set((t.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 2 && !STOP.has(w)));
function same(a, b) { let i = 0; for (const x of a) if (b.has(x)) i++; const u = a.size + b.size - i; return (u && i / u >= 0.5) || (i >= 5 && i / Math.min(a.size, b.size) >= 0.7); }
function cluster(items) {
  const st = [];
  for (const x of items.slice().sort((a, b) => b.d - a.d)) {
    const tk = toks(x.t); if (!tk.size) continue;
    const s = st.find((s) => same(tk, s.tk));
    if (s) { if (!s.out.some((o) => o.s === x.s)) s.out.push({ s: x.s, u: x.u }); s.first = Math.min(s.first, x.d); }
    else st.push({ t: x.t, u: x.u, s: x.s, d: x.d, first: x.d, tk, out: [{ s: x.s, u: x.u }] });
  }
  return st;
}
const rank = (a, b) => Math.min(b.out.length, 6) - Math.min(a.out.length, 6) || b.d - a.d;
const strip = (s, th) => { const o = { t: s.t, u: s.u, s: s.s, d: new Date(s.d).toISOString(), n: s.out.length, also: [...new Set(s.out.filter((a) => a.s !== s.s).map((a) => a.s))].slice(0, 6) }; if (s.who && s.who.length) o.who = s.who; if (th) o.th = th; return o; };

function build(items) {
  const now = Date.now(), cut = now - CFG.days * 864e5, by = {};
  THEMES.forEach((t) => (by[t.id] = []));
  for (const x of items) {
    if (x.d < cut) continue;
    const hit = THEMES.filter((t) => t.id !== "other" && t.kwR.test(x.t) && (!t.needR || t.needR.test(x.t)));
    if (hit.length) hit.slice(0, 2).forEach((t) => by[t.id].push(x));
    else if (MARKET.test(x.t) && (x.o === "BUSINESS" || x.o === "other" || /^(corporate|world|fx|energy|rates|macro)$/.test(x.o))) by.other.push(x);
  }
  const themes = [], all = [], full = {}, every = new Map();
  for (const t of THEMES) {
    let st = cluster(by[t.id]);
    if (t.people) st.forEach((s) => (s.who = PEOPLE.filter(([, r]) => r.test(s.t)).map(([n]) => n).slice(0, 2)));
    if (t.people) st = st.filter((s) => s.who.length);
    st.sort(rank);
    const day = st.filter((s) => now - s.d < 864e5).length;
    themes.push({ id: t.id, name: t.name, short: t.short, why: t.why, ref: t.ref, sectors: t.sectors, total: st.length, day, stories: st.slice(0, 30).map((s) => strip(s)) });
    st.slice(0, 30).forEach((s) => all.push({ s, th: t.id }));
    full[t.id] = st.map((s) => strip(s));
    st.forEach((s) => { if (!every.has(s.u)) every.set(s.u, strip(s, t.id)); });
  }
  // every story of the last 7 days, newest first (served on request, not in the main feed)
  full.all = [...every.values()].sort((a, b) => b.d.localeCompare(a.d)).slice(0, 1200);
  // top stories: last 48 hours, most outlets first; a story found under two themes counts once
  const top = [], seen = [];
  for (const { s, th } of all.filter((x) => now - x.s.d < 2 * 864e5).sort((a, b) => rank(a.s, b.s))) {
    if (seen.some((tk) => same(s.tk, tk))) continue;
    seen.push(s.tk); top.push(strip(s, th)); if (top.length >= 15) break;
  }
  const latest = [], seen2 = [];
  for (const { s, th } of all.sort((a, b) => b.s.d - a.s.d)) {
    if (seen2.some((tk) => same(s.tk, tk))) continue;
    seen2.push(s.tk); latest.push(strip(s, th)); if (latest.length >= 30) break;
  }
  const people = {};
  const pt = themes.find((t) => t.id === "people");
  if (pt) for (const s of pt.stories) for (const w of s.who || []) (people[w] = people[w] || []).push(s);
  return { updated: new Date(now).toISOString(), live: true, market_open: marketOpen(), refresh_min: marketOpen() ? 5 : 60, days: CFG.days, pool: items.length, stories_total: every.size, full,
    top, latest, themes, people: Object.entries(people).map(([name, st]) => ({ name, n: st.length })).sort((a, b) => b.n - a.n), owners: CFG.owners,
    note: "Collected from Google News (searches plus its Business, World, India and Technology sections), limited to a fixed list of established outlets, grouped when several outlets carry the same story, and ranked by how many outlets carry it and how recent it is. Headlines are kept for 7 days and topped up on every refresh. Posts on X or Truth Social appear when these outlets report them. Headlines are not summarised or checked." };
}

async function refresh(oldPool, k) {
  const tasks = CFG.sections.map(([sec, gl]) => async () => parse(await get(surl(sec, gl)), sec))
    .concat(batch(oldPool && oldPool.length ? k : "all").map(([id, q]) => async () => parse(await get(qurl(q, CFG.days)), id)));
  const res = await pool(tasks, 14);
  const fresh = res.flat(), ok = res.filter((r) => r && r.length).length;
  const cut = Date.now() - CFG.days * 864e5, map = new Map();
  for (const x of (oldPool || []).concat(fresh)) {
    if (x.d < cut) continue;
    const key = x.t.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 80) + "|" + x.s;
    const prev = map.get(key); if (!prev || prev.o === "other") map.set(key, x);
  }
  const items = [...map.values()].sort((a, b) => b.d - a.d).slice(0, 3500);
  return { items, fetched: tasks.length, answered: ok, added: fresh.length };
}
module.exports = { refresh, build, marketOpen };
