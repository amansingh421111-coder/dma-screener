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
GRID = {"swing": [(s, t) for s in (5, 8, 12) for t in (10, 15, 20, 30)], "short": [(s, t) for s in (4, 6) for t in (5, 8, 12)]}
MOMSIG = {}   # filled by run(): cross-sectional momentum signals per stock

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


def adx_di(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(mdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False).mean(); adx.iloc[:2 * n] = np.nan
    return adx, pdi, mdi
def s_minervini(df):
    c = df["Close"]; m50, m150, m200 = sma(c, 50), sma(c, 150), sma(c, 200)
    hi, lo = c.rolling(252).max(), c.rolling(252).min()
    return first((c > m150) & (c > m200) & (m150 > m200) & (m200 > m200.shift(21)) & (m50 > m150) & (m50 > m200) & (c > m50) & (c >= 1.3 * lo) & (c >= 0.75 * hi))
def s_holygrail(df):
    adx, pdi, mdi = adx_di(df); m20 = sma(df["Close"], 20)
    return (adx > 30) & (adx > adx.shift(1)) & (pdi > mdi) & (df["Low"] <= m20) & (df["Close"] > m20)
def s_pocket(df):
    c, v = df["Close"], df["Volume"]; down_v = v.where(c < c.shift(1))
    mx = down_v.shift(1).rolling(10, min_periods=1).max(); m50 = sma(c, 50)
    return (c > c.shift(1)) & (v > mx) & (c > m50) & (c <= m50 * 1.10)
def s_turtle55(df):
    h, c = df["High"], df["Close"]; return first(c > h.shift(1).rolling(55).max())
def s_ibs(df):
    h, l, c = df["High"], df["Low"], df["Close"]; ibs = (c - l) / (h - l).replace(0, np.nan)
    return (ibs <= 0.2) & (c > sma(c, 200))
def s_mom6(df): return MOMSIG.get(df.attrs.get("key"), pd.Series(False, index=df.index)).reindex(df.index, fill_value=False)

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
    dict(id="minervini", name="Minervini Trend Template", kind="swing", fn=s_minervini, rule="First day all seven hold: close above the 150- and 200-day averages; 150-day above 200-day; 200-day higher than a month ago; 50-day above both; close above the 50-day; at least 30% above the 52-week low; within 25% of the 52-week high."),
    dict(id="holygrail", name="Holy Grail (ADX pullback)", kind="swing", fn=s_holygrail, rule="14-day ADX above 30 and rising with +DI above -DI; the day's low touches the 20-day average and the close finishes above it."),
    dict(id="pocketpivot", name="Pocket pivot", kind="swing", fn=s_pocket, rule="Up day whose volume is higher than the highest volume of any down day in the previous 10 sessions; close above the 50-day average but no more than 10% above it (the 10% limit is this app's numeric stand-in for 'not extended')."),
    dict(id="turtle55", name="55-day breakout (Turtle System 2)", kind="swing", fn=s_turtle55, rule="First close above the highest high of the previous 55 days."),
    dict(id="mom6", name="6-month momentum leaders (monthly)", kind="swing", fn=s_mom6, rule="On the first trading day of each month: the stock is in the top 10% of the list by 6-month return and above its 200-day average."),
    dict(id="ibs", name="Internal bar strength dip", kind="short", fn=s_ibs, rule="Close in the lowest 20% of the day's range (IBS 0.2 or lower) while above the 200-day average."),
]

FAMILY = {
 "dma44_cross": "Trend",
 "dma44_zone": "Trend",
 "dma44_pull": "Pullback",
 "ma_cross": "Trend",
 "pull50": "Pullback",
 "breakout": "Breakout",
 "base": "Breakout",
 "donchian": "Breakout",
 "momentum": "Momentum",
 "squeeze": "Breakout",
 "nr7": "Breakout",
 "gapup": "Breakout",
 "surge": "Breakout",
 "supertrend": "Trend",
 "macd": "Pullback",
 "oversold": "Mean reversion",
 "rsi2": "Mean reversion",
 "bolldip": "Mean reversion",
 "reversal": "Mean reversion",
 "minervini": "Trend",
 "holygrail": "Pullback",
 "pocketpivot": "Breakout",
 "turtle55": "Breakout",
 "ibs": "Mean reversion",
 "mom6": "Momentum"
}
SOURCES = {
 "minervini": {
  "name": "Mark Minervini's Trend Template (7 price rules, no relative-strength rule)",
  "url": "https://prorealcode.com/prorealtime-market-screeners/trend-template-mark-minervini"
 },
 "holygrail": {
  "name": "Linda Raschke and Larry Connors, 'Holy Grail' setup",
  "url": "https://tradingsetupsreview.com/the-holy-grail-trading-setup"
 },
 "pocketpivot": {
  "name": "Gil Morales and Chris Kacher, pocket pivot (Trade Like an O'Neil Disciple)",
  "url": "https://www.luxalgo.com/library/concept/pocket-pivot/"
 },
 "turtle55": {
  "name": "Turtle trading, System 2 entry (55-day breakout)",
  "url": "https://www.kotakneo.com/investing-guide/articles/turtle-trading-strategy-explained-rules/"
 },
 "donchian": {
  "name": "Turtle trading, System 1 entry (20-day breakout)",
  "url": "https://www.kotakneo.com/investing-guide/articles/turtle-trading-strategy-explained-rules/"
 },
 "ibs": {
  "name": "Internal Bar Strength (IBS) mean reversion; 0.2 or lower treated as oversold",
  "url": "https://in.tradingview.com/script/Ay41FF7e-SHORT-ONLY-Internal-Bar-Strength-IBS-Mean-Reversion-Strategy"
 },
 "mom6": {
  "name": "Momentum profits in Indian stocks: SPJIMR student research paper published on the NSE site (CNX 100, 2003-2011, 6-month formation)",
  "url": "https://nsearchives.nseindia.com/research/content/RP_2_Feb2012.pdf"
 }
}
SOURCES["mom6"]["note"] = "A student research project (not peer-reviewed); it reports momentum profits that peaked around 6 months and faded by 12, before trading costs."
for _k in ("minervini", "holygrail", "pocketpivot", "turtle55", "donchian"): SOURCES[_k]["note"] = "The published method uses its own exits and position rules; this app tests only the entry rule with a stop, target and time limit."

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

def stats(tr, base_tr=None):
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
    if base_tr:
        br = np.array([t["ret"] for t in base_tr]); e = float(r.mean() - br.mean()); se = float(np.sqrt(r.var(ddof=1) / len(r) + br.var(ddof=1) / len(br))) if len(r) > 1 and len(br) > 1 else None
        d["baseline"] = round(float(br.mean()), 4); d["baseline_n"] = len(br); d["edge"] = round(e, 4); d["t"] = None if not se else round(e / se, 2)
    return d

def rate(train, test):
    """Score out of 5 from fixed arithmetic (no judgement calls). The main measure is the EDGE: average profit per trade minus what entering the
    same stocks on random days earned with the SAME stop, target and time limit in the same period. Without that, a rising market makes every strategy look good.
    Returns (stars, label, parts) where parts lists every point awarded."""
    if not test or test["n"] < 60: return 0.0, "unproven", [["Fewer than 60 trades in the later period: no score", 0]]
    parts = []; a = test["avg_ret"]; e = test.get("edge", 0) or 0; pf = test["profit_factor"] or 0
    def add(label, pts): parts.append([label, pts])
    add("Edge over random entries with the same stop, target and time limit (later period): 2.5 points at +1.5% or more, 2 at +0.8%, 1.5 at +0.4%, 1 at +0.1%, 0.5 above 0", 2.5 if e >= 0.015 else 2.0 if e >= 0.008 else 1.5 if e >= 0.004 else 1.0 if e >= 0.001 else 0.5 if e > 0 else 0)
    add("Average profit per trade after costs is above zero: 0.5 point", 0.5 if a > 0 else 0)
    add("Profit factor (money won / money lost): 0.5 point at 1.3 or more, 0.25 at 1.15", 0.5 if pf >= 1.3 else 0.25 if pf >= 1.15 else 0)
    add("Number of trades: 0.5 point at 300 or more, 0.25 at 150", 0.5 if test["n"] >= 300 else 0.25 if test["n"] >= 150 else 0)
    add("Edge over random entries was also positive in the earlier period: 0.5 point", 0.5 if train and (train.get("edge", 0) or 0) > 0 else 0)
    add("Profitable in at least 75% of calendar years of the later period: 0.5 point", 0.5 if test["years_n"] >= 2 and test["years_pos"] / test["years_n"] >= 0.75 else 0)
    pts = sum(x[1] for x in parts); t = test.get("t")
    if e <= 0 and pts > 1.0: add("Cap: with no edge over random entries the score cannot exceed 1", 1.0 - pts); pts = 1.0
    elif (t is None or t < 1) and pts > 1.5: add("Cap: edge is within normal luck (confidence t below 1): score cannot exceed 1.5", 1.5 - pts); pts = 1.5
    elif (t is None or t < 2) and pts > 2.5: add("Cap: edge not yet statistically solid (confidence t below 2): score cannot exceed 2.5", 2.5 - pts); pts = 2.5
    stars = round(min(5.0, pts) * 2) / 2
    return stars, ("reliable" if stars >= 3.5 else "mixed" if stars >= 2.5 else "unreliable"), parts


def _m(x): return float(np.mean([t["ret"] for t in x]))
def _edge(a, b, mn=30):
    if len(a) < mn or len(b) < mn: return None
    return _m(a) - _m(b)

def compute_robust(tr_by_g, bt_by_g, g, split, order, nsyms, cost):
    """Eight extra checks on one strategy. Every check is a fixed rule with a printed number; none is a judgement call."""
    ST, BT = tr_by_g[g], bt_by_g[g]
    test = [t for t in ST if t["entry"] >= split]; btest = [t for t in BT if t["entry"] >= split]
    out = {}
    # 1. walk-forward: for each year, pick the stop/target using only earlier years, then trade that year
    years = sorted({t["entry"][:4] for t in ST + BT})
    wf_a, wf_b, wf_years = [], [], []
    for y in years:
        if years.index(y) < 2: continue
        cut = f"{y}-01-01"; best = None
        for gg in tr_by_g:
            a = [t for t in tr_by_g[gg] if t["entry"] < cut]; b = [t for t in bt_by_g[gg] if t["entry"] < cut]
            e = _edge(a, b, 60)
            if e is not None and (best is None or e > best[0]): best = (e, gg)
        if not best: continue
        gg = best[1]; a = [t for t in tr_by_g[gg] if t["entry"][:4] == y]; b = [t for t in bt_by_g[gg] if t["entry"][:4] == y]
        wf_a += a; wf_b += b
        wf_years.append(dict(year=y, stop=gg[0], target=gg[1], n=len(a), edge=None if _edge(a, b, 20) is None else round(_edge(a, b, 20), 4)))
    wf = stats(wf_a, wf_b) if len(wf_a) >= 30 and len(wf_b) >= 30 else None
    out["walk_forward"] = dict(stats=wf, years=wf_years)
    # 2. calendar years with the chosen stop/target
    yrs = []
    for y in years:
        a = [t for t in ST if t["entry"][:4] == y]; b = [t for t in BT if t["entry"][:4] == y]
        e = _edge(a, b, 30)
        yrs.append(dict(year=y, n=len(a), avg=round(_m(a), 4) if a else None, base=round(_m(b), 4) if b else None, edge=None if e is None else round(e, 4)))
    out["years"] = yrs
    # 3. every stop/target combination on the later period
    sens = []
    for gg in tr_by_g:
        a = [t for t in tr_by_g[gg] if t["entry"] >= split]; b = [t for t in bt_by_g[gg] if t["entry"] >= split]
        st = stats(a, b) if a and b else None
        sens.append(dict(stop=gg[0], target=gg[1], n=len(a), avg=None if not st else st["avg_ret"], edge=None if not st else st["edge"], t=None if not st else st.get("t")))
    out["sensitivity"] = sens
    # 4. costs
    base_avg = _m(test) if test else None
    out["costs"] = [dict(cost=c, avg=None if base_avg is None else round(base_avg + cost - c, 4)) for c in (0.0, 0.002, 0.004, 0.008, 0.012)]
    # 5. two random halves of the stock list, and 6. three liquidity groups
    half = lambda t: sum(map(ord, t["sym"])) % 2
    out["halves"] = []
    for h, nm in ((0, "Stock group A"), (1, "Stock group B")):
        a = [t for t in test if half(t) == h]; b = [t for t in btest if half(t) == h]; e = _edge(a, b)
        out["halves"].append(dict(name=nm, n=len(a), edge=None if e is None else round(e, 4)))
    grp = lambda t: min(2, int(3 * order.get(t["sym"], 0) / max(1, nsyms)))
    out["liquidity"] = []
    for k, nm in enumerate(("Most traded third", "Middle third", "Least traded third")):
        a = [t for t in test if grp(t) == k]; b = [t for t in btest if grp(t) == k]; e = _edge(a, b)
        out["liquidity"].append(dict(name=nm, n=len(a), edge=None if e is None else round(e, 4)))
    # 7. month-by-month t: stocks that signal on the same day are not independent, so judge by monthly averages
    months = sorted({t["entry"][:7] for t in test})
    d = []
    for mo in months:
        a = [t for t in test if t["entry"][:7] == mo]; b = [t for t in btest if t["entry"][:7] == mo]
        if len(a) >= 5 and len(b) >= 5: d.append(_m(a) - _m(b))
    mt = None if len(d) < 6 or np.std(d, ddof=1) == 0 else float(np.mean(d) / (np.std(d, ddof=1) / np.sqrt(len(d))))
    out["month"] = dict(months=len(d), t=None if mt is None else round(mt, 2), positive=int(sum(1 for x in d if x > 0)))
    # 8. bootstrap interval of the edge
    ra = np.array([t["ret"] for t in test]); rb = np.array([t["ret"] for t in btest]); lo = hi = None
    if len(ra) >= 30 and len(rb) >= 30:
        rng = np.random.default_rng(7)
        bs = [ra[rng.integers(0, len(ra), len(ra))].mean() - rb[rng.integers(0, len(rb), len(rb))].mean() for _ in range(400)]
        lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
    out["bootstrap"] = dict(lo=None if lo is None else round(lo, 4), hi=None if hi is None else round(hi, 4))
    # the eight pass/fail rules
    ys = [y for y in yrs if y["edge"] is not None]; yp = sum(1 for y in ys if y["edge"] > 0)
    sp = [x for x in sens if x["edge"] is not None]; sg = sum(1 for x in sp if x["edge"] > 0)
    hv = [x for x in out["halves"] if x["edge"] is not None]; lq = [x for x in out["liquidity"] if x["edge"] is not None]
    fmt = lambda v: "n/a" if v is None else f"{v*100:+.2f}%"
    ck = [
      dict(id="wf", label="Walk-forward: picking the stop and target each year from earlier years only, the edge is positive and t is 2 or more", ok=bool(wf and wf["edge"] > 0 and (wf.get("t") or 0) >= 2), detail="not enough years" if not wf else f"edge {fmt(wf['edge'])}, t {wf.get('t')}, {wf['n']} trades"),
      dict(id="years", label="The edge is positive in at least two thirds of the calendar years that have 30 or more trades (and at least 3 such years)", ok=bool(len(ys) >= 3 and yp / len(ys) >= 2 / 3), detail=f"{yp} of {len(ys)} years positive"),
      dict(id="sens", label="The edge is positive for at least 70% of all stop and target combinations tried (later period)", ok=bool(sp and sg / len(sp) >= 0.7), detail=f"{sg} of {len(sp)} combinations positive"),
      dict(id="halves", label="The edge is positive in both random halves of the stock list", ok=bool(len(hv) == 2 and all(x["edge"] > 0 for x in hv)), detail=", ".join(f"{x['name']} {fmt(x['edge'])}" for x in hv) or "n/a"),
      dict(id="liq", label="The edge is positive in at least two of three liquidity groups (most, middle, least traded)", ok=bool(len(lq) >= 2 and sum(1 for x in lq if x["edge"] > 0) >= 2), detail=", ".join(f"{x['name']} {fmt(x['edge'])}" for x in lq) or "n/a"),
      dict(id="month", label="Judged by monthly averages (stocks signalling on the same day are not independent), t is 2 or more", ok=bool(mt is not None and mt >= 2), detail="n/a" if mt is None else f"t {mt:.2f} over {len(d)} months, {out['month']['positive']} positive"),
      dict(id="boot", label="Resampling the trades 400 times, the lower end of the 95% range of the edge is above zero", ok=bool(lo is not None and lo > 0), detail="n/a" if lo is None else f"95% range {fmt(lo)} to {fmt(hi)}"),
      dict(id="cost", label="Still profitable on average if costs are doubled to 0.8% per trade", ok=bool(base_avg is not None and base_avg + cost - 0.008 > 0), detail="n/a" if base_avg is None else f"average {fmt(base_avg + cost - 0.008)} per trade at 0.8% costs"),
    ]
    out["checks"] = ck; out["passed"] = sum(1 for c in ck if c["ok"]); out["total"] = len(ck)
    return out

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

FWD_CAP = 10        # at most this many signals per strategy per day are followed (the most traded stocks first)
FWD_CTRL = 10       # random stocks followed per day for every stop/target combination, as the control group

def _resolve(df, sig, stop, target, hold, cost):
    """Replays one signal from its signal day: buy at the next open, then stop / target / time limit. Returns ('done', trade), ('open', None) or ('wait', None)."""
    ts = pd.Timestamp(sig); pos = df.index.searchsorted(ts)
    if pos >= len(df) or df.index[pos] != ts: return "lost", None
    sub = df.iloc[pos:]
    if len(sub) < 2: return "wait", None
    en = pd.Series(False, index=sub.index); en.iloc[0] = True
    tr, op = simulate(sub, en, stop, target, hold, cost)
    if tr: return "done", tr[0]
    return ("open", None) if op else ("wait", None)

def update_forward(data, strategies, todays, price_date, order_idx, cost=0.004):
    """Live record. Every day the signals of every strategy are logged and followed to their real outcome with the same rules as the backtest,
    next to a control group of random stocks with the same stop, target and time limit. Nothing here is tuned: it is a plain diary."""
    import random
    path = ROOT / "forward.json"
    try: F = json.loads(path.read_text())
    except Exception: F = {}
    F.setdefault("since", price_date); F.setdefault("agg", {}); F.setdefault("ctrl", {}); F.setdefault("open", [])
    by = {s["id"]: s for s in strategies}
    combos = {}
    for s in strategies: combos[f"{s['params']['stop']}/{s['params']['target']}/{s['params']['max_hold']}"] = (s["params"]["stop"], s["params"]["target"], s["params"]["max_hold"])
    if F.get("last_sig") != price_date:
        for sid, t in todays.items():
            if sid not in by: continue
            sig = sorted(t.get("buy", []), key=lambda x: order_idx.get(x["s"], 9999))[:FWD_CAP]
            F["open"] += [["s:" + sid, x["s"], price_date] for x in sig]
        keys = sorted(data)
        for cb in combos:
            rnd = random.Random(f"{price_date}|{cb}")
            F["open"] += [["c:" + cb, k[:-3], price_date] for k in rnd.sample(keys, min(FWD_CTRL, len(keys)))]
        F["last_sig"] = price_date
    keep = []; today = pd.Timestamp(price_date)
    for tag, sym, sig in F["open"]:
        df = data.get(sym + ".NS")
        if df is None: continue
        if tag.startswith("s:"):
            sx = by.get(tag[2:]); 
            if not sx: continue
            stop, tgt, hold = sx["params"]["stop"], sx["params"]["target"], sx["params"]["max_hold"]; grp, key = F["agg"], tag[2:]
        else:
            stop, tgt, hold = combos.get(tag[2:], (None, None, None))
            if stop is None: continue
            grp, key = F["ctrl"], tag[2:]
        st, tr = _resolve(df, sig, stop, tgt, hold, cost)
        if st == "done":
            b = grp.setdefault(key, {})
            for k, v in (("n", 0), ("sum", 0.0), ("sumsq", 0.0), ("win", 0), ("target", 0), ("stop", 0), ("time", 0)): b.setdefault(k, v)
            b["n"] += 1; b["sum"] = round(b["sum"] + tr["ret"], 6); b["sumsq"] = round(b["sumsq"] + tr["ret"] ** 2, 6); b["win"] += 1 if tr["ret"] > 0 else 0; b[tr["why"]] += 1
            b["last"] = tr["exit"]; b.setdefault("first", sig)
        elif (today - pd.Timestamp(sig)).days <= 100 and st != "lost": keep.append([tag, sym, sig])
    F["open"] = keep; F["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(); F["price_date"] = price_date
    F["note"] = f"Up to {FWD_CAP} signals per strategy per day (most traded stocks first) and {FWD_CTRL} random stocks per stop/target combination per day are followed. Trades pay {cost*100:.1f}% costs."
    path.write_text(json.dumps(F, separators=(",", ":")))
    return F

def run(mode, top, years, cost):
    old = {}
    try: old = json.loads((ROOT / "strategies.json").read_text())
    except Exception: pass
    if mode == "states" and not old.get("strategies"): mode = "full"
    syms, bhav_day = liquid_universe(top); order_idx = {x: i for i, x in enumerate(syms)}
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
    closes = pd.DataFrame({k: d["Close"] for k, d in data.items()}).sort_index().ffill(limit=5)
    rank = closes.pct_change(126, fill_method=None).rank(axis=1, pct=True)
    firstday = pd.Series(closes.index.to_period("M"), index=closes.index).ne(pd.Series(closes.index.to_period("M"), index=closes.index).shift(1)).to_numpy()
    MOMSIG.clear()
    for k, d in data.items():
        MOMSIG[k] = ((rank[k] >= 0.9) & firstday & (closes[k] > sma(closes[k], 200))).fillna(False)
    allt = {s["id"]: {g: [] for g in GRID[s["kind"]]} for s in STRATS}; daily = []
    allb = {k: {g: [] for g in GRID[k]} for k in GRID}   # random-entry control trades: same exits, entry every 5th day
    states = {k: ["-"] * len(STRATS) for k in data}; todays = {s["id"]: dict(buy=[], hold=0, exit=[]) for s in STRATS}; opens = {}
    for key, df in data.items():
        sym = key[:-3]
        df.attrs["key"] = key
        reg = nok.reindex(df.index, method="ffill").fillna(False).to_numpy(bool) if len(nok) else None
        if mode == "full":
            daily.append(df["Close"].pct_change().dropna())
            rnd = pd.Series(np.arange(len(df)) % 5 == 0, index=df.index)
            for k in GRID:
                for g in GRID[k]:
                    tr, _ = simulate(df, rnd, g[0], g[1], MAX_HOLD[k], cost, None)
                    allb[k][g] += [dict(t, sym=sym) for t in tr]
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
        out.update(years=years, cost_pct=round(cost * 100, 2), split=split, strategies=[])
        for s in STRATS:
            best = None; table = []
            inper = lambda x, lo, hi: [t for t in x if lo <= t["entry"] < hi]
            for g, tr in allt[s["id"]].items():
                train = [t for t in tr if t["entry"] < split]; test = [t for t in tr if t["entry"] >= split]
                a = stats(train, inper(allb[s["kind"]][g], "0000", split)); table.append(dict(stop=g[0], target=g[1], train_n=len(train), train_avg=None if not a else a["avg_ret"], train_edge=None if not a else a["edge"], train_pf=None if not a else a["profit_factor"]))
                if a and a["n"] >= 60 and (best is None or a["edge"] > best[0]): best = (a["edge"], g, train, test)
            if best is None:
                g = GRID[s["kind"]][0]; tr = allt[s["id"]][g]; best = (0, g, [t for t in tr if t["entry"] < split], [t for t in tr if t["entry"] >= split])
            _, g, train, test = best
            bk = allb[s["kind"]][g]; a, b = stats(train, inper(bk, "0000", split)), stats(test, inper(bk, split, "9999"))
            ups, dns = [t for t in test if t["up"]], [t for t in test if t["up"] is False]
            stars, verdict, parts = rate(a, b)
            out["strategies"].append(dict(id=s["id"], name=s["name"], rule=s["rule"], kind=s["kind"], params=dict(stop=g[0], target=g[1], max_hold=MAX_HOLD[s["kind"]]),
                                          exit=f"Sell at the target (+{g[1]}%), the stop loss (-{g[0]}%), or after {MAX_HOLD[s['kind']]} trading days, whichever comes first.",
                                          train=a, test=b, test_up=stats(ups), test_down=stats(dns), grid=table, robust=compute_robust(allt[s["id"]], allb[s["kind"]], g, split, order_idx, len(syms), cost), stars=stars, verdict=verdict, score_parts=parts, family=FAMILY.get(s["id"], "Other"), source=SOURCES.get(s["id"])))
    for s in out.get("strategies", []):
        t = todays.get(s["id"], {}); p = s["params"]
        buys = sorted(t.get("buy", []), key=lambda x: x["s"])
        s["today"] = dict(buy=[dict(x, stop=round(x["c"] * (1 - p["stop"] / 100), 2), target=round(x["c"] * (1 + p["target"] / 100), 2)) for x in buys[:60]], buy_n=len(buys),
                          exit=sorted(t.get("exit", []))[:40] if mode == "states" else s.get("today", {}).get("exit", []), hold_n=t.get("hold", 0) if mode == "states" else s.get("today", {}).get("hold_n", 0))
    out["caveats"] = ["A signal is bought at the next day's open; every trade pays 0.4% round-trip costs; the stop is assumed to hit first if a day touches both stop and target.",
                      "The stop and target for each strategy were chosen on the earlier 60% of the history (by edge over random entries) and judged on the later 40% only.",
                      "Past results do not predict the future. Testing many strategies means some will look good by luck: trust the ones with many trades, a clear edge and profits in most years.",
                      "Edge means average profit per trade minus the average of trades entered on random days in the same stocks with exactly the same stop, target and time limit. In a rising market most strategies show a profit that is mostly the market itself; the edge is the part the entry rule added.",
                      "The stock list is today's liquid stocks, so stocks that were delisted are missing and results look better than real life would have been.",
                      "News, results announcements and company events are not part of the test."]
    (ROOT / "strategies.json").write_text(json.dumps(out, separators=(",", ":")))
    if mode == "states" and out.get("strategies"):
        F = update_forward(data, out["strategies"], todays, price_date, order_idx, cost)
        print("forward log: open", len(F["open"]), "| strategies with finished trades:", sum(1 for v in F["agg"].values() if v.get("n")))
    for s in out.get("strategies", []):
        t = s["test"] or {}; print(f"{s['name']:40s} {s['stars']:3.1f}* {s['verdict']:10s} stop {s['params']['stop']} tgt {s['params']['target']} test n={t.get('n')} avg={t.get('avg_ret')} pf={t.get('profit_factor')} win={t.get('win_rate')}")
    print("market:", market, "| stocks:", len(data), "| price date:", price_date, "| stale:", out["stale"])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="states", choices=["full", "states"]); ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--years", type=int, default=6); ap.add_argument("--cost", type=float, default=0.004)
    a = ap.parse_args(); run(a.mode, a.top, a.years, a.cost)
