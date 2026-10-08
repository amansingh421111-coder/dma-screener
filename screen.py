"""NSE + BSE auto screener: MA cross / approach alerts, market cap, position alerts.
Alerts only. This program never places orders."""
import argparse, concurrent.futures as cf, datetime as dt, io, json, logging, os, smtplib, sys, time
from email.mime.text import MIMEText
from pathlib import Path
import numpy as np, pandas as pd, requests, yaml

ROOT = Path(__file__).resolve().parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
log = logging.getLogger("dma")
UA = {"User-Agent": "Mozilla/5.0"}
NSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Atea=&Scripcode=&segment=Equity&status=Active"
DEFAULTS = dict(ma_type="SMA", ma_period=44, near_pct=1.5, min_price=50, min_avg_volume=100000,
                max_near_alerts=25, include_bse=True, bse_min_avg_volume=25000,
                bse_groups=["A", "B", "T", "X", "XT"], mcap_large_cr=100000, mcap_mid_cr=30000, mcap_small_cr=5000)

def load_cfg():
    c = dict(DEFAULTS); c.update(yaml.safe_load((ROOT / "config.yaml").read_text()) or {}); return c

def pick(x, *names):
    low = {k.lower(): v for k, v in x.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""): return str(v).strip()
    return ""

def nse_universe():
    cache = ROOT / "universe_nse.csv"
    try:
        r = requests.get(NSE_URL, headers=UA, timeout=30); r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text)); df.columns = [c.strip() for c in df.columns]
        df = df[df["SERIES"].str.strip() == "EQ"]
        out = pd.DataFrame({"symbol": df["SYMBOL"].str.strip(), "name": df["NAME OF COMPANY"].str.strip(),
                            "isin": df["ISIN NUMBER"].str.strip()})
        out.to_csv(cache, index=False)
    except Exception as e:
        log.warning("NSE list failed (%s); using cache", e)
        src = cache if cache.exists() else ROOT / "universe.csv"
        out = pd.read_csv(src).fillna("")
        out = out.rename(columns={"SYMBOL": "symbol"})
        for k in ("name", "isin"):
            if k not in out: out[k] = ""
    return [dict(symbol=s, name=n, isin=i, exchange="NSE", yahoo=s + ".NS")
            for s, n, i in zip(out["symbol"], out["name"], out["isin"])]

BSE_ERR = []
BSE_BHAV = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"

def _bse_from_api(skip_isins, groups):
    s = requests.Session(); h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                 "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com", "Accept": "application/json, text/plain, */*"}
    try: s.get("https://www.bseindia.com/", headers=h, timeout=20)
    except Exception: pass
    r = s.get(BSE_URL, headers=h, timeout=45); r.raise_for_status()
    rec = []
    for x in r.json():
        code, isin, grp = pick(x, "SCRIP_CD"), pick(x, "ISIN_NUMBER", "ISIN"), pick(x, "GROUP", "Scrip_Grp")
        if not code.isdigit() or (isin and isin in skip_isins) or (groups and grp and grp not in groups): continue
        rec.append(dict(symbol=pick(x, "scrip_id") or code, name=pick(x, "Scrip_Name", "Issuer_Name"), isin=isin, code=code))
    return rec

def _bse_from_bhavcopy(skip_isins, groups):
    """Fallback: list of BSE scrips that traded on a recent day (from the exchange's daily bhavcopy file)."""
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Referer": "https://www.bseindia.com/"}
    day, last = dt.date.today(), None
    for _ in range(8):
        if day.weekday() < 5:
            try:
                r = requests.get(BSE_BHAV.format(d=day), headers=h, timeout=45); r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text), dtype=str).fillna(""); df.columns = [c.strip() for c in df.columns]
                rec = []
                for x in df.to_dict("records"):
                    code, isin, grp = str(x.get("FinInstrmId", "")).strip(), str(x.get("ISIN", "")).strip(), str(x.get("SctySrs", "")).strip()
                    if not code.isdigit() or (isin and isin in skip_isins) or (groups and grp and grp not in groups): continue
                    rec.append(dict(symbol=str(x.get("TckrSymb", "")).strip() or code, name=str(x.get("FinInstrmNm", "")).strip(), isin=isin, code=code))
                if rec: return rec
            except Exception as e:
                last = e
        day -= dt.timedelta(days=1)
    raise last or ValueError("no bhavcopy found")

def bse_universe(skip_isins, groups):
    """BSE-only stocks (those not already listed on NSE, matched by ISIN). Yahoo uses scrip code + .BO"""
    cache = ROOT / "universe_bse.csv"; rec = None
    for name, fn in (("BSE list API", _bse_from_api), ("BSE bhavcopy", _bse_from_bhavcopy)):
        try:
            rec = fn(skip_isins, groups)
            if rec: pd.DataFrame(rec).to_csv(cache, index=False); BSE_ERR.clear(); break
            raise ValueError("empty list")
        except Exception as e:
            log.warning("%s failed (%s)", name, e); BSE_ERR.append(f"{name}: {str(e)[:120]}"); rec = None
    if rec is None:
        if not cache.exists(): return []
        log.warning("Using cached BSE list")
        rec = pd.read_csv(cache, dtype=str).fillna("").to_dict("records")
    return [dict(symbol=r["symbol"], name=r["name"], isin=r["isin"], exchange="BSE", yahoo=str(r["code"]) + ".BO") for r in rec]

PRE = {}
BH_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
NSE_BHAV = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"

def _latest_bhav(url, headers, parse):
    day, last = dt.date.today(), None
    for _ in range(8):
        if day.weekday() < 5:
            try:
                r = requests.get(url.format(d=day), headers=headers, timeout=40); r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text), dtype=str).fillna(""); df.columns = [c.strip() for c in df.columns]
                out = parse(df)
                if len(out) > 300: return out, day
            except Exception as e: last = e
        day -= dt.timedelta(days=1)
    raise last or ValueError("no bhavcopy")

def _num(x):
    try: return float(str(x).replace(",", "").strip())
    except Exception: return None

def prefilter(items, c):
    """Drop stocks that cannot pass the price / volume filters, using the exchanges' official end-of-day files.
    Fewer tickers to download = much faster runs. Any failure leaves the list untouched."""
    def nse_parse(df):
        df = df[df["SERIES"].str.strip() == "EQ"]
        return {r["SYMBOL"].strip(): (_num(r["CLOSE_PRICE"]), _num(r["TTL_TRD_QNTY"])) for r in df.to_dict("records")}
    def bse_parse(df):
        return {str(r["FinInstrmId"]).strip(): (_num(r["ClsPric"]), _num(r["TtlTradgVol"])) for r in df.to_dict("records")}
    keep, info = [], {}
    maps = {}
    for ex, url, hd, fn in (("NSE", NSE_BHAV, BH_H, nse_parse),
                            ("BSE", BSE_BHAV, dict(BH_H, Referer="https://www.bseindia.com/"), bse_parse)):
        try: maps[ex], day = _latest_bhav(url, hd, fn); info[ex] = str(day)
        except Exception as e: log.warning("%s prefilter unavailable (%s)", ex, str(e)[:100]); info[ex] = None
    for u in items:
        m = maps.get(u["exchange"])
        if m is None: keep.append(u); continue
        key = u["symbol"] if u["exchange"] == "NSE" else u["yahoo"].split(".")[0]
        v = m.get(key)
        if v is None: continue                      # did not trade on the latest day
        px, vol = v
        mv = c["bse_min_avg_volume"] if u["exchange"] == "BSE" else c["min_avg_volume"]
        if px is not None and px < c["min_price"] * 0.97: continue
        if vol is not None and vol < mv * 0.15: continue
        keep.append(u)
    PRE.update(info=info, before=len(items), after=len(keep))
    log.info("prefilter %s: %d -> %d tickers", info, len(items), len(keep))
    return keep

def moving_avg(close, kind, n):
    return close.rolling(n).mean() if kind.upper() == "SMA" else close.ewm(span=n, adjust=False).mean()

def candle_info(df):
    if not {"Open", "High", "Low"} <= set(df.columns): return None, 0.5
    r = df.iloc[-1]; vals = [r[x] for x in ("Open", "High", "Low", "Close")]
    if any(pd.isna(v) for v in vals): return None, 0.5
    o, h, l, c = map(float, vals); rng = h - l
    if rng <= 0: return "doji", 0.5
    body, pos = abs(c - o), (c - l) / rng
    lw, uw = min(o, c) - l, h - max(o, c)
    if lw >= 2 * body and pos >= 0.6 and body > 0: name = "hammer"
    elif uw >= 2 * body and pos <= 0.4 and body > 0: name = "shooting_star"
    elif body / rng < 0.15: name = "doji"
    else: name = "bullish" if c > o else "bearish"
    return name, pos

def conviction(direction, name, pos, vol_x):
    if name is None: return 0
    pts = 0
    if direction > 0: pts += name in ("bullish", "hammer"); pts += pos >= 0.67
    else: pts += name in ("bearish", "shooting_star"); pts += pos <= 0.33
    return int(pts + (vol_x >= 1.5))

def rsi14(close):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    return round(float(100 - 100 / (1 + up / dn)), 1) if dn > 0 else 100.0

def extras(close, m, c0, c1):
    m200 = close.rolling(200).mean().iloc[-1]
    hi, lo = float(close.tail(252).max()), float(close.tail(252).min())
    cur = bool(close.iloc[-1] > m.iloc[-1])
    idx = np.where(m.notna().values & ((close > m).values != cur))[0]
    return dict(chg=round(float((c0 / c1 - 1) * 100), 2), rsi=rsi14(close),
                above200=bool(c0 > m200) if pd.notna(m200) else None,
                hi52=round(hi, 2), lo52=round(lo, 2), from_hi=round(float((c0 / hi - 1) * 100), 1),
                since=int(len(close) - 1 - idx[-1]) if idx.size else None,
                spark=[round(float(x), 2) for x in close.tail(60)],
                sparkma=[None if pd.isna(x) else round(float(x), 2) for x in m.tail(60)])

WHY = {}; CUR = ["NSE"]
def _no(r):
    k = f"{CUR[0]}:{r}"; WHY[k] = WHY.get(k, 0) + 1

def classify(sym, df, c):
    """Return a signal dict (buy/sell/near) or None. Pure function, easy to test."""
    df = df.dropna(subset=["Close"])
    if len(df) < c["ma_period"] + 2: _no("short_history"); return None
    close = df["Close"]; m = moving_avg(close, c["ma_type"], c["ma_period"])
    c0, c1, m0, m1 = close.iloc[-1], close.iloc[-2], m.iloc[-1], m.iloc[-2]
    if c0 < c["min_price"]: _no("low_price"); return None
    if df["Volume"].tail(20).mean() < c["min_avg_volume"]: _no("low_volume"); return None
    pct = (c0 / m0 - 1) * 100
    if c1 <= m1 and c0 > m0: kind = "buy"
    elif c1 >= m1 and c0 < m0: kind = "sell"
    elif abs(pct) <= c["near_pct"]: kind = "near"
    else: _no("not_near_average"); return None
    name, pos = candle_info(df)
    prev_vol = df["Volume"].iloc[-21:-1].mean()
    vol_x = float(df["Volume"].iloc[-1] / prev_vol) if prev_vol > 0 else 0.0
    direction = 1 if kind == "buy" else -1 if kind == "sell" else (1 if pct < 0 else -1)
    return dict(symbol=sym, price=round(float(c0), 2), ma=round(float(m0), 2), pct=round(float(pct), 2),
                volume=int(df["Volume"].iloc[-1]), type=kind, candle=name,
                score=conviction(direction, name, pos, vol_x), vol_x=round(vol_x, 1), **extras(close, m, c0, c1))

def fetch(tickers, batch=100, period="1y", workers=3, budget=780):
    """Download daily OHLCV for Yahoo tickers in parallel batches. Returns {ticker: DataFrame}."""
    import yfinance as yf
    out = {}; t0 = time.time()
    chunks = [tickers[i:i + batch] for i in range(0, len(tickers), batch)]
    def one(chunk):
        if time.time() - t0 > budget: return chunk, None
        for attempt in range(2):
            try:
                d = yf.download(chunk, period=period, interval="1d", group_by="ticker", threads=True,
                                progress=False, auto_adjust=False)
                if d is not None and not d.empty: return chunk, d
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                log.warning("batch retry %d: %s", attempt, str(e)[:100]); time.sleep(4 * (attempt + 1))
        return chunk, None
    skipped = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for chunk, d in ex.map(one, chunks):
            if d is None: skipped += 1; continue
            for t in chunk:
                try: out[t] = d[t][["Open", "High", "Low", "Close", "Volume"]]
                except KeyError: pass
    if skipped: log.warning("%d of %d batches returned nothing (rate limit or time budget)", skipped, len(chunks))
    return out

# ---- market cap (cached; only fetched for stocks that show up in signals) ----
def get_mcaps(items, max_age=7, cap=400):
    f = ROOT / "mcap.json"
    cache = json.loads(f.read_text()) if f.exists() else {}
    today = dt.date.today()
    def stale(k):
        return k not in cache or (today - dt.date.fromisoformat(cache[k]["d"])).days >= max_age
    need = [it for it in items if stale(it["key"])][:cap]
    def one(it):
        try:
            import yfinance as yf
            mc = yf.Ticker(it["yahoo"]).fast_info.market_cap
            return it["key"], (round(float(mc) / 1e7, 1) if mc and mc > 0 else None)
        except Exception: return it["key"], None
    if need:
        with cf.ThreadPoolExecutor(8) as ex:
            for k, cr in ex.map(one, need):
                if cr: cache[k] = {"cr": cr, "d": today.isoformat()}
        f.write_text(json.dumps(cache))
    return {k: v["cr"] for k, v in cache.items()}

def mcap_cat(cr, c):
    if cr is None: return None
    return "Large" if cr >= c["mcap_large_cr"] else "Mid" if cr >= c["mcap_mid_cr"] else "Small" if cr >= c["mcap_small_cr"] else "Micro"

# ---- positions (positions.json exported from the website) ----
def is_open(p): return not (p.get("sellDate") and (p.get("sellPrice") or 0) > 0)

def load_positions():
    f = ROOT / "positions.json"
    if not f.exists(): return []
    try:
        d = json.loads(f.read_text()); d = d["positions"] if isinstance(d, dict) else d
        return [p for p in d if p.get("symbol") and is_open(p)]
    except Exception as e:
        log.warning("positions.json unreadable: %s", e); return []

def redis(cmd):
    """Upstash Redis over REST. Returns None when not configured."""
    url, tok = os.getenv("UPSTASH_URL"), os.getenv("UPSTASH_TOKEN")
    if not (url and tok): return None
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"}, json=cmd, timeout=20)
    r.raise_for_status(); return r.json().get("result")

CLOUD = {"redis": False, "users": 0, "connected": 0, "error": None, "token_set": bool(os.getenv("TELEGRAM_TOKEN")), "send": None}

def cloud_users():
    """Everyone who connected Telegram on the website: [{uid, chat, positions}]."""
    CLOUD["redis"] = bool(os.getenv("UPSTASH_URL") and os.getenv("UPSTASH_TOKEN"))
    try:
        uids = redis(["SMEMBERS", "users"]) or []
        out = []
        for uid in uids:
            chat, raw = redis(["GET", f"chat:{uid}"]), redis(["GET", f"pos:{uid}"])
            if not chat or not raw: continue
            d = json.loads(raw); d = d["positions"] if isinstance(d, dict) else d
            out.append(dict(uid=uid, chat=chat, positions=[p for p in d if p.get("symbol") and is_open(p)]))
        CLOUD["users"] = len(uids); CLOUD["connected"] = len(out)
        return out
    except Exception as e:
        CLOUD["error"] = str(e)[:150]
        log.warning("Cloud positions unavailable: %s", e); return []

def _tokens():
    t = []
    if os.getenv("TELEGRAM_TOKEN"): t.append(os.getenv("TELEGRAM_TOKEN").strip())
    try:
        r = redis(["GET", "cfg:bot"])          # the website saves its own bot token here when you press Connect
        if r and r not in t: t.append(r)
    except Exception: pass
    return t

def send_telegram(chat, text):
    toks = _tokens()
    if not toks:
        log.warning("no Telegram token available; cannot message %s", chat)
        CLOUD["send"] = {"ok": False, "status": None, "error": "No bot token: set the TELEGRAM_TOKEN secret, or press Connect Telegram on the site once"}; return False
    for tok in toks:
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                              data={"chat_id": chat, "text": text, "disable_web_page_preview": True})
            err = None
            if not r.ok:
                try: err = r.json().get("description")
                except Exception: err = r.text[:120]
            CLOUD["send"] = {"ok": r.ok, "status": r.status_code, "error": err}
            log.info("telegram user alert %s %s", r.status_code, err or "")
            if r.ok or r.status_code not in (401, 404): return r.ok
        except Exception as e:
            CLOUD["send"] = {"ok": False, "status": None, "error": str(e)[:120]}
    return False

def pos_key(p): return f"{p.get('exchange', 'NSE')}:{p['symbol']}"
def pos_yahoo(p): return p["symbol"] + (".BO" if p.get("exchange") == "BSE" else ".NS")

def position_quotes(pos, c):
    if not pos: return {}
    data = fetch([pos_yahoo(p) for p in pos]); q = {}
    for p in pos:
        df = data.get(pos_yahoo(p))
        if df is None: continue
        close = df["Close"].dropna()
        if len(close) < 2: continue
        m = moving_avg(close, c["ma_type"], c["ma_period"]).iloc[-1]
        px = float(close.iloc[-1])
        q[pos_key(p)] = dict(price=round(px, 2), ma=None if pd.isna(m) else round(float(m), 2),
                             pct=None if pd.isna(m) else round((px / float(m) - 1) * 100, 2),
                             chg=round((px / float(close.iloc[-2]) - 1) * 100, 2))
    return q

def position_events(pos, quotes, c):
    ev = []
    seen = set()
    for p in pos:
        if not is_open(p) or pos_key(p) in seen: continue
        seen.add(pos_key(p))
        q = quotes.get(pos_key(p))
        if not q: continue
        px, k, s = q["price"], pos_key(p), p["symbol"]
        if p.get("alertSl") and p.get("sl") and px <= p["sl"]:
            ev.append((k + ":sl", f"🛑 STOP LOSS hit: {s} ₹{px} (stop ₹{p['sl']})"))
        if p.get("alertTg") and p.get("target") and px >= p["target"]:
            ev.append((k + ":tg", f"🎯 TARGET reached: {s} ₹{px} (target ₹{p['target']})"))
        if p.get("alertMa") and q["pct"] is not None:
            if q["pct"] < 0: ev.append((k + ":below", f"⚠️ {s} closed below its {c['ma_period']}-DMA ({q['pct']:+}%)"))
            elif q["pct"] <= c["near_pct"]: ev.append((k + ":near", f"👀 {s} is approaching its {c['ma_period']}-DMA from above ({q['pct']:+}%)"))
    return ev

# ---- alerts ----
def fmt_cr(x): return "" if not x else (f"₹{x / 1e5:.2f}L Cr" if x >= 1e5 else f"₹{x:,.0f} Cr")

def format_msg(sigs, title, cap):
    lines = [title]
    for kind, label in (("buy", "🟢 BUY signals"), ("sell", "🔴 SELL signals"), ("near", "🟡 Approaching")):
        g = sorted([s for s in sigs if s["type"] == kind], key=lambda s: (-s.get("score", 0), abs(s["pct"])))
        if not g: continue
        lines.append(f"\n{label} ({len(g)})")
        for s in g[:cap]:
            lines.append(f"{s['symbol']} ({s.get('exchange', 'NSE')})  ₹{s['price']}  MA ₹{s['ma']}  {s['pct']:+}%  "
                         f"{s.get('candle') or ''} {'★' * s.get('score', 0)}{'☆' * (3 - s.get('score', 0))}  {fmt_cr(s.get('mcap'))}")
    lines.append("\nResearch alert only, not financial advice.")
    return "\n".join(lines)[:4000]

def notify(text):
    sent = False
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                          data={"chat_id": chat, "text": text, "disable_web_page_preview": True})
        log.info("telegram %s", r.status_code); sent = r.ok
    user, pw, to = os.getenv("EMAIL_USER"), os.getenv("EMAIL_APP_PASSWORD"), os.getenv("EMAIL_TO")
    if user and pw and to:
        msg = MIMEText(text); msg["Subject"] = text.split("\n")[0]; msg["From"] = user; msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pw); s.send_message(msg)
        sent = True
    if not sent: log.warning("No alert channel configured (set secrets)")
    return sent

def in_market_hours(now):
    return now.weekday() < 5 and dt.time(9, 15) <= now.time() <= dt.time(15, 45)

def read_json(name, default):
    try: return json.loads((ROOT / name).read_text())
    except Exception: return default

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore market-hours gate, scan BSE too")
    ap.add_argument("--summary", action="store_true", help="send full end-of-day summary")
    ap.add_argument("--test-alert", action="store_true", help="send a sample alert and exit")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    c = load_cfg(); now = dt.datetime.now(IST)
    if a.test_alert:
        demo = [dict(symbol="RELIANCE", exchange="NSE", price=2910.5, ma=2875.2, pct=1.2, volume=1, type="buy", mcap=1960000)]
        sys.exit(0 if notify(format_msg(demo, "🧪 TEST alert", 5)) else 1)
    if not (a.force or a.summary or in_market_hours(now)):
        log.info("Outside market hours, skipping"); return
    old = read_json("signals.json", {})
    nse = nse_universe(); items = list(nse)
    scan_bse = c["include_bse"] and (a.force or a.summary or now.minute < 15 or not old.get("bse_updated"))
    if scan_bse:
        items += bse_universe({u["isin"] for u in nse if u["isin"]}, c["bse_groups"])
    items = prefilter(items, c)
    # skip tickers that Yahoo has had no data for on 2+ consecutive runs (refreshed weekly) -> faster runs
    nd = read_json("nodata.json", {}); today = now.strftime("%Y-%m-%d")
    if nd.get("week") != now.strftime("%G-%V"): nd = {"week": now.strftime("%G-%V"), "miss": {}}
    miss = nd["miss"]
    todo = [u for u in items if miss.get(u["yahoo"], 0) < 2]
    log.info("fetching %d of %d tickers (%d skipped as no-data)", len(todo), len(items), len(items) - len(todo))
    t_fetch = time.time()
    data = fetch([u["yahoo"] for u in todo])
    fetch_secs = round(time.time() - t_fetch)
    for u in todo:
        if u["yahoo"] in data: miss.pop(u["yahoo"], None)
        else: miss[u["yahoo"]] = miss.get(u["yahoo"], 0) + 1
    if len(data) > 0.3 * len(todo): (ROOT / "nodata.json").write_text(json.dumps(nd))
    bse_items = [u for u in items if u["exchange"] == "BSE"]
    bse_stats = {"listed": len(bse_items), "priced": sum(1 for u in bse_items if u["yahoo"] in data), "signals": 0, "skipped": sum(1 for u in bse_items if miss.get(u["yahoo"], 0) >= 2)} if scan_bse else (old.get("bse_stats"))
    if not data: log.error("No price data fetched"); sys.exit(1)
    latest = max(d.dropna().index[-1].date() for d in data.values() if not d.dropna().empty)
    if latest != now.date() and not (a.force or a.summary):
        log.info("No bar for today (holiday?), skipping"); return
    sigs, yh = [], {}
    for u in items:
        df = data.get(u["yahoo"])
        if df is None: continue
        CUR[0] = u["exchange"]
        s = classify(u["symbol"], df, dict(c, min_avg_volume=c["bse_min_avg_volume"]) if u["exchange"] == "BSE" else c)
        if s:
            s.update(exchange=u["exchange"], name=u["name"]); sigs.append(s)
            yh[f"{u['exchange']}:{u['symbol']}"] = u["yahoo"]
    if scan_bse and bse_stats: bse_stats["signals"] = sum(1 for s in sigs if s["exchange"] == "BSE"); bse_stats["rejected"] = {k[4:]: v for k, v in WHY.items() if k.startswith("BSE:")}; log.info("BSE stats: %s", bse_stats)
    mc = get_mcaps([dict(key=k, yahoo=y) for k, y in yh.items()])
    for s in sigs:
        cr = mc.get(f"{s['exchange']}:{s['symbol']}"); s["mcap"] = cr; s["mcap_cat"] = mcap_cat(cr, c)
    if not scan_bse:
        sigs += [s for s in old.get("signals", []) if s.get("exchange") == "BSE"]
    pos, users = load_positions(), cloud_users()
    allpos = {pos_key(p): p for p in pos + [p for u in users for p in u["positions"]] if is_open(p)}
    quotes = position_quotes(list(allpos.values()), c)
    (ROOT / "signals.json").write_text(json.dumps(
        {"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "ma_period": c["ma_period"], "ma_type": c["ma_type"],
         "near_pct": c["near_pct"], "universe": "NSE + BSE" if c["include_bse"] else "NSE",
         "bse_updated": dt.datetime.now(dt.timezone.utc).isoformat() if scan_bse else old.get("bse_updated"),
         "cloud": CLOUD, "fetch_secs": fetch_secs, "prefilter": PRE or None, "bse_stats": bse_stats,
         "bse_error": "; ".join(BSE_ERR) if scan_bse and BSE_ERR else None,
         "signals": sigs, "quotes": quotes}, indent=1))
    st = read_json("state.json", {})
    if st.get("date") != str(now.date()): st = {"date": str(now.date()), "sent": [], "pos_sent": []}
    st.setdefault("sent", []); st.setdefault("pos_sent", [])
    if a.summary:
        notify(format_msg(sigs, f"📊 {c['ma_period']}-DMA daily summary", c["max_near_alerts"])); return
    sk = lambda s: f"{s['exchange']}:{s['symbol']}:{s['type']}"
    new = [s for s in sigs if sk(s) not in st["sent"]]
    if new and notify(format_msg(new, f"📈 {c['ma_period']}-{c['ma_type']} alert {now:%H:%M} IST", c["max_near_alerts"])):
        st["sent"] += [sk(s) for s in new]
    ev = [e for e in position_events(pos, quotes, c) if e[0] not in st["pos_sent"]]
    if ev and notify("📌 Position alerts\n" + "\n".join(t for _, t in ev) + "\n\nResearch alert only, not financial advice."):
        st["pos_sent"] += [k for k, _ in ev]
    for u in users:
        uev = [e for e in position_events(u["positions"], quotes, c) if f"{u['uid']}:{e[0]}" not in st["pos_sent"]]
        if uev and send_telegram(u["chat"], "📌 Position alerts\n" + "\n".join(t for _, t in uev) + "\n\nResearch alert only, not financial advice."):
            st["pos_sent"] += [f"{u['uid']}:{k}" for k, _ in uev]; ev += uev
    (ROOT / "state.json").write_text(json.dumps(st))
    try:
        sj = json.loads((ROOT / "signals.json").read_text()); sj["cloud"] = CLOUD
        (ROOT / "signals.json").write_text(json.dumps(sj, indent=1))
    except Exception as e: log.warning("could not record alert status: %s", e)
    log.info("%d symbols, %d signals, %d new, %d position alerts", len(data), len(sigs), len(new), len(ev))

if __name__ == "__main__":
    main()
