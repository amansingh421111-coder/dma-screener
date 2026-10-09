"""Strategy library: each strategy is a plain written rule. This file backtests them honestly and reports, for every stock,
today's state (b = buy signal, h = holding it, s = exit signal, - = nothing).

Usage:  python strategies.py --mode full      (weekly: download ~6 years, backtest, write strategies.json)
        python strategies.py --mode states    (daily after the close: refresh each stock's state, keep the saved statistics)

How the test avoids the usual traps:
  * a signal seen at the close is bought at the NEXT day's open (no peeking at the signal day's price)
  * prices are adjusted for splits and bonuses
  * every trade pays a round-trip cost (default 0.4%: brokerage-free delivery still pays STT, charges and slippage)
  * every trade has the same protective stop (default 8% below entry; gaps below it fill at the open) and a maximum holding time
  * the history is split in two: the rules are judged on the later 40% they were not tuned on ("test")
Known limits: the stock list is today's liquid stocks, so delisted losers are missing (survivorship bias flatters results)."""
import argparse, datetime as dt, json, logging, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("strat")

def sma(s, n): return s.rolling(n).mean()
def rsi(close, n=14):
    d = close.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def cross_up(a, b): return (a > b) & (a.shift(1) <= b.shift(1))

# each strategy: id, name, written rule, written exit, function(df) -> (entry, exit) boolean Series
def s_dma44_cross(df):
    c, m = df["Close"], sma(df["Close"], 44)
    return cross_up(c, m) & (c <= m * 1.05), c < m
def s_dma44_pull(df):
    c, m = df["Close"], sma(df["Close"], 44)
    stretched = (c / m - 1).rolling(20).max().shift(1) >= 0.08
    return (c >= m) & (c <= m * 1.02) & (m > m.shift(5)) & stretched & (c.shift(1) > m.shift(1) * 1.02), c < m
def s_ma_cross(df):
    a, b = sma(df["Close"], 20), sma(df["Close"], 50)
    return cross_up(a, b), a < b
def s_breakout(df):
    c, v = df["Close"], df["Volume"]
    return (c > c.shift(1).rolling(252).max()) & (v > 1.5 * v.shift(1).rolling(20).mean()), c < sma(c, 50)
def s_pullback(df):
    c = df["Close"]; r = rsi(c); m200 = sma(c, 200)
    return (c > m200) & (r < 35), (r > 60) | (c < m200)
def s_surge(df):
    c, v = df["Close"], df["Volume"]
    return (v >= 2 * v.shift(1).rolling(20).mean()) & (c / c.shift(1) - 1 >= 0.03) & (c > sma(c, 50)), c < sma(c, 20)
def s_base(df):
    c = df["Close"]; hi, lo = c.shift(1).rolling(40).max(), c.shift(1).rolling(40).min()
    return (c > hi) & (hi / lo - 1 <= 0.25), c < sma(c, 20)
def s_momentum(df):
    c = df["Close"]; cond = (c / c.shift(126) - 1 > 0.20) & (c >= 0.9 * c.rolling(252).max()) & (c > sma(c, 50))
    return cond & ~cond.shift(1, fill_value=False), c < sma(c, 50)

STRATS = [
    dict(id="dma44_cross", name="44-DMA cross-up", fn=s_dma44_cross,
         rule="Close crosses above the 44-day average and finishes within 5% of it.", exit="Close falls below the 44-day average."),
    dict(id="dma44_pull", name="44-DMA pullback", fn=s_dma44_pull,
         rule="A rising 44-day average; the stock was at least 8% above it in the last 20 days, then falls back to within 2% above it.", exit="Close falls below the 44-day average."),
    dict(id="ma_cross", name="20/50 average cross", fn=s_ma_cross,
         rule="The 20-day average crosses above the 50-day average.", exit="The 20-day average falls back below the 50-day average."),
    dict(id="breakout", name="52-week high breakout", fn=s_breakout,
         rule="Close above the highest close of the last 252 days, with volume above 1.5 times the 20-day average.", exit="Close falls below the 50-day average."),
    dict(id="pullback200", name="Oversold in an uptrend", fn=s_pullback,
         rule="Close above the 200-day average while the 14-day RSI is below 35.", exit="RSI above 60, or close below the 200-day average."),
    dict(id="surge", name="Volume surge", fn=s_surge,
         rule="Volume at least 2 times the 20-day average and the stock up 3% or more on the day, while above its 50-day average.", exit="Close falls below the 20-day average."),
    dict(id="base", name="Base breakout", fn=s_base,
         rule="Close above the highest close of the last 40 days, after a base no wider than 25% from low to high.", exit="Close falls below the 20-day average."),
    dict(id="momentum", name="Strong momentum", fn=s_momentum,
         rule="Up more than 20% in 6 months, within 10% of its 52-week high and above its 50-day average (first day only).", exit="Close falls below the 50-day average."),
]

def simulate(df, entry, exit_, stop_pct=8.0, max_hold=120, cost=0.004):
    """Returns (closed trades, open_trade_or_None). Buys at the next open after a signal; exits at the next open after an exit signal,
    at the stop (or the open if it gaps below), or at the close of the maximum holding day."""
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    idx = df.index; n = len(df); en = entry.fillna(False).to_numpy(bool); ex = exit_.fillna(False).to_numpy(bool)
    trades, open_t, i = [], None, 0
    for s in np.flatnonzero(en):
        if s < i or s >= n - 1: continue
        ei = s + 1; ep = o[ei]
        if not np.isfinite(ep) or ep <= 0: continue
        stop = ep * (1 - stop_pct / 100); xk = xp = None
        for k in range(ei, min(n, ei + max_hold + 1)):
            if np.isfinite(l[k]) and l[k] <= stop: xk, xp = k, min(o[k], stop) if np.isfinite(o[k]) else stop; break
            if k > ei and ex[k - 1] and np.isfinite(o[k]): xk, xp = k, o[k]; break
            if k == ei + max_hold and np.isfinite(c[k]): xk, xp = k, c[k]; break
        if xk is None:
            open_t = dict(entry=str(idx[ei].date()), entry_price=float(ep), exit_signal=bool(ex[n - 1])); break
        trades.append(dict(entry=str(idx[ei].date()), exit=str(idx[xk].date()), days=int(xk - ei), ret=float(xp / ep - 1 - cost)))
        i = xk
    return trades, open_t

def stats(tr, baseline_ret=None):
    if not tr: return None
    r = np.array([t["ret"] for t in tr]); w, lo = r[r > 0], r[r <= 0]
    pf = float(w.sum() / -lo.sum()) if lo.sum() < 0 else None
    seq = np.array([t["ret"] for t in sorted(tr, key=lambda t: t["exit"])]); cum = np.cumsum(seq); dd = float((np.maximum.accumulate(cum) - cum).max())
    streak = cur = 0
    for x in seq: cur = cur + 1 if x <= 0 else 0; streak = max(streak, cur)
    d = dict(n=len(tr), win_rate=round(float((r > 0).mean()), 3), avg_ret=round(float(r.mean()), 4), avg_win=round(float(w.mean()), 4) if len(w) else None,
             avg_loss=round(float(lo.mean()), 4) if len(lo) else None, profit_factor=None if pf is None else round(pf, 2),
             median_days=int(np.median([t["days"] for t in tr])), worst=round(float(r.min()), 4), worst_streak=int(streak), max_drawdown=round(dd, 3))
    if baseline_ret is not None: d["edge"] = round(d["avg_ret"] - baseline_ret, 4)
    return d

def verdict(train, test):
    """Plain, rule-based label for the strategy. It judges the later period only, and needs the earlier one to agree in sign."""
    if not test or test["n"] < 60: return "unproven"
    good = test["avg_ret"] >= 0.008 and (test["profit_factor"] or 0) >= 1.3 and test.get("edge", 0) > 0 and test["n"] >= 150 and bool(train) and train["avg_ret"] > 0
    if good: return "reliable"
    if test["avg_ret"] > 0 and test.get("edge", 0) > 0: return "mixed"
    return "unreliable"

def adjusted_download(tickers, years, batch=50, budget=1500):
    import yfinance as yf
    out, t0 = {}, time.time()
    for i in range(0, len(tickers), batch):
        if time.time() - t0 > budget: log.warning("time budget reached at %d tickers", i); break
        chunk = tickers[i:i + batch]
        for attempt in range(2):
            try:
                d = yf.download(chunk, period=f"{years}y", interval="1d", group_by="ticker", threads=True, progress=False, auto_adjust=True)
                if d is not None and not d.empty:
                    for t in chunk:
                        try:
                            x = d[t][["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                            if len(x) > 300: out[t] = x
                        except KeyError: pass
                    break
            except Exception as e: log.warning("batch %d retry: %s", i, str(e)[:80])
            time.sleep(3)
    return out

def liquid_universe(top):
    from screen import load_bhav, BHAV
    load_bhav(); b = BHAV.get("NSE")
    if not b: raise SystemExit("official NSE file unavailable")
    rows = [(k, v[6] or 0, v[3] or 0) for k, v in b[1].items() if (v[3] or 0) >= 50]
    rows.sort(key=lambda x: -x[1]); return [k for k, _, _ in rows[:top]], str(b[0])

def run(mode, top, years, cost, stop_pct):
    old = {}
    try: old = json.loads((ROOT / "strategies.json").read_text())
    except Exception: pass
    if mode == "states" and not old.get("strategies"): mode = "full"
    syms, bhav_day = liquid_universe(top)
    data = adjusted_download([s + ".NS" for s in syms], years if mode == "full" else 2)
    if len(data) < 100: raise SystemExit(f"only {len(data)} stocks downloaded; not updating")
    last_dates = pd.Series([d.index[-1].date() for d in data.values()]); price_date = str(last_dates.mode().iloc[0])
    states = {k: ["-"] * len(STRATS) for k in data}; todays = {s["id"]: dict(buy=[], sell=[], hold=0) for s in STRATS}
    all_tr = {s["id"]: [] for s in STRATS}; daily = []
    if mode == "full":
        longest = max(data.values(), key=len).index; split = str(longest[int(len(longest) * 0.6)].date())
    else: split = old.get("split")
    for key, df in data.items():
        sym = key[:-3]
        if mode == "full": daily.append(df["Close"].pct_change().dropna().loc[split:] if split else None)
        for j, s in enumerate(STRATS):
            try: en, ex = s["fn"](df)
            except Exception as e: log.warning("%s on %s: %s", s["id"], sym, str(e)[:60]); continue
            tr, op = simulate(df, en, ex, stop_pct, 120, cost)
            if mode == "full": all_tr[s["id"]] += [dict(t, sym=sym) for t in tr]
            last_buy = bool(en.iloc[-1]) if len(en) else False
            if op: st = "s" if op["exit_signal"] else "h"
            elif last_buy: st = "b"
            else: st = "-"
            states[key][j] = st
            if st == "b": todays[s["id"]]["buy"].append(sym)
            elif st == "s": todays[s["id"]]["sell"].append(sym)
            elif st == "h": todays[s["id"]]["hold"] += 1
    out = dict(old) if mode == "states" else {}
    out.update(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=price_date, official_date=bhav_day, stale=price_date < bhav_day,
               universe=f"Top {len(data)} NSE stocks by traded value", order=[s["id"] for s in STRATS], states={f"NSE:{k[:-3]}": "".join(v) for k, v in states.items()})
    if mode == "full":
        rd = pd.concat([d for d in daily if d is not None]).mean() if daily else 0.0
        out.update(years=years, cost_pct=round(cost * 100, 2), stop_pct=stop_pct, max_hold_days=120, split=split, strategies=[])
        for s in STRATS:
            tr = all_tr[s["id"]]
            train = [t for t in tr if t["entry"] < split]; test = [t for t in tr if t["entry"] >= split]
            base = lambda x: ((1 + rd) ** (np.mean([t["days"] for t in x]) * 0.69) - 1 - cost) if x else None   # about 0.69 trading days per calendar day
            a, b = stats(train, base(train)), stats(test, base(test))
            out["strategies"].append(dict(id=s["id"], name=s["name"], rule=s["rule"], exit=s["exit"], train=a, test=b, verdict=verdict(a, b)))
    for s in out.get("strategies", []):
        t = todays.get(s["id"], {}); s["today"] = dict(buy=sorted(t.get("buy", []))[:40], buy_n=len(t.get("buy", [])), sell=sorted(t.get("sell", []))[:40], sell_n=len(t.get("sell", [])), hold_n=t.get("hold", 0))
    out["caveats"] = ["Signals are bought at the next day's open; every trade pays the round-trip cost and has the same protective stop.",
                      "Judged on the later 40% of the history only. Past results do not predict future returns.",
                      "The stock list is today's liquid stocks, so stocks that were delisted are missing and results look better than real life would have been."]
    (ROOT / "strategies.json").write_text(json.dumps(out, separators=(",", ":")))
    for s in out.get("strategies", []): print(f"{s['name']:28s} {s['verdict']:11s} test n={ (s['test'] or {}).get('n')} avg={(s['test'] or {}).get('avg_ret')} pf={(s['test'] or {}).get('profit_factor')}")
    print("stocks:", len(data), "price date:", price_date, "stale:", out["stale"])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="states", choices=["full", "states"]); ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--years", type=int, default=6); ap.add_argument("--cost", type=float, default=0.004); ap.add_argument("--stop", type=float, default=8.0)
    a = ap.parse_args(); run(a.mode, a.top, a.years, a.cost, a.stop)
