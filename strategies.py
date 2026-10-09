"""Strategy library. Every strategy is a written entry rule. Every trade leaves the same three ways: a stop loss, a profit target, or a time limit.
There is no "sell when it falls back below the average": winners are booked at the target, losers are cut at the stop.

Usage:  python strategies.py --mode full      (weekly: download ~6 years, test every strategy, write strategies.json)
        python strategies.py --mode states    (daily after the close: today's signals with entry, stop and target; keeps the saved statistics)

How the test stays honest:
  * a signal seen at the close is bought at the NEXT day's open (no peeking at the signal day's price)
  * prices are adjusted for splits and bonuses
  * every trade pays a round-trip cost (default 0.4%)
  * if a day touches both the stop and the target, the stop is assumed to hit first
  * a gap through the stop or target fills at the open, not at the stop/target price
  * the history is split in two. The stop/target pair for each strategy is CHOSEN on the earlier 60% only, then JUDGED on the later 40%
  * the later period is also split by market mood (Nifty above or below its 200-day average at the time of the signal)
Known limit: the stock list is today's liquid stocks, so stocks that failed or were delisted are missing (this flatters every result)."""
import argparse, datetime as dt, json, logging, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("strat")
MAX_HOLD = {"swing": 40, "short": 15}
GRID = {"swing": [(s, t) for s in (5, 8) for t in (10, 15, 20)], "short": [(s, t) for s in (4, 6) for t in (5, 8, 12)]}

def sma(s, n): return s.rolling(n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(close, n=14):
    d = close.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def cross_up(a, b): return (a > b) & (a.shift(1) <= b.shift(1))
def first(cond): return cond & ~cond.shift(1, fill_value=False)

def s_dma44_cross(df):
    c, m = df["Close"], sma(df["Close"], 44)
    return cross_up(c, m) & (c <= m * 1.05)
def s_dma44_zone(df):
    c, m = df["Close"], sma(df["Close"], 44)
    return first((c >= m) & (c <= m * 1.05) & (m > m.shift(5)))
def s_dma44_pull(df):
    c, m = df["Close"], sma(df["Close"], 44)
    stretched = (c / m - 1).rolling(20).max().shift(1) >= 0.08
    return (c >= m) & (c <= m * 1.02) & (m > m.shift(5)) & stretched & (c.shift(1) > m.shift(1) * 1.02)
def s_ma_cross(df): return cross_up(sma(df["Close"], 20), sma(df["Close"], 50))
def s_breakout(df):
    c, v = df["Close"], df["Volume"]
    return (c > c.shift(1).rolling(252).max()) & (v > 1.5 * v.shift(1).rolling(20).mean())
def s_oversold(df):
    c = df["Close"]; return (c > sma(c, 200)) & (rsi(c) < 35)
def s_surge(df):
    c, v = df["Close"], df["Volume"]
    return (v >= 2 * v.shift(1).rolling(20).mean()) & (c / c.shift(1) - 1 >= 0.03) & (c > sma(c, 50))
def s_base(df):
    c = df["Close"]; hi, lo = c.shift(1).rolling(40).max(), c.shift(1).rolling(40).min()
    return (c > hi) & (hi / lo - 1 <= 0.25)
def s_momentum(df):
    c = df["Close"]; return first((c / c.shift(126) - 1 > 0.20) & (c >= 0.9 * c.rolling(252).max()) & (c > sma(c, 50)))
def s_pull50(df):
    c = df["Close"]; m50 = sma(c, 50)
    return cross_up(c, m50) & (m50 > sma(c, 200)) & (c > sma(c, 200)) & (c <= m50 * 1.03)
def s_macd(df):
    c = df["Close"]; macd = ema(c, 12) - ema(c, 26); sig = ema(macd, 9)
    return cross_up(macd, sig) & (macd < 0) & (c > sma(c, 200))
def s_squeeze(df):
    c = df["Close"]; m, sd = sma(c, 20), c.rolling(20).std(); bw = (4 * sd) / m
    tight = bw <= bw.rolling(120).quantile(0.10)
    return (c > m + 2 * sd) & (tight.shift(1, fill_value=False).astype(float).rolling(5).max() > 0) & (c > sma(c, 50))
def s_nr7(df):
    h, l, c = df["High"], df["Low"], df["Close"]; rg = h - l
    nr7 = rg.shift(1) <= rg.shift(1).rolling(7).min()
    return nr7 & (c > h.shift(1)) & (c > sma(c, 50))
def s_gapup(df):
    o, h, c, v = df["Open"], df["High"], df["Close"], df["Volume"]
    return (o > h.shift(1) * 1.02) & (c > o) & (v >= 2 * v.shift(1).rolling(20).mean()) & (c > sma(c, 50))
def s_donchian(df):
    h, c = df["High"], df["Close"]; return (c > h.shift(1).rolling(20).max()) & (c > sma(c, 100))
def s_supertrend(df, n=10, mult=3.0):
    h, l, c = df["High"].to_numpy(float), df["Low"].to_numpy(float), df["Close"].to_numpy(float); N = len(c)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))); tr[0] = h[0] - l[0]
    atr = pd.Series(tr).rolling(n).mean().to_numpy(); hl2 = (h + l) / 2
    ub, lb = hl2 + mult * atr, hl2 - mult * atr; fu, fl = ub.copy(), lb.copy(); up = np.zeros(N, bool)
    for i in range(1, N):
        if not np.isfinite(atr[i]): continue
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1] or not np.isfinite(fu[i - 1])) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1] or not np.isfinite(fl[i - 1])) else fl[i - 1]
        up[i] = True if c[i] > fu[i - 1] else False if c[i] < fl[i - 1] else up[i - 1]
    u = pd.Series(up, index=df.index); return first(u) & (df["Close"] > sma(df["Close"], 100))
def s_rsi2(df):
    c = df["Close"]; return (c > sma(c, 200)) & (rsi(c, 2) < 10)
def s_boll_dip(df):
    c = df["Close"]; m, sd = sma(c, 20), c.rolling(20).std()
    return first((c < m - 2 * sd) & (c > sma(c, 200)))
def s_inside_reversal(df):
    h, l, c, o = df["High"], df["Low"], df["Close"], df["Open"]
    return (c > sma(c, 200)) & (c < c.shift(5) * 0.95) & (c > o) & (c > h.shift(1))

# kind: "swing" (stops 5/8%, targets 10/15/20%, 40-day limit) or "short" (stops 4/6%, targets 5/8/12%, 15-day limit)
STRATS = [
    dict(id="dma44_cross", name="44-DMA cross-up", kind="swing", fn=s_dma44_cross, rule="Close crosses above the 44-day average and finishes within 5% of it."),
    dict(id="dma44_zone", name="44-DMA buy zone (rising)", kind="swing", fn=s_dma44_zone, rule="First day the close is 0 to 5% above a rising 44-day average (the average is higher than 5 days ago)."),
    dict(id="dma44_pull", name="44-DMA pullback", kind="swing", fn=s_dma44_pull, rule="Rising 44-day average; the stock was at least 8% above it in the last 20 days, then falls back to within 2% above it."),
    dict(id="ma_cross", name="20/50 average cross", kind="swing", fn=s_ma_cross, rule="The 20-day average crosses above the 50-day average."),
    dict(id="pull50", name="Pullback to the 50-DMA in an uptrend", kind="swing", fn=s_pull50, rule="50-day average above the 200-day; the close comes back up through the 50-day average and finishes within 3% of it."),
    dict(id="breakout", name="52-week high breakout", kind="swing", fn=s_breakout, rule="Close above the highest close of the last 252 days, with volume above 1.5 times the 20-day average."),
    dict(id="base", name="Base breakout", kind="swing", fn=s_base, rule="Close above the highest close of the last 40 days, after a base no wider than 25% from low to high."),
    dict(id="donchian", name="20-day high breakout", kind="swing", fn=s_donchian, rule="Close above the highest high of the last 20 days while above the 100-day average."),
    dict(id="momentum", name="Strong momentum", kind="swing", fn=s_momentum, rule="Up more than 20% in 6 months, within 10% of its 52-week high and above its 50-day average (first day only)."),
    dict(id="squeeze", name="Volatility squeeze breakout", kind="swing", fn=s_squeeze, rule="After the Bollinger bands were at their tightest 10% of the last 120 days (within 5 days), the close breaks above the upper band, above the 50-day average."),
    dict(id="nr7", name="Narrow-range breakout (NR7)", kind="swing", fn=s_nr7, rule="Yesterday had the narrowest day range of the last 7; today closes above yesterday's high, above the 50-day average."),
    dict(id="gapup", name="Gap-up on volume", kind="swing", fn=s_gapup, rule="Opens more than 2% above yesterday's high, closes above its open, volume at least 2 times average, above the 50-day average."),
    dict(id="surge", name="Volume surge", kind="swing", fn=s_surge, rule="Volume at least 2 times the 20-day average and up 3% or more on the day, while above the 50-day average."),
    dict(id="supertrend", name="Supertrend flip up", kind="swing", fn=s_supertrend, rule="The Supertrend (10 days, 3 times ATR) turns up, with the close above the 100-day average."),
    dict(id="macd", name="MACD cross in an uptrend", kind="swing", fn=s_macd, rule="MACD crosses above its signal line while still below zero, with the close above the 200-day average."),
    dict(id="oversold", name="Oversold in an uptrend (RSI 14)", kind="short", fn=s_oversold, rule="Close above the 200-day average while the 14-day RSI is below 35."),
    dict(id="rsi2", name="Extreme dip (RSI 2)", kind="short", fn=s_rsi2, rule="Close above the 200-day average while the 2-day RSI is below 10."),
    dict(id="bolldip", name="Dip below the lower Bollinger band", kind="short", fn=s_boll_dip, rule="First close below the lower Bollinger band (20 days, 2 deviations) while above the 200-day average."),
    dict(id="reversal", name="Bounce after a 5% slide", kind="short", fn=s_inside_reversal, rule="Above the 200-day average, down more than 5% over 5 days, then an up day that closes above yesterday's high."),
]

def simulate(df, entry, stop_pct, target_pct, max_hold, cost=0.004, reg=None):
    """Buys at the next open after a signal. Leaves at the stop, the target, or the close of the last allowed day.
    Returns (closed trades, open trade or None)."""
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    idx = df.index; n = len(df); en = entry.fillna(False).to_numpy(bool)
    trades, open_t, i = [], None, 0
    for s in np.flatnonzero(en):
        if s < i or s >= n - 1: continue
        ei = s + 1; ep = o[ei]
        if not np.isfinite(ep) or ep <= 0: continue
        stop, tgt = ep * (1 - stop_pct / 100), ep * (1 + target_pct / 100); xk = xp = why = None
        last = ei + max_hold - 1
        for k in range(ei, min(n, last + 1)):
            if not (np.isfinite(l[k]) and np.isfinite(h[k]) and np.isfinite(o[k])): continue
            if k > ei and o[k] <= stop: xk, xp, why = k, o[k], "stop"; break
            if k > ei and o[k] >= tgt: xk, xp, why = k, o[k], "target"; break
            if l[k] <= stop: xk, xp, why = k, stop, "stop"; break
            if h[k] >= tgt: xk, xp, why = k, tgt, "target"; break
            if k == last and np.isfinite(c[k]): xk, xp, why = k, c[k], "time"; break
        if xk is None:
            open_t = dict(entry=str(idx[ei].date()), entry_price=float(ep), stop=float(stop), target=float(tgt)); break
        trades.append(dict(sig=str(idx[s].date()), entry=str(idx[ei].date()), exit=str(idx[xk].date()), days=int(xk - ei + 1), ret=float(xp / ep - 1 - cost), why=why,
                           up=None if reg is None else bool(reg[s])))
        i = xk
    return trades, open_t

def stats(tr, baseline_ret=None):
    if not tr: return None
    r = np.array([t["ret"] for t in tr]); w, lo = r[r > 0], r[r <= 0]
    pf = float(w.sum() / -lo.sum()) if lo.sum() < 0 else None
    seq = np.array([t["ret"] for t in sorted(tr, key=lambda t: t["exit"])]); cum = np.cumsum(seq); dd = float((np.maximum.accumulate(cum) - cum).max())
    streak = cur = 0
    for x in seq: cur = cur + 1 if x <= 0 else 0; streak = max(streak, cur)
    why = {k: sum(1 for t in tr if t["why"] == k) / len(tr) for k in ("target", "stop", "time")}
    yrs = {}
    for t in tr: yrs.setdefault(t["entry"][:4], []).append(t["ret"])
    ys = [np.mean(v) for v in yrs.values() if len(v) >= 10]
    d = dict(n=len(tr), win_rate=round(float((r > 0).mean()), 3), avg_ret=round(float(r.mean()), 4), avg_win=round(float(w.mean()), 4) if len(w) else None,
             avg_loss=round(float(lo.mean()), 4) if len(lo) else None, profit_factor=None if pf is None else round(pf, 2),
             median_days=int(np.median([t["days"] for t in tr])), worst=round(float(r.min()), 4), worst_streak=int(streak), max_drawdown=round(dd, 3),
             hit_target=round(why["target"], 3), hit_stop=round(why["stop"], 3), hit_time=round(why["time"], 3),
             years_pos=int(sum(1 for y in ys if y > 0)), years_n=len(ys))
    if baseline_ret is not None: d["edge"] = round(d["avg_ret"] - baseline_ret, 4)
    return d

def rate(train, test):
    """Stars out of 5, from the later (unseen) period only, with the earlier period as a sanity check. Returns (stars, verdict)."""
    if not test or test["n"] < 60: return 0.0, "unproven"
    pts = 0.0; a = test["avg_ret"]; pf = test["profit_factor"] or 0
    pts += 2.0 if a >= 0.015 else 1.5 if a >= 0.008 else 1.0 if a >= 0.004 else 0.5 if a > 0 else 0
    pts += 1.0 if pf >= 1.5 else 0.75 if pf >= 1.3 else 0.4 if pf >= 1.15 else 0
    pts += 0.5 if test["n"] >= 300 else 0.25 if test["n"] >= 150 else 0
    pts += 0.5 if train and train["avg_ret"] > 0 else 0
    pts += 0.5 if test.get("edge", 0) > 0 else 0
    if test["years_n"] >= 2 and test["years_pos"] / test["years_n"] >= 0.75: pts += 0.5
    if a <= 0: pts = min(pts, 1.0)
    stars = round(min(5.0, pts) * 2) / 2
    return stars, ("reliable" if stars >= 3.5 else "mixed" if stars >= 2.5 else "unreliable")

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

def nifty_regime(years):
    import yfinance as yf
    d = yf.download("^NSEI", period=f"{years}y", interval="1d", progress=False, auto_adjust=True)
    c = d["Close"].squeeze().dropna()
    if getattr(c.index, 'tz', None) is not None: c.index = c.index.tz_localize(None)
    ok = c > sma(c, 200)
    return c, ok

def liquid_universe(top):
    from screen import load_bhav, BHAV
    load_bhav(); b = BHAV.get("NSE")
    if not b: raise SystemExit("official NSE file unavailable")
    rows = [(k, v[6] or 0, v[3] or 0) for k, v in b[1].items() if (v[3] or 0) >= 50]
    rows.sort(key=lambda x: -x[1]); return [k for k, _, _ in rows[:top]], str(b[0])

def run(mode, top, years, cost):
    old = {}
    try: old = json.loads((ROOT / "strategies.json").read_text())
    except Exception: pass
    if mode == "states" and not old.get("strategies"): mode = "full"
    syms, bhav_day = liquid_universe(top)
    data = adjusted_download([s + ".NS" for s in syms], years if mode == "full" else 3)
    if len(data) < 100: raise SystemExit(f"only {len(data)} stocks downloaded; not updating")
    last_dates = pd.Series([d.index[-1].date() for d in data.values()]); price_date = str(last_dates.mode().iloc[0])
    nc, nok = nifty_regime(years if mode == "full" else 3)
    now_up = bool(nok.iloc[-1]) if len(nok) else None
    market = dict(nifty=round(float(nc.iloc[-1]), 1), nifty_200dma=round(float(sma(nc, 200).iloc[-1]), 1), above_200=now_up,
                  month_ret=round(float(nc.iloc[-1] / nc.iloc[-22] - 1), 4) if len(nc) > 22 else None)
    ab50 = [bool(d["Close"].iloc[-1] > sma(d["Close"], 50).iloc[-1]) for d in data.values() if len(d) > 60]
    ab200 = [bool(d["Close"].iloc[-1] > sma(d["Close"], 200).iloc[-1]) for d in data.values() if len(d) > 210]
    market.update(breadth50=round(float(np.mean(ab50)), 3), breadth200=round(float(np.mean(ab200)), 3), stocks=len(data))
    if mode == "full":
        longest = max(data.values(), key=len).index; split = str(longest[int(len(longest) * 0.6)].date())
    else: split = old.get("split")
    chosen = {s["id"]: tuple(s2["params"][k] for k in ("stop", "target")) for s in STRATS for s2 in old.get("strategies", []) if s2["id"] == s["id"] and "params" in s2} if mode == "states" else {}
    allt = {s["id"]: {g: [] for g in GRID[s["kind"]]} for s in STRATS}; daily = []
    states = {k: ["-"] * len(STRATS) for k in data}; todays = {s["id"]: dict(buy=[], hold=0, exit=[]) for s in STRATS}; opens = {}
    for key, df in data.items():
        sym = key[:-3]
        reg = nok.reindex(df.index, method="ffill").fillna(False).to_numpy(bool) if len(nok) else None
        if mode == "full": daily.append(df["Close"].pct_change().dropna().loc[split:])
        for j, s in enumerate(STRATS):
            try: en = s["fn"](df)
            except Exception as e: log.warning("%s on %s: %s", s["id"], sym, str(e)[:60]); continue
            mh = MAX_HOLD[s["kind"]]
            if mode == "full":
                for g in GRID[s["kind"]]:
                    tr, _ = simulate(df, en, g[0], g[1], mh, cost, reg)
                    allt[s["id"]][g] += [dict(t, sym=sym) for t in tr]
            else:
                g = chosen.get(s["id"]) or GRID[s["kind"]][0]
            if mode == "states":
                tr, op = simulate(df, en, g[0], g[1], mh, cost, reg)
                if op: states[key][j] = "h"; todays[s["id"]]["hold"] += 1
                elif tr and tr[-1]["exit"] == str(df.index[-1].date()): states[key][j] = "s"; todays[s["id"]]["exit"].append(sym)
            last_buy = bool(en.iloc[-1]) if len(en) else False
            if last_buy and states[key][j] != "h":
                states[key][j] = "b"; todays[s["id"]]["buy"].append(dict(s=sym, c=round(float(df["Close"].iloc[-1]), 2)))
    out = dict(old) if mode == "states" else {}
    out.update(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=price_date, official_date=bhav_day, stale=price_date < bhav_day, market=market,
               universe=f"Top {len(data)} NSE stocks by traded value", order=[s["id"] for s in STRATS], states={f"NSE:{k[:-3]}": "".join(v) for k, v in states.items()})
    if mode == "full":
        rd = float(pd.concat(daily).mean())
        out.update(years=years, cost_pct=round(cost * 100, 2), split=split, strategies=[])
        for s in STRATS:
            best = None; table = []
            for g, tr in allt[s["id"]].items():
                train = [t for t in tr if t["entry"] < split]; test = [t for t in tr if t["entry"] >= split]
                a = stats(train); table.append(dict(stop=g[0], target=g[1], train_n=len(train), train_avg=None if not a else a["avg_ret"], train_pf=None if not a else a["profit_factor"]))
                if a and a["n"] >= 60 and (best is None or a["avg_ret"] > best[0]): best = (a["avg_ret"], g, train, test)
            if best is None:
                g = GRID[s["kind"]][0]; tr = allt[s["id"]][g]; best = (0, g, [t for t in tr if t["entry"] < split], [t for t in tr if t["entry"] >= split])
            _, g, train, test = best
            base = lambda x: ((1 + rd) ** np.mean([t["days"] for t in x]) - 1 - cost) if x else None
            a, b = stats(train, base(train)), stats(test, base(test))
            ups, dns = [t for t in test if t["up"]], [t for t in test if t["up"] is False]
            stars, verdict = rate(a, b)
            out["strategies"].append(dict(id=s["id"], name=s["name"], rule=s["rule"], kind=s["kind"], params=dict(stop=g[0], target=g[1], max_hold=MAX_HOLD[s["kind"]]),
                                          exit=f"Sell at the target (+{g[1]}%), the stop loss (-{g[0]}%), or after {MAX_HOLD[s['kind']]} trading days, whichever comes first.",
                                          train=a, test=b, test_up=stats(ups), test_down=stats(dns), grid=table, stars=stars, verdict=verdict))
    for s in out.get("strategies", []):
        t = todays.get(s["id"], {}); p = s["params"]
        buys = sorted(t.get("buy", []), key=lambda x: x["s"])
        s["today"] = dict(buy=[dict(x, stop=round(x["c"] * (1 - p["stop"] / 100), 2), target=round(x["c"] * (1 + p["target"] / 100), 2)) for x in buys[:60]], buy_n=len(buys),
                          exit=sorted(t.get("exit", []))[:40] if mode == "states" else s.get("today", {}).get("exit", []), hold_n=t.get("hold", 0) if mode == "states" else s.get("today", {}).get("hold_n", 0))
    out["caveats"] = ["A signal is bought at the next day's open; every trade pays 0.4% round-trip costs; the stop is assumed to hit first if a day touches both stop and target.",
                      "The stop and target for each strategy were chosen on the earlier 60% of the history and judged on the later 40% only.",
                      "Past results do not predict the future. Testing many strategies means some will look good by luck: trust the ones with many trades, a clear edge and profits in most years.",
                      "The stock list is today's liquid stocks, so stocks that were delisted are missing and results look better than real life would have been.",
                      "News, results announcements and company events are not part of the test."]
    (ROOT / "strategies.json").write_text(json.dumps(out, separators=(",", ":")))
    for s in out.get("strategies", []):
        t = s["test"] or {}; print(f"{s['name']:40s} {s['stars']:3.1f}* {s['verdict']:10s} stop {s['params']['stop']} tgt {s['params']['target']} test n={t.get('n')} avg={t.get('avg_ret')} pf={t.get('profit_factor')} win={t.get('win_rate')}")
    print("market:", market, "| stocks:", len(data), "| price date:", price_date, "| stale:", out["stale"])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="states", choices=["full", "states"]); ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--years", type=int, default=6); ap.add_argument("--cost", type=float, default=0.004)
    a = ap.parse_args(); run(a.mode, a.top, a.years, a.cost)
