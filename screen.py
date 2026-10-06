"""Auto NSE screener: 44-DMA cross / approach alerts. Alerts only, never places orders.

This version also carries an explicit exchange field through the signal payload.
The current universe is NSE EQ, so exchange is NSE unless a future multi-exchange
universe/config supplies another value.
"""
import argparse, datetime as dt, io, json, logging, os, smtplib, sys, time
from email.mime.text import MIMEText
from pathlib import Path

import numpy as np, pandas as pd, requests, yaml

ROOT = Path(__file__).resolve().parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
log = logging.getLogger("dma")
NSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
DEFAULT_EXCHANGE = "NSE"


def load_cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def universe():
    """Return the current NSE equity universe from NSE's official security list."""
    cache = ROOT / "universe.csv"
    try:
        r = requests.get(NSE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        syms = df[df["SERIES"].str.strip() == "EQ"]["SYMBOL"].str.strip().tolist()
        pd.DataFrame({"SYMBOL": syms, "EXCHANGE": DEFAULT_EXCHANGE}).to_csv(cache, index=False)
        return syms
    except Exception as e:
        log.warning("NSE list failed (%s); using cached list", e)
        cached = pd.read_csv(cache)
        return cached["SYMBOL"].tolist()


def moving_avg(close, kind, n):
    return close.rolling(n).mean() if kind.upper() == "SMA" else close.ewm(span=n, adjust=False).mean()


def candle_info(df):
    """Name the latest candle and where it closed in its range (0=low, 1=high)."""
    if not {"Open", "High", "Low"} <= set(df.columns):
        return None, 0.5
    r = df.iloc[-1]
    vals = [r[x] for x in ("Open", "High", "Low", "Close")]
    if any(pd.isna(v) for v in vals):
        return None, 0.5
    o, h, l, c = map(float, vals)
    rng = h - l
    if rng <= 0:
        return "doji", 0.5
    body, pos = abs(c - o), (c - l) / rng
    lw, uw = min(o, c) - l, h - max(o, c)
    if lw >= 2 * body and pos >= 0.6 and body > 0:
        name = "hammer"
    elif uw >= 2 * body and pos <= 0.4 and body > 0:
        name = "shooting_star"
    elif body / rng < 0.15:
        name = "doji"
    else:
        name = "bullish" if c > o else "bearish"
    return name, pos


def conviction(direction, name, pos, vol_x):
    """0-3 points: candle agrees with expected move, close near the extreme, volume surge."""
    if name is None:
        return 0
    pts = 0
    if direction > 0:
        pts += name in ("bullish", "hammer")
        pts += pos >= 0.67
    else:
        pts += name in ("bearish", "shooting_star")
        pts += pos <= 0.33
    return int(pts + (vol_x >= 1.5))


def rsi14(close):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    return round(float(100 - 100 / (1 + up / dn)), 1) if dn > 0 else 100.0


def extras(close, m, c0, c1):
    """Extra screening fields: day change, RSI, 200-DMA trend, 52W position, days on side, mini-chart data."""
    m200 = close.rolling(200).mean().iloc[-1]
    hi, lo = float(close.tail(252).max()), float(close.tail(252).min())
    cur = bool(close.iloc[-1] > m.iloc[-1])
    idx = np.where(m.notna().values & ((close > m).values != cur))[0]
    return dict(
        chg=round(float((c0 / c1 - 1) * 100), 2),
        rsi=rsi14(close),
        above200=bool(c0 > m200) if pd.notna(m200) else None,
        hi52=round(hi, 2),
        lo52=round(lo, 2),
        from_hi=round(float((c0 / hi - 1) * 100), 1),
        since=int(len(close) - 1 - idx[-1]) if idx.size else None,
        spark=[round(float(x), 2) for x in close.tail(60)],
        sparkma=[None if pd.isna(x) else round(float(x), 2) for x in m.tail(60)],
    )


def classify(sym, df, c, exchange=DEFAULT_EXCHANGE):
    """Return a signal dict (buy/sell/near) or None."""
    df = df.dropna(subset=["Close"])
    if len(df) < c["ma_period"] + 2:
        return None
    close = df["Close"]
    m = moving_avg(close, c["ma_type"], c["ma_period"])
    c0, c1, m0, m1 = close.iloc[-1], close.iloc[-2], m.iloc[-1], m.iloc[-2]
    if c0 < c["min_price"] or df["Volume"].tail(20).mean() < c["min_avg_volume"]:
        return None
    pct = (c0 / m0 - 1) * 100
    if c1 <= m1 and c0 > m0:
        kind = "buy"
    elif c1 >= m1 and c0 < m0:
        kind = "sell"
    elif abs(pct) <= c["near_pct"]:
        kind = "near"
    else:
        return None
    name, pos = candle_info(df)
    prev_vol = df["Volume"].iloc[-21:-1].mean()
    vol_x = float(df["Volume"].iloc[-1] / prev_vol) if prev_vol > 0 else 0.0
    direction = 1 if kind == "buy" else -1 if kind == "sell" else (1 if pct < 0 else -1)
    return dict(
        symbol=sym,
        exchange=exchange,
        price=round(float(c0), 2),
        ma=round(float(m0), 2),
        pct=round(float(pct), 2),
        volume=int(df["Volume"].iloc[-1]),
        type=kind,
        candle=name,
        score=conviction(direction, name, pos, vol_x),
        vol_x=round(vol_x, 1),
        **extras(close, m, c0, c1),
    )


def fetch(syms, batch=150, period="1y"):
    import yfinance as yf
    out = {}
    for i in range(0, len(syms), batch):
        chunk = [s + ".NS" for s in syms[i:i + batch]]
        d = None
        for attempt in range(3):
            try:
                d = yf.download(
                    chunk, period=period, interval="1d", group_by="ticker",
                    threads=True, progress=False, auto_adjust=False
                )
                break
            except Exception as e:
                log.warning("batch %d retry %d: %s", i, attempt, e)
                time.sleep(5 * (attempt + 1))
        if d is None or d.empty:
            continue
        for t in chunk:
            try:
                out[t[:-3]] = d[t][["Open", "High", "Low", "Close", "Volume"]]
            except KeyError:
                pass
        time.sleep(1)
    return out


def format_msg(sigs, title, cap):
    lines = [title]
    for kind, label in (("buy", "🟢 BUY signals"), ("sell", "🔴 SELL signals"), ("near", "🟡 Approaching")):
        g = sorted(
            [s for s in sigs if s["type"] == kind],
            key=lambda s: (-s.get("score", 0), abs(s["pct"]))
        )
        if not g:
            continue
        lines.append(f"\n{label} ({len(g)})")
        for s in g[:cap]:
            lines.append(
                f"{s['symbol']} [{s.get('exchange', DEFAULT_EXCHANGE)}]  ₹{s['price']}  "
                f"MA ₹{s['ma']}  {s['pct']:+}%  {s.get('candle') or ''} "
                f"{'★' * s.get('score', 0)}{'☆' * (3 - s.get('score', 0))}  "
                f"https://www.tradingview.com/chart/?symbol={s.get('exchange', DEFAULT_EXCHANGE)}:{s['symbol']}"
            )
    lines.append("\nResearch alert only, not financial advice.")
    return "\n".join(lines)[:4000]


def notify(text):
    sent = False
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
            data={"chat_id": chat, "text": text, "disable_web_page_preview": True}
        )
        log.info("telegram %s", r.status_code)
        sent = r.ok
    user, pw, to = os.getenv("EMAIL_USER"), os.getenv("EMAIL_APP_PASSWORD"), os.getenv("EMAIL_TO")
    if user and pw and to:
        msg = MIMEText(text)
        msg["Subject"] = text.split("\n")[0]
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
        sent = True
    if not sent:
        log.warning("No alert channel configured (set secrets)")
    return sent


def in_market_hours(now):
    return now.weekday() < 5 and dt.time(9, 15) <= now.time() <= dt.time(15, 45)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore market-hours gate")
    ap.add_argument("--summary", action="store_true", help="send full end-of-day summary")
    ap.add_argument("--test-alert", action="store_true", help="send a sample alert and exit")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    c = load_cfg()
    now = dt.datetime.now(IST)
    exchange = str(c.get("exchange", DEFAULT_EXCHANGE)).upper()

    if a.test_alert:
        demo = [dict(symbol="RELIANCE", exchange=exchange, price=2910.5, ma=2875.2, pct=1.2, volume=1, type="buy")]
        sys.exit(0 if notify(format_msg(demo, "🧪 TEST alert", 5)) else 1)
    if not (a.force or a.summary or in_market_hours(now)):
        log.info("Outside market hours, skipping")
        return

    data = fetch(universe())
    if not data:
        log.error("No price data fetched")
        sys.exit(1)
    latest = max(d.dropna().index[-1].date() for d in data.values() if not d.dropna().empty)
    if latest != now.date() and not (a.force or a.summary):
        log.info("No bar for today (holiday?), skipping")
        return

    sigs = [s for s in (classify(k, v, c, exchange) for k, v in data.items()) if s]
    (ROOT / "signals.json").write_text(json.dumps(
        {
            "updated": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ma_period": c["ma_period"],
            "ma_type": c["ma_type"],
            "universe_exchange": exchange,
            "signals": sigs,
        },
        indent=1,
    ))

    sf = ROOT / "state.json"
    st = json.loads(sf.read_text())
    if st["date"] != str(now.date()):
        st = {"date": str(now.date()), "sent": []}
    if a.summary:
        notify(format_msg(sigs, f"📊 {c['ma_period']}-DMA daily summary", c["max_near_alerts"]))
        return

    new = [s for s in sigs if f"{s['exchange']}:{s['symbol']}:{s['type']}" not in st["sent"]]
    if new and notify(format_msg(new, f"📈 {c['ma_period']}-{c['ma_type']} alert {now:%H:%M} IST", c["max_near_alerts"])):
        st["sent"] += [f"{s['exchange']}:{s['symbol']}:{s['type']}" for s in new]
    sf.write_text(json.dumps(st))
    log.info("%d symbols, %d signals, %d new", len(data), len(sigs), len(new))


if __name__ == "__main__":
    main()
