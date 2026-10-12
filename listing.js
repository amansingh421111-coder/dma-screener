/* Which exchange lists a share, its full name, and the search that finds it on either exchange.
   listings.json (written by the screener): n = NSE shares {symbol: [name, BSE scrip code or ""]}, b = BSE-only {symbol: [name, code]}.
   A share with a BSE code in n trades on both exchanges: company figures are the same, prices are each exchange's own. */
let LISTING = null, BSEC = null;   // BSEC: official BSE closing prices (bse_close.json)
async function loadListing() {
  if (LISTING !== null) return LISTING; LISTING = { n: {}, b: {} };
  try { const [r, r2] = await Promise.all([fetch("/listings.json", { cache: "no-cache" }), fetch("/bse_close.json", { cache: "no-cache" })]); if (r.ok) LISTING = await r.json(); if (r2.ok) BSEC = await r2.json(); } catch (e) {}
  render(); return LISTING;
}
function lsInfo(sym) {
  if (LISTING === null) loadListing();
  const L = LISTING || {}, n = L.n && L.n[sym], b = L.b && L.b[sym];
  return { name: (n || b || [])[0] || null, nse: !!n, bse: !!(b || (n && n[1])), code: (n && n[1]) || (b && b[1]) || null };
}
const lsBoth = (sym) => { const i = lsInfo(sym); return i.nse && i.bse; };
/* the exchange to open when none is given: NSE when listed there */
const lsEx = (sym, ex) => { const i = lsInfo(sym); return ex === "BSE" && i.bse ? "BSE" : ex === "NSE" && i.nse ? "NSE" : i.nse ? "NSE" : i.bse ? "BSE" : ex || "NSE"; };
const lsName = (sym) => lsInfo(sym).name;
/* Yahoo tickers to try, best first: a BSE share also on NSE is usually SYMBOL.BO, a BSE-only share its scrip code */
function lsTickers(sym, ex) {
  if (ex !== "BSE") return [sym + ".NS"];
  const i = lsInfo(sym); return [...new Set(i.nse && i.code ? [sym + ".BO", i.code + ".BO"] : i.code ? [i.code + ".BO", sym + ".BO"] : [sym + ".BO"])];
}
const lsTicker = (sym, ex) => lsTickers(sym, ex)[0];
/* daily prices for a share on one exchange, trying each ticker; cached in EQ.charts under the first ticker */
const LSBUSY = {};
function lsChartLoad(sym, ex) {
  const T = lsTickers(sym, ex), key = T[0];
  if (typeof EQ === "undefined") return Promise.resolve(null);
  if (EQ.charts[key]) return Promise.resolve(EQ.charts[key]);
  if (LSBUSY[key]) return LSBUSY[key];   // already on its way: share the same request
  return (LSBUSY[key] = (async () => {
    let out = null;   // the ticker with the most history wins; Yahoo often has only today's BSE price for shares also on NSE
    for (const t of T) {
      try { const r = await fetch("/api/dma?a=chart&t=" + encodeURIComponent(t)), j = await r.json();
        if (r.ok && j.c && j.c.length && (!out || !out.c || j.c.length > out.c.length)) out = j; else out = out || { error: j.error || "No price history." };
        if (out.c && out.c.length >= 60) break; }
      catch (e) { out = out || { error: "Could not reach the price source." }; }
    }
    EQ.charts[key] = out; delete LSBUSY[key];
    render(); if (typeof entDraw === "function") entDraw(); if (typeof renderModes === "function" && document.getElementById("pform") && !document.getElementById("pform").hidden) renderModes();
    return out;
  })());
}

/* ---- search: symbols and company names on both exchanges ---- */
const LSK = {};
function lsSearch(q, limit = 8) {
  q = String(q || "").trim(); if (!q || LISTING === null) { if (LISTING === null) loadListing(); return []; }
  const up = q.toUpperCase(), k = typeof nameKey === "function" ? nameKey(q) : q.toLowerCase(), out = [];
  const add = (s, ex, n, sc) => { if (!out.some((x) => x.s === s && x.ex === ex)) out.push({ s, ex, n, sc }); };
  const each = (fn) => { for (const s in LISTING.n || {}) fn(s, LISTING.n[s], true); for (const s in LISTING.b || {}) fn(s, LISTING.b[s], false); };
  each((s, v, isN) => {
    let sc = s === up ? 1 : s.startsWith(up) ? 0.9 - Math.min(0.2, (s.length - up.length) * 0.02) : 0;
    if (!sc && k && v[0]) { const nk = LSK[v[0]] || (LSK[v[0]] = nameKey(v[0])); sc = nk === k ? 0.95 : nk.startsWith(k) ? 0.85 : typeof symScore === "function" && k.length >= 3 ? symScore(k, nk) * 0.8 : 0; }
    if (sc >= 0.45) { if (isN) { add(s, "NSE", v[0], sc); if (v[1]) add(s, "BSE", v[0], sc - 0.001); } else add(s, "BSE", v[0], sc); }
  });
  return out.sort((a, b) => b.sc - a.sc || a.s.localeCompare(b.s) || (a.ex === "NSE" ? -1 : 1)).slice(0, limit * 2).slice(0, limit);
}
/* a search box with suggestions; pick(sym, ex) is called with the chosen share */
const LSBOX = {};
function lsBox(id, pickFn, ph, val) {
  LSBOX[id] = pickFn;
  return `<div class="lsb" id="${id}-w"><input id="${id}" type="search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="${esc(ph || "Symbol or company name")}" value="${esc(val || "")}"
    oninput="lsSuggest('${id}')" onkeydown="lsKey(event,'${id}')" onfocus="lsSuggest('${id}')" onblur="setTimeout(()=>lsHide('${id}'),180)" aria-label="${esc(ph || "Find a share")}" role="combobox" aria-autocomplete="list" aria-controls="${id}-l"><div class="lsl" id="${id}-l" role="listbox" hidden></div></div>`;
}
function lsSuggest(id) {
  const el = document.getElementById(id), L = document.getElementById(id + "-l"); if (!el || !L) return;
  const R = lsSearch(el.value, 8); L.dataset.i = "0";
  if (!R.length) { L.hidden = !el.value.trim(); L.innerHTML = el.value.trim() ? `<div class="lse">${LISTING && Object.keys(LISTING.n || {}).length ? "No share matches “" + esc(el.value.trim()) + "”" : "Loading the share list…"}</div>` : ""; return; }
  L.innerHTML = R.map((r, i) => `<button type="button" role="option" class="lso${i === 0 ? " on" : ""}" onmousedown="event.preventDefault()" onclick="lsChoose('${id}','${esc(r.s)}','${r.ex}')"><b>${esc(r.s)}</b><span class="tag ex${r.ex === "BSE" ? " bse" : ""}">${r.ex}</span><small>${esc(r.n || "")}${lsBoth(r.s) ? " · on NSE and BSE" : ""}</small></button>`).join("");
  L.hidden = false;
}
function lsHide(id) { const L = document.getElementById(id + "-l"); if (L) L.hidden = true; }
function lsChoose(id, s, ex) { const el = document.getElementById(id); if (el) el.value = s; lsHide(id); if (LSBOX[id]) LSBOX[id](s, ex); }
function lsKey(e, id) {
  const L = document.getElementById(id + "-l"), opts = L ? [...L.querySelectorAll(".lso")] : [];
  let i = +(L && L.dataset.i || 0);
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (!opts.length) return; i = (i + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length; L.dataset.i = i; opts.forEach((o, j) => o.classList.toggle("on", j === i)); return; }
  if (e.key === "Enter") {
    e.preventDefault(); const v = e.target.value.trim(); if (!v) return;
    if (opts[i] && !(L && L.hidden)) { opts[i].click(); return; }
    if (LSFORM[id]) { lsHide(id); return; }   // a form field: keep what was typed
    const R = lsSearch(v, 1); if (R[0]) lsChoose(id, R[0].s, R[0].ex); else if (LSBOX[id]) LSBOX[id](v.toUpperCase(), "NSE");
  }
  if (e.key === "Escape") lsHide(id);
}

/* ---- the other exchange's price, for shares on both ---- */
/* daily history good enough for readings: the exchange's own, or NSE's for a share on both when Yahoo lacks its BSE history */
function lsHist(sym, ex) {
  if (typeof EQ === "undefined") return null;
  const C = EQ.charts[lsTicker(sym, ex)]; if (C && C.c && C.c.length >= 60) return { C, from: ex };
  if (ex === "BSE" && lsBoth(sym)) { const N = EQ.charts[sym + ".NS"]; if (N && N.c && N.c.length >= 60) return { C: N, from: "NSE" }; if (!N) lsChartLoad(sym, "NSE"); }
  return C && C.c && C.c.length ? { C, from: ex, thin: true } : null;
}
function lsPx(sym, ex) {   // latest price and day change on one exchange (shared chart cache)
  if (typeof EQ === "undefined") return null; const t = lsTicker(sym, ex);
  const C = EQ.charts[t]; if (C && C.c && C.c.length) { const n = C.c.length, prev = n > 1 ? C.c[n - 2] : BSEC && BSEC.c && ex === "BSE" && BSEC.date < C.dates[n - 1] ? BSEC.c[sym] : null; return { p: C.c[n - 1], d1: prev ? (C.c[n - 1] / prev - 1) * 100 : null, date: C.dates[n - 1] }; }
  if (C && ex === "BSE" && BSEC && BSEC.c && BSEC.c[sym]) return { p: BSEC.c[sym], d1: null, date: BSEC.date, official: true };
  if (!C) lsChartLoad(sym, ex);
  return null;
}
/* NSE | BSE switch with each exchange's price; go(ex) is a JS expression template with {ex} */
function lsSwitch(sym, ex, onJs) {
  if (!lsBoth(sym)) return `<span class="tag ex${ex === "BSE" ? " bse" : ""}" title="${ex === "BSE" ? "Listed on BSE only" : lsInfo(sym).nse ? "Listed on NSE" : ""}">${ex}${lsInfo(sym).nse || lsInfo(sym).bse ? (ex === "BSE" ? " only" : "") : ""}</span>`;
  const b = (x) => { const v = lsPx(sym, x); return `<button type="button" aria-pressed="${ex === x}" onclick="event.stopPropagation();${onJs.replace(/\{ex\}/g, x)}" title="Prices from ${x}">${x}${v ? ` <span>₹${v.p.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>` : ""}</button>`; };
  return `<span class="seg2 lsw" role="group" aria-label="Exchange">${b("NSE")}${b("BSE")}</span>`;
}

/* suggestions on an existing form field (symbol + exchange select): picking fills both and names the company below */
const LSFORM = {};
function lsAttach(id, exId, cb) {
  const el = document.getElementById(id); if (!el || el.dataset.ls) return; el.dataset.ls = "1"; el.removeAttribute("list");
  const w = document.createElement("div"); w.className = "lsb"; el.parentNode.insertBefore(w, el); w.appendChild(el);
  const l = document.createElement("div"); l.className = "lsl"; l.id = id + "-l"; l.hidden = true; l.setAttribute("role", "listbox"); w.appendChild(l);
  const nm = document.createElement("div"); nm.className = "lsn"; nm.id = id + "-n"; w.after(nm);
  LSFORM[id] = exId || true;
  LSBOX[id] = (s, ex) => { if (exId && document.getElementById(exId)) document.getElementById(exId).value = ex; lsNote(id); if (cb) cb(s, ex); el.dispatchEvent(new Event("input")); lsHide(id); };
  el.addEventListener("input", () => { if (document.activeElement === el) lsSuggest(id); lsNote(id); });
  el.addEventListener("keydown", (e) => lsKey(e, id)); el.addEventListener("focus", () => { if (el.value) lsSuggest(id); });
  el.addEventListener("blur", () => setTimeout(() => lsHide(id), 180));
  if (exId && document.getElementById(exId)) document.getElementById(exId).addEventListener("change", () => lsNote(id));
}
/* what the typed symbol is: the company, and whether it is listed on the chosen exchange */
function lsNote(id) {
  const el = document.getElementById(id), n = document.getElementById(id + "-n"); if (!el || !n) return;
  const s = el.value.trim().toUpperCase(), exId = LSFORM[id], ex = typeof exId === "string" && document.getElementById(exId) ? document.getElementById(exId).value : null;
  if (!s || LISTING === null || !Object.keys(LISTING.n || {}).length) { n.textContent = ""; n.className = "lsn"; return; }
  const i = lsInfo(s);
  if (!i.nse && !i.bse) { n.textContent = "Not found on NSE or BSE: check the symbol, or pick one from the list."; n.className = "lsn bad"; return; }
  const on = i.nse && i.bse ? "on NSE and BSE" : i.nse ? "on NSE" : "on BSE only";
  const bad = ex && ((ex === "BSE" && !i.bse) || (ex === "NSE" && !i.nse));
  n.textContent = `${i.name || s} · ${on}` + (bad ? ` · not listed on ${ex}: choose ${ex === "BSE" ? "NSE" : "BSE"}` : ""); n.className = "lsn" + (bad ? " bad" : "");
}

/* exchange label: NSE and BSE look different everywhere */
const exTag = (ex) => `<span class="tag ex${ex === "BSE" ? " bse" : ""}" title="${ex === "BSE" ? "Prices from BSE (Bombay Stock Exchange)" : "Prices from NSE (National Stock Exchange)"}">${ex === "BSE" ? "BSE" : "NSE"}</span>`;
