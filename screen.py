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
            for s, n, i in zip(out.symbol, out.name, out.isin)]

def bse_universe(skip_isins, groups):
    """BSE-only stocks (those not already listed on NSE, matched by ISIN). Yahoo uses scrip code + .BO"""
    cache = ROOT / "universe_bse.csv"
    try:
        h = dict(UA, Referer="https://www.bseindia.com/", Accept="application/json")
        r = requests.get(BSE_URL, headers=h, timeout=45); r.raise_for_status()
        rec = []
        for x in r.json():
            code, isin, grp = pick(x, "SCRIP_CD"), pick(x, "ISIN_NUMBER", "ISIN"), pick(x, "GROUP", "Scrip_Grp")
            if not code.isdigit() or (isin and isin in skip_isins) or (groups and grp and grp not in groups): continue
            rec.append(dict(symbol=pick(x, "scrip_id") or code, name=pick(x, "Scrip_Name", "Issuer_Name"), isin=isin, code=code))
        if not rec: raise ValueError("empty BSE list")
        pd.DataFrame(rec).to_csv(cache, index=False)
    except Exception as e:
        log.warning("BSE list failed (%s); using cache", e)
        if not cache.exists(): return []
        rec = pd.read_csv(cache, dtype=str).fillna("").to_dict("records")
    return [dict(symbol=r["symbol"], name=r["name"], isin=r["isin"], exchange="BSE", yahoo=str(r["code"]) + ".BO") for r in rec]

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

def classify(sym, df, c):
    """Return a signal dict (buy/sell/near) or None. Pure function, easy to test."""
    df = df.dropna(subset=["Close"])
    if len(df) < c["ma_period"] + 2: return None
    close = df["Close"]; m = moving_avg(close, c["ma_type"], c["ma_period"])
    c0, c1, m0, m1 = close.iloc[-1], close.iloc[-2], m.iloc[-1], m.iloc[-2]
    if c0 < c["min_price"] or df["Volume"].tail(20).mean() < c["min_avg_volume"]: return None
    pct = (c0 / m0 - 1) * 100
    if c1 <= m1 and c0 > m0: kind = "buy"
    elif c1 >= m1 and c0 < m0: kind = "sell"
    elif abs(pct) <= c["near_pct"]: kind = "near"
    else: return None
    name, pos = candle_info(df)
    prev_vol = df["Volume"].iloc[-21:-1].mean()
    vol_x = float(df["Volume"].iloc[-1] / prev_vol) if prev_vol > 0 else 0.0
    direction = 1 if kind == "buy" else -1 if kind == "sell" else (1 if pct < 0 else -1)
    return dict(symbol=sym, price=round(float(c0), 2), ma=round(float(m0), 2), pct=round(float(pct), 2),
                volume=int(df["Volume"].iloc[-1]), type=kind, candle=name,
                score=conviction(direction, name, pos, vol_x), vol_x=round(vol_x, 1), **extras(close, m, c0, c1))

def fetch(tickers, batch=150, period="1y"):
    """Download daily OHLCV for Yahoo tickers. Returns {ticker: DataFrame}."""
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]; d = None
        for attempt in range(3):
            try:
                d = yf.download(chunk, period=period, interval="1d", group_by="ticker", threads=True,
                                progress=False, auto_adjust=False); break
            except Exception as e:
                log.warning("batch %d retry %d: %s", i, attempt, e); time.sleep(5 * (attempt + 1))
        if d is None or d.empty: continue
        for t in chunk:
            try: out[t] = d[t][["Open", "High", "Low", "Close", "Volume"]]
            except KeyError: pass
        time.sleep(1)
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
def load_positions():
    f = ROOT / "positions.json"
    if not f.exists(): return []
    try:
        d = json.loads(f.read_text()); d = d["positions"] if isinstance(d, dict) else d
        return [p for p in d if p.get("symbol")]
    except Exception as e:
        log.warning("positions.json unreadable: %s", e); return []

def redis(cmd):
    """Upstash Redis over REST. Returns None when not configured."""
    url, tok = os.getenv("UPSTASH_URL"), os.getenv("UPSTASH_TOKEN")
    if not (url and tok): return None
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"}, json=cmd, timeout=20)
    r.raise_for_status(); return r.json().get("result")

def cloud_users():
    """Everyone who connected Telegram on the website: [{uid, chat, positions}]."""
    try:
        uids = redis(["SMEMBERS", "users"]) or []
        out = []
        for uid in uids:
            chat, raw = redis(["GET", f"chat:{uid}"]), redis(["GET", f"pos:{uid}"])
            if not chat or not raw: continue
            d = json.loads(raw); d = d["positions"] if isinstance(d, dict) else d
            out.append(dict(uid=uid, chat=chat, positions=[p for p in d if p.get("symbol")]))
        return out
    except Exception as e:
        log.warning("Cloud positions unavailable: %s", e); return []

def send_telegram(chat, text):
    tok = os.getenv("TELEGRAM_TOKEN")
    if not tok: log.warning("TELEGRAM_TOKEN missing; cannot message %s", chat); return False
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": True})
    log.info("telegram user alert %s", r.status_code); return r.ok

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
    for p in pos:
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
    data = fetch([u["yahoo"] for u in items])
    if not data: log.error("No price data fetched"); sys.exit(1)
    latest = max(d.dropna().index[-1].date() for d in data.values() if not d.dropna().empty)
    if latest != now.date() and not (a.force or a.summary):
        log.info("No bar for today (holiday?), skipping"); return
    sigs, yh = [], {}
    for u in items:
        df = data.get(u["yahoo"])
        if df is None: continue
        s = classify(u["symbol"], df, dict(c, min_avg_volume=c["bse_min_avg_volume"]) if u["exchange"] == "BSE" else c)
        if s:
            s.update(exchange=u["exchange"], name=u["name"]); sigs.append(s)
            yh[f"{u['exchange']}:{u['symbol']}"] = u["yahoo"]
    mc = get_mcaps([dict(key=k, yahoo=y) for k, y in yh.items()])
    for s in sigs:
        cr = mc.get(f"{s['exchange']}:{s['symbol']}"); s["mcap"] = cr; s["mcap_cat"] = mcap_cat(cr, c)
    if not scan_bse:
        sigs += [s for s in old.get("signals", []) if s.get("exchange") == "BSE"]
    pos, users = load_positions(), cloud_users()
    allpos = {pos_key(p): p for p in pos + [p for u in users for p in u["positions"]]}
    quotes = position_quotes(list(allpos.values()), c)
    (ROOT / "signals.json").write_text(json.dumps(
        {"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "ma_period": c["ma_period"], "ma_type": c["ma_type"],
         "near_pct": c["near_pct"], "universe": "NSE + BSE" if c["include_bse"] else "NSE",
         "bse_updated": dt.datetime.now(dt.timezone.utc).isoformat() if scan_bse else old.get("bse_updated"),
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
    log.info("%d symbols, %d signals, %d new, %d position alerts", len(data), len(sigs), len(new), len(ev))

if __name__ == "__main__":
    main()
