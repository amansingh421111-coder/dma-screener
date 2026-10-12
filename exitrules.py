"""Stop-loss and target rules: one definition used by the backtest (exits.py) and by the live levels for your positions (screen.py).

Every rule is a price level for the stop and (optionally) one for the target, both measured from the entry price, plus a time limit.
  fix    fixed percentages: stop sp% below entry, target tp% above
  atr    volatility based: stop k x ATR below entry, target m x ATR above (ATR = average true range over 14 days, on the day before entry)
  chand  trailing on volatility: stop k x ATR below the highest close since entry (starts k x ATR below entry)
  trail  trailing on percent: stop t% below the highest close since entry (starts t% below entry)
  dma    44-day average: stop at the previous day's 44-DMA, never lower than cat% below entry; optional target tp%
Stops only move up: each day the stop is the higher of yesterday's stop and the rule's new level.
Day by day, in this order: a gap open at or below the stop sells at the open; a gap open at or above the target sells at the open;
the day's low touching the stop sells at the stop; the day's high touching the target sells at the target;
otherwise the trade is closed at the close of the last allowed day.
"""
import math
import numpy as np

COST = 0.004   # brokerage, taxes and slippage per round trip, as in the strategy library
HMAX = {"swing": 60, "short": 25}


def _r(fam, hold, **p):
    p = {k: v for k, v in p.items() if v is not None}
    rid = fam + "-" + "-".join(f"{k}{v:g}" for k, v in sorted(p.items())) + f"-h{hold}"
    return dict(id=rid, fam=fam, hold=hold, **p)


def grid(kind):
    R = []
    if kind == "swing":
        for sp in (5, 8, 12):
            for tp in (10, 15, 20, 30, None): R.append(_r("fix", 40, sp=sp, tp=tp))
        for k in (1.5, 2, 3):
            for m in (3, 5, None): R.append(_r("atr", 40, k=k, m=m))
        for hold in (40, 60):
            for k in (2, 3, 4): R.append(_r("chand", hold, k=k))
            for t in (8, 12, 15): R.append(_r("trail", hold, t=t))
            for cat in (8, 12):
                for tp in (20, None): R.append(_r("dma", hold, cat=cat, tp=tp))
    else:
        for sp in (4, 6, 8):
            for tp in (5, 8, 12, None): R.append(_r("fix", 15, sp=sp, tp=tp))
        for k in (1, 1.5, 2):
            for m in (2, 3, None): R.append(_r("atr", 15, k=k, m=m))
        for hold in (15, 25):
            for k in (1.5, 2, 3): R.append(_r("chand", hold, k=k))
            for t in (4, 6, 8): R.append(_r("trail", hold, t=t))
    return R


def library_rule(kind, sp, tp):
    return _r("fix", 40 if kind == "swing" else 15, sp=sp, tp=tp)["id"]


def label(r):
    """Plain description of a rule."""
    f, h = r["fam"], r["hold"]
    tg = lambda: f"target +{r['tp']:g}%" if r.get("tp") else "no fixed target"
    if f == "fix": s = f"Stop −{r['sp']:g}%, {tg()}"
    elif f == "atr": s = f"Stop {r['k']:g}× ATR below entry, " + (f"target {r['m']:g}× ATR above" if r.get("m") else "no fixed target")
    elif f == "chand": s = f"Trailing stop {r['k']:g}× ATR below the highest close, no fixed target"
    elif f == "trail": s = f"Trailing stop {r['t']:g}% below the highest close, no fixed target"
    else: s = f"Stop at the 44-DMA (never more than {r['cat']:g}% below entry), {tg()}"
    return s + f", sell after {h} trading days at the latest"


def atr14(h, l, c):
    """Average true range, Wilder smoothing over 14 days. NaN bars keep the previous value."""
    n = len(c); out = np.full(n, np.nan); a = np.nan; pc = np.nan
    for i in range(n):
        hi, lo, cl = h[i], l[i], c[i]
        if not (hi == hi and lo == lo and cl == cl): out[i] = a; continue
        tr = hi - lo if pc != pc else max(hi - lo, abs(hi - pc), abs(lo - pc))
        a = tr if a != a else a + (tr - a) / 14.0
        out[i] = a; pc = cl
    return out


def sma(c, n=44):
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        cs = np.cumsum(np.r_[0.0, np.nan_to_num(c, nan=0.0)]); bad = np.cumsum(np.r_[0, np.isnan(c).astype(int)])
        s = (cs[n:] - cs[:-n]) / n; ok = (bad[n:] - bad[:-n]) == 0
        out[n - 1:] = np.where(ok, s, np.nan)
    return out


def simulate(O, H, L, C, D, a, rule, upto=None, final=True):
    """Vectorised over N trades. O, H, L, C: (N, W) day by day from the entry day, divided by the entry price.
    D: (N, W) the 44-DMA of the PREVIOUS day, divided by the entry price. a: (N,) ATR on the day before entry / entry price.
    upto: number of days available (live positions); None = full windows.
    final: the last available bar is a finished day (after the close). During market hours its close is not used to move the stop.
    Returns ret (gross, as a fraction), k (exit day index or -1 if still open), why (0 stop, 1 target, 2 time, -1 open),
    stop (N,) the stop level for the NEXT day, tgt (N,)."""
    N, W = O.shape; hold = rule["hold"]; f = rule["fam"]; last = min(hold, W if upto is None else upto)
    inf = np.full(N, np.inf)
    if f == "fix": stop = np.full(N, 1 - rule["sp"] / 100.0); tgt = np.full(N, 1 + rule["tp"] / 100.0) if rule.get("tp") else inf
    elif f == "atr": stop = 1 - rule["k"] * a; tgt = 1 + rule["m"] * a if rule.get("m") else inf
    elif f == "chand": stop = 1 - rule["k"] * a; tgt = inf
    elif f == "trail": stop = np.full(N, 1 - rule["t"] / 100.0); tgt = inf
    else:
        stop = np.maximum(1 - rule["cat"] / 100.0, np.nan_to_num(D[:, 0], nan=-np.inf)); tgt = np.full(N, 1 + rule["tp"] / 100.0) if rule.get("tp") else inf
    stop = stop.astype(float).copy(); tgt = np.asarray(tgt, float)
    ret = np.zeros(N); kx = np.full(N, -1); why = np.full(N, -1); alive = np.ones(N, bool); mx = np.full(N, -np.inf)
    for k in range(last):
        if k > 0:   # move the stop with what was known at yesterday's close
            mx = np.fmax(mx, C[:, k - 1])
            if f == "chand": new = mx - rule["k"] * a
            elif f == "trail": new = mx * (1 - rule["t"] / 100.0)
            elif f == "dma": new = np.nan_to_num(D[:, k], nan=-np.inf)
            else: new = None
            if new is not None: stop = np.where(alive, np.maximum(stop, new), stop)
        o, h, l, c = O[:, k], H[:, k], L[:, k], C[:, k]
        gs = alive & (o <= stop); gt = alive & ~gs & (o >= tgt)
        ls = alive & ~gs & ~gt & (l <= stop); ht = alive & ~gs & ~gt & ~ls & (h >= tgt)
        tm = alive & ~gs & ~gt & ~ls & ~ht & (k == hold - 1)
        for m_, px, w in ((gs, o, 0), (gt, o, 1), (ls, stop, 0), (ht, tgt, 1), (tm, c, 2)):
            if m_.any(): ret[m_] = px[m_] - 1; kx[m_] = k; why[m_] = w; alive &= ~m_
        if not alive.any(): break
    if upto is not None and final and alive.any() and last > 0:   # live, after the close: tomorrow's stop includes today's close
        mx = np.fmax(mx, C[:, last - 1])
        if f == "chand": stop = np.where(alive, np.maximum(stop, mx - rule["k"] * a), stop)
        elif f == "trail": stop = np.where(alive, np.maximum(stop, mx * (1 - rule["t"] / 100.0)), stop)
        elif f == "dma" and last < D.shape[1]: stop = np.where(alive, np.maximum(stop, np.nan_to_num(D[:, last], nan=-np.inf)), stop)
    return ret, kx, why, stop, tgt


def live_levels(dates, o, h, l, c, entry_date, entry_price, rule, final=True):
    """Levels for one open position from its daily bars (oldest first). entry_date 'YYYY-MM-DD', entry_price = your average cost.
    final: False during market hours (the last bar is still forming).
    Returns dict(sl, target, days_held, days_left, exit, atr) where exit is None or dict(date, price, why)."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c)); n = len(c)
    if n < 15 or not entry_price or entry_price <= 0: return None
    A = atr14(h, l, c); M = sma(c, 44)
    ei = next((i for i, d in enumerate(dates) if d >= entry_date), None)
    ep = float(entry_price)
    if ei is None:   # bought after the last bar: only the starting levels
        a = A[-1] / ep
        if not a == a: return None
        z = np.ones((1, 1)); s0 = np.array([[M[-1] / ep]])
        _, _, _, stop, tgt = simulate(z, z * np.inf, z * np.inf, z, s0, np.array([a]), rule, upto=0)
        return dict(sl=round(float(stop[0]) * ep, 2), target=None if not np.isfinite(tgt[0]) else round(float(tgt[0]) * ep, 2), days_held=0, days_left=rule["hold"], exit=None, atr=round(float(A[-1]), 2))
    s = max(ei - 1, 0); a = A[s] / ep
    if not a == a: return None
    W = n - ei; dprev = np.r_[M[s] if ei >= 1 else np.nan, M[ei:n - 1]] if W > 0 else np.array([])
    dprev = np.r_[dprev, M[n - 1]]   # last element: today's DMA, used for tomorrow's stop
    O, H_, L_, C_ = (np.array([x[ei:n] / ep]) for x in (o, h, l, c))
    D = np.array([dprev / ep])
    # a missing bar (NaN) never triggers anything: every comparison with NaN is false
    ret, kx, why, stop, tgt = simulate(O, H_, L_, C_, D, np.array([a]), rule, upto=W, final=final)
    out = dict(sl=round(float(stop[0]) * ep, 2), target=None if not np.isfinite(tgt[0]) else round(float(tgt[0]) * ep, 2),
               days_held=int(W), days_left=max(0, rule["hold"] - int(W)), exit=None, atr=round(float(A[s]), 2))
    if kx[0] >= 0:
        out["exit"] = dict(date=str(dates[ei + kx[0]]), price=round(float(ret[0] + 1) * ep, 2), why=["stop", "target", "time"][int(why[0])])
    return out
