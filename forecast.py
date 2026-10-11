"""Outlook for the next 1 and 3 months, estimated from history and tested on years it did not see.

python forecast.py              downloads prices (Yahoo) and writes forecast.json
python forecast.py --synthetic  same arithmetic on made-up prices (offline smoke test; the output is meaningless)

Two estimates, both mechanical (no opinion goes into them):

1. Nifty 50 range ("analogs"). Today is described by 14 numbers: trend (price vs its 200-day average and that average's slope),
   momentum (1, 3, 6 months), distance from the 52-week high, India VIX and its change, breadth (share of stocks above their
   200- and 50-day averages), the S&P 500's trend, and 3-month changes in Brent crude, the rupee and the US 10-year yield.
   The past days most like today on those numbers are found (each at least 10 trading days apart, so one episode counts once),
   and what the Nifty did in the 21 and 63 trading days after each of them is the estimate: a median, a range and the share that rose.
   Only days whose outcome was already known at the time are used, so the test below is a fair one.

2. Sector ranking. For each sector (equal-weighted index of the covered stocks, Yahoo sector names) a ridge regression on
   relative momentum (1, 3, 6 months), breadth inside the sector, and the sector's sensitivity to crude, the rupee and US yields
   times how much those moved in the last 3 months. Refit every month on past data only.

Settings (which inputs, how many analogs, how much shrinkage) are chosen on 2011-2018 and the track record is reported on 2019 onwards.
Live news, results and policy events are shown on the page next to these numbers but are not inside them: they cannot be tested on history.
"""
import argparse, datetime as dt, json, logging
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("fc")
H = (21, 63)
SPLIT = "2019-01-01"
QS = (0.10, 0.25, 0.50, 0.75, 0.90)
GAP = 10

FEAT = {   # key: (label, unit shown on the page)
    "vs200": ("Nifty vs its 200-day average", "pct"),
    "s200": ("Slope of the 200-day average (20 days)", "pct"),
    "m1": ("Nifty, last 1 month", "pct"),
    "m3": ("Nifty, last 3 months", "pct"),
    "m6": ("Nifty, last 6 months", "pct"),
    "dd52": ("Below the 52-week high", "pct"),
    "vix": ("India VIX", "lvl"),
    "vixc": ("India VIX, change over 1 month", "lvl"),
    "b200": ("Stocks above their 200-day average", "share"),
    "b50": ("Stocks above their 50-day average", "share"),
    "spx": ("S&P 500 (US) vs its 200-day average", "pct"),
    "brent3": ("Brent crude, last 3 months", "pct"),
    "inr3": ("US dollar in rupees, last 3 months", "pct"),
    "tnx3": ("US 10-year yield, change over 3 months", "bp"),
}
SETS = {"price": ["vs200", "s200", "m1", "m3", "m6", "dd52"]}
SETS["price+mood"] = SETS["price"] + ["vix", "vixc", "b200", "b50"]
SETS["all"] = SETS["price+mood"] + ["spx", "brent3", "inr3", "tnx3"]
KS = (25, 40, 60)

SFEAT = {
    "r1": "Last month vs the Nifty", "r3": "Last 3 months vs the Nifty", "r6": "Last 6 months vs the Nifty",
    "b200": "Share of its stocks above the 200-day average", "crude": "Crude oil: sensitivity x 3-month move",
    "inr": "Rupee: sensitivity x 3-month move", "rate": "US yields: sensitivity x 3-month move",
}
ALPHAS = (0.01, 0.1, 1.0)


# ---------------- data ----------------
def download():
    import insights as I
    fund = json.loads((ROOT / "fund.json").read_text())
    sec = {s: o.get("sec") for s, o in fund.get("fund", {}).items() if o.get("sec")}
    mk = ["^NSEI", "^INDIAVIX", "^GSPC", "BZ=F", "INR=X", "^TNX"]
    M = I.yfdl(mk, "max")
    px = I.yfdl([s + ".NS" for s in sec], "20y")
    stocks = {s: px[s + ".NS"]["Close"] for s in sec if s + ".NS" in px}
    log.info("market series %d/%d, stocks %d/%d", len(M), len(mk), len(stocks), len(sec))
    return {k: v["Close"] for k, v in M.items()}, stocks, sec, fund


def synthetic():
    rng = np.random.default_rng(7)
    d = pd.bdate_range("2006-01-02", "2026-10-09")
    walk = lambda mu, sd, s0: pd.Series(s0 * np.exp(np.cumsum(rng.normal(mu, sd, len(d)))), index=d)
    nifty = walk(0.0004, 0.012, 3000)
    M = {"^NSEI": nifty, "^INDIAVIX": pd.Series(np.clip(18 + np.cumsum(rng.normal(0, .6, len(d))) * .1, 9, 60), index=d),
         "^GSPC": walk(.0003, .011, 1200), "BZ=F": walk(0, .02, 60), "INR=X": walk(.0001, .004, 45), "^TNX": pd.Series(3 + np.cumsum(rng.normal(0, .03, len(d))) * .2, index=d)}
    secs = ["Technology", "Energy", "Healthcare", "Industrials", "Financial Services", "Utilities", "Real Estate", "Basic Materials"]
    stocks, sec = {}, {}
    for i in range(240):
        s = f"S{i:03d}"; start = int(rng.integers(0, 1500))
        stocks[s] = walk(.0004, .02, 100).iloc[start:] * (nifty.iloc[start:] / nifty.iloc[start]) ** .7
        sec[s] = secs[i % len(secs)]
    return M, stocks, sec, {"fund": {}}


# ---------------- helpers ----------------
sma = lambda s, n: s.rolling(n, min_periods=n).mean()


def on(idx, s):
    """a series on the Nifty's trading days, carried forward over other markets' holidays"""
    s = s[~s.index.duplicated()].sort_index()
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)


def rank(a):
    return pd.Series(a).rank().to_numpy()


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float); m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 4: return np.nan
    ra, rb = rank(a[m]), rank(b[m])
    return float(np.corrcoef(ra, rb)[0, 1]) if ra.std() > 0 and rb.std() > 0 else np.nan


def pinball(qv, a):
    return float(sum(max(q * (a - f), (q - 1) * (a - f)) for q, f in zip(QS, qv)))


def rnd(x, n=4):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


# ---------------- 1. Nifty analogs ----------------
def market_frame(M, stocks):
    c = M["^NSEI"].dropna(); c = c[~c.index.duplicated()]; idx = c.index
    m200 = sma(c, 200)
    F = pd.DataFrame(index=idx)
    F["vs200"] = c / m200 - 1
    F["s200"] = m200 / m200.shift(20) - 1
    for k, n in (("m1", 21), ("m3", 63), ("m6", 126)): F[k] = c / c.shift(n) - 1
    F["dd52"] = c / c.rolling(252, min_periods=200).max() - 1
    if "^INDIAVIX" in M:
        v = on(idx, M["^INDIAVIX"]); F["vix"] = v; F["vixc"] = v - v.shift(21)
    # breadth from the covered stocks (each counted once it has 200 days of history)
    C = pd.DataFrame({s: on(idx, x.dropna()) .where(lambda y: y.index >= x.dropna().index[0]) for s, x in stocks.items() if len(x.dropna()) > 250})
    has = C.rolling(200, min_periods=200).count() >= 200
    a200 = (C > C.rolling(200, min_periods=200).mean()).astype(float).where(has)
    a50 = (C > C.rolling(50, min_periods=50).mean()).astype(float).where(has)
    n = a200.notna().sum(axis=1).astype(float).replace(0, np.nan)
    F["b200"] = (a200.sum(axis=1) / n).where(n >= 100)
    F["b50"] = (a50.sum(axis=1) / n).where(n >= 100)
    if "^GSPC" in M: g = on(idx, M["^GSPC"]); F["spx"] = g / sma(g, 200) - 1
    if "BZ=F" in M: b = on(idx, M["BZ=F"]); F["brent3"] = b / b.shift(63) - 1
    if "INR=X" in M: r = on(idx, M["INR=X"]); F["inr3"] = r / r.shift(63) - 1
    if "^TNX" in M: t = on(idx, M["^TNX"]); F["tnx3"] = (t - t.shift(63)) * 100
    Y = pd.DataFrame({h: c.shift(-h) / c - 1 for h in H}, index=idx)
    return c, F, Y, n, C


def analogs(X, y, i, h, K):
    """indices of the K past days most like day i whose h-day outcome was known on day i (each >= GAP days apart)"""
    e = i - h                      # outcome of day j is known on day j + h, so j < i - h + 1
    if e < 300: return None
    hist = X[:i]; mu, sd = np.nanmean(hist, 0), np.nanstd(hist, 0); sd[sd == 0] = 1
    Z = (X[:e] - mu) / sd; z = (X[i] - mu) / sd
    d = np.sqrt(np.nansum((Z - z) ** 2, 1)); d[~np.isfinite(y[:e])] = np.inf
    blocked = np.zeros(e, bool); out = []
    for j in np.argsort(d):
        if not np.isfinite(d[j]): break
        if blocked[j]: continue
        out.append(j); blocked[max(0, j - GAP + 1): j + GAP] = True
        if len(out) == K: break
    return np.array(out) if len(out) >= min(K, 15) else None


def dist(v):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    q = np.quantile(v, QS)
    return dict(q=[rnd(x) for x in q], pup=rnd((v > 0).mean(), 3), pdn5=rnd((v < -0.05).mean(), 3), pup5=rnd((v > 0.05).mean(), 3), n=int(len(v)))


def walk_market(F, Y, cols, K, h, step=5):
    X = F[cols].to_numpy(float); y = Y[h].to_numpy(float); dates = F.index
    ok = np.isfinite(X).all(1)
    first = int(np.argmax(ok)); rows = []
    for i in range(first + 756, len(X) - h, step):
        if not ok[i]: continue
        sub = np.where(ok[:i])[0]
        Xs = X[sub]; ys = y[sub]; ii = len(sub)
        Xs = np.vstack([Xs, X[i]])
        # positions in "sub" index: outcome known only if original index + h < i
        known = sub + h < i
        ys = np.where(known, ys, np.nan)
        pk = analogs(Xs, np.append(ys, np.nan), ii, 0, K)
        if pk is None: continue
        v = ys[pk]; base = ys[np.isfinite(ys)]
        qv, qb = np.quantile(v, QS), np.quantile(base, QS)
        rows.append(dict(d=dates[i], a=y[i], q=qv, qb=qb, pup=(v > 0).mean(), pb=(base > 0).mean()))
    return rows


def score(rows):
    if not rows: return None
    a = np.array([r["a"] for r in rows]); pup = np.array([r["pup"] for r in rows]); pb = np.array([r["pb"] for r in rows])
    Lm = np.mean([pinball(r["q"], r["a"]) for r in rows]); Lb = np.mean([pinball(r["qb"], r["a"]) for r in rows])
    up = (a > 0).astype(float); bm, bb = np.mean((pup - up) ** 2), np.mean((pb - up) ** 2)
    q10 = np.array([r["q"][0] for r in rows]); q90 = np.array([r["q"][4] for r in rows]); q25 = np.array([r["q"][1] for r in rows]); q75 = np.array([r["q"][3] for r in rows])
    q50 = np.array([r["q"][2] for r in rows])
    cal = []
    for lo, hi in ((0, .45), (.45, .55), (.55, .65), (.65, .75), (.75, 1.01)):
        m = (pup >= lo) & (pup < hi)
        if m.sum() >= 5: cal.append(dict(lo=lo, hi=min(hi, 1), pred=rnd(pup[m].mean(), 3), act=rnd(up[m].mean(), 3), n=int(m.sum())))
    return dict(n=len(rows), start=str(rows[0]["d"].date()), end=str(rows[-1]["d"].date()),
                skill=rnd(1 - Lm / Lb, 4), brier=rnd(bm, 4), brier_base=rnd(bb, 4), bskill=rnd(1 - bm / bb, 4),
                cover80=rnd(((a >= q10) & (a <= q90)).mean(), 3), cover50=rnd(((a >= q25) & (a <= q75)).mean(), 3),
                hit=rnd((np.sign(q50) == np.sign(a)).mean(), 3), hit_always_up=rnd(up.mean(), 3), ic=rnd(spearman(q50, a), 3), cal=cal)


def market(F, Y):
    best, table = {}, []
    for name, cols in SETS.items():
        cols = [c for c in cols if c in F]
        for K in KS:
            res = {}
            for h in H:
                rows = walk_market(F, Y, cols, K, h)
                tr = [r for r in rows if str(r["d"].date()) < SPLIT]; te = [r for r in rows if str(r["d"].date()) >= SPLIT]
                res[h] = (score(tr), score(te), te)
            sel = np.mean([res[h][0]["skill"] for h in H if res[h][0]])
            table.append(dict(set=name, k=K, sel_skill=rnd(sel, 4), test={str(h): dict(skill=res[h][1]["skill"], bskill=res[h][1]["bskill"], cover80=res[h][1]["cover80"]) for h in H if res[h][1]}))
            log.info("variant %-10s K=%d  choose-on-2011-18 skill %+.4f   2019+: %s", name, K, sel, {h: res[h][1] and res[h][1]["skill"] for h in H})
            if not best or sel > best["sel"]: best = dict(sel=sel, set=name, cols=cols, k=K, res=res)
    return best, table


def today_market(c, F, Y, cols, K):
    X = F[cols].to_numpy(float); ok = np.isfinite(X).all(1)
    i = len(X) - 1
    while i > 0 and not ok[i]: i -= 1
    sub = np.where(ok[:i])[0]; Xs = np.vstack([X[sub], X[i]]); out = {}
    for h in H:
        ys = np.where(sub + h < i, Y[h].to_numpy(float)[sub], np.nan)
        pk = analogs(Xs, np.append(ys, np.nan), len(sub), 0, K)
        v = ys[pk]; base = ys[np.isfinite(ys)]
        last = float(c.iloc[i])
        o = dist(v); o["base"] = dist(base); o["level"] = [rnd(last * (1 + q), 0) for q in o["q"]]
        o["analogs"] = sorted([dict(d=str(F.index[sub[j]].date()), r=rnd(ys[j])) for j in pk], key=lambda x: x["d"])
        out[str(h)] = o
    return F.index[i], float(c.iloc[i]), out


def drivers(F, Y, asof):
    out = []
    for k, (lab, unit) in FEAT.items():
        if k not in F: continue
        s = F[k]; v = s.loc[asof]
        if not np.isfinite(v): continue
        hist = s.loc[:asof].dropna()
        pr = float((hist < v).mean())
        qs = np.quantile(hist, [0, .2, .4, .6, .8, 1]); b = int(np.clip(np.searchsorted(qs, v, side="right") - 1, 0, 4))
        lo, hi = qs[b], qs[b + 1]
        o = dict(k=k, label=lab, unit=unit, v=rnd(v, 5), pct=rnd(pr, 3), band=b, lo=rnd(lo, 5), hi=rnd(hi, 5), h={})
        for h in H:
            y = Y[h]; known = y.index <= y.index[max(0, y.index.get_loc(asof) - h)]
            m = (s >= lo) & (s <= hi) & known & y.notna(); allm = known & y.notna() & s.notna()
            # is the difference beyond noise? h-day returns overlap, so compare non-overlapping samples (one every h days),
            # averaging Welch's t over several starting offsets so the answer does not hang on one choice of days
            ts = []
            pos_all = np.flatnonzero(allm.to_numpy())
            for off in range(0, h, max(1, h // 5)):
                take = pos_all[off::h]; inb = m.to_numpy()[take]; yy = y.to_numpy()[take]
                a_, b_ = yy[inb], yy[~inb]
                if len(a_) >= 8 and len(b_) >= 8:
                    se = np.sqrt(a_.var(ddof=1) / len(a_) + b_.var(ddof=1) / len(b_))
                    if se > 0: ts.append((a_.mean() - b_.mean()) / se)
            t = float(np.mean(ts)) if ts else None
            o["h"][str(h)] = dict(med=rnd(y[m].median()), mean=rnd(y[m].mean()), pup=rnd((y[m] > 0).mean(), 3), n=int(m.sum()), n_indep=int(m.sum() // h),
                                  med_all=rnd(y[allm].median()), mean_all=rnd(y[allm].mean()), pup_all=rnd((y[allm] > 0).mean(), 3), t=rnd(t, 2))
        out.append(o)
    return out


# ---------------- 2. sectors ----------------
def sector_frame(c, M, stocks, sec, C):
    idx = c.index
    R = C.pct_change(fill_method=None).clip(-0.2, 0.2)
    groups = {}
    for s, g in sec.items():
        if s in R: groups.setdefault(g, []).append(s)
    groups = {g: L for g, L in groups.items() if len(L) >= 8}
    nret = c.pct_change()
    SI, B = {}, {}
    above = (C > C.rolling(200, min_periods=200).mean()).astype(float).where(C.rolling(200, min_periods=200).count() >= 200)
    for g, L in groups.items():
        r = R[L]; cnt = r.notna().sum(axis=1)
        SI[g] = np.log1p(r.mean(axis=1).fillna(0)).cumsum().where(cnt >= 5)
        a = above[L]; na = a.notna().sum(axis=1); B[g] = (a.sum(axis=1) / na).where(na >= 5)
    SI = pd.DataFrame(SI); B = pd.DataFrame(B); LN = np.log(c)
    rel = lambda k: SI.sub(SI.shift(k)).sub(LN - LN.shift(k), axis=0)
    feats = {"r1": rel(21), "r3": rel(63), "r6": rel(126), "b200": B.sub(B.mean(axis=1), axis=0)}
    # sensitivity to crude, the rupee and US yields: 3-year rolling beta of weekly relative returns
    wk = idx[::5]; srel = SI.reindex(wk).diff().sub(LN.reindex(wk).diff(), axis=0)
    mac = {"crude": ("BZ=F", "log"), "inr": ("INR=X", "log"), "rate": ("^TNX", "diff")}
    betas = {}
    for k, (t, kind) in mac.items():
        if t not in M: continue
        m = on(idx, M[t])
        mw = (np.log(m.reindex(wk)).diff() if kind == "log" else m.reindex(wk).diff())
        cov = srel.apply(lambda col: col.rolling(156, min_periods=104).cov(mw)); var = mw.rolling(156, min_periods=104).var()
        bt = cov.div(var, axis=0).reindex(idx).ffill()
        move = (np.log(m / m.shift(63)) if kind == "log" else (m - m.shift(63)))
        feats[k] = bt.mul(move, axis=0); betas[k] = bt
    Y = {h: SI.shift(-h).sub(SI).sub(LN.shift(-h) - LN, axis=0) for h in H}
    return SI, B, feats, Y, betas, groups


def panel(feats, Y, h, dates):
    keys = list(feats)
    rows = []
    for d in dates:
        X = np.column_stack([feats[k].loc[d].to_numpy(float) for k in keys]); y = Y[h].loc[d].to_numpy(float)
        rows.append((d, X, y))
    return keys, rows


def ridge_fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1; Z = (X - mu) / sd; ym = y.mean()
    w = np.linalg.solve(Z.T @ Z + alpha * len(Z) * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return mu, sd, ym, w


def walk_sectors(feats, Y, h, alpha, step=5, refit=21):
    idx = Y[h].index; keys = list(feats)
    good = pd.concat([feats[k].notna().all(axis=1) for k in keys], axis=1).all(axis=1)
    dates = idx[good.to_numpy()][::step]
    keys, rows = panel(feats, Y, h, dates)
    pos = {d: idx.get_loc(d) for d in dates}
    out, model, last_fit = [], None, -999
    for n, (d, X, y) in enumerate(rows):
        i = pos[d]
        if model is None or i - last_fit >= refit:
            tr = [(X2, y2) for d2, X2, y2 in rows[:n] if pos[d2] + h < i]
            if len(tr) < 150: continue
            XX = np.vstack([a for a, _ in tr]); yy = np.concatenate([b for _, b in tr]); m = np.isfinite(XX).all(1) & np.isfinite(yy)
            if m.sum() < 1000: continue
            model = ridge_fit(XX[m], yy[m], alpha); last_fit = i
        if not np.isfinite(y).all() or not np.isfinite(X).all(): continue
        mu, sd, ym, w = model; p = ym + ((X - mu) / sd) @ w
        out.append(dict(d=d, p=p, y=y, mom=X[:, keys.index("r3")]))
    return out


def sscore(rows, h):
    if not rows: return None
    ic = np.array([spearman(r["p"], r["y"]) for r in rows]); icm = np.array([spearman(r["mom"], r["y"]) for r in rows])
    spread = []
    for r in rows:
        o = np.argsort(r["p"]); spread.append(r["y"][o[-3:]].mean() - r["y"][o[:3]].mean())
    spread = np.array(spread)
    nono = ic[:: max(1, h // 5)]; nono = nono[np.isfinite(nono)]
    t = float(nono.mean() / (nono.std(ddof=1) / np.sqrt(len(nono)))) if len(nono) > 3 and nono.std() > 0 else None
    return dict(n=len(rows), start=str(rows[0]["d"].date()), end=str(rows[-1]["d"].date()), ic=rnd(np.nanmean(ic), 3), ic_pos=rnd(np.nanmean(ic > 0), 3), t=rnd(t, 2),
                ic_mom=rnd(np.nanmean(icm), 3), spread=rnd(spread.mean()), spread_hit=rnd((spread > 0).mean(), 3), n_indep=int(len(nono)))


def sectors(c, M, stocks, sec, C, fund):
    SI, B, feats, Y, betas, groups = sector_frame(c, M, stocks, sec, C)
    keys = list(feats); res = {}
    for h in H:
        best = None
        for al in ALPHAS:
            rows = walk_sectors(feats, Y, h, al)
            tr = [r for r in rows if str(r["d"].date()) < SPLIT]; te = [r for r in rows if str(r["d"].date()) >= SPLIT]
            s_tr, s_te = sscore(tr, h), sscore(te, h)
            log.info("sectors h=%d alpha=%.2f  2011-18 IC %s   2019+ IC %s (momentum alone %s)", h, al, s_tr and s_tr["ic"], s_te and s_te["ic"], s_te and s_te["ic_mom"])
            if s_tr and (best is None or (s_tr["ic"] or -9) > (best["sel"] or -9)): best = dict(sel=s_tr["ic"], alpha=al, test=s_te, train=s_tr)
        res[h] = best
    # today's estimate: fit on everything whose outcome is known
    idx = c.index; good = pd.concat([feats[k].notna().all(axis=1) for k in keys], axis=1).all(axis=1)
    asof = idx[good.to_numpy()][-1]; i = idx.get_loc(asof)
    out = {g: dict(name=g, n=len(L)) for g, L in groups.items()}
    for h in H:
        dates = idx[good.to_numpy()][::5]; dates = [d for d in dates if idx.get_loc(d) + h < i]
        _, rows = panel(feats, Y, h, dates)
        XX = np.vstack([x for _, x, _ in rows]); yy = np.concatenate([y for _, _, y in rows]); m = np.isfinite(XX).all(1) & np.isfinite(yy)
        mu, sd, ym, w = ridge_fit(XX[m], yy[m], res[h]["alpha"])
        resid = yy[m] - (ym + ((XX[m] - mu) / sd) @ w); rq = np.quantile(resid, [0.1, 0.9])
        X0 = np.column_stack([feats[k].loc[asof].to_numpy(float) for k in keys]); Z0 = (X0 - mu) / sd; p = ym + Z0 @ w
        for j, g in enumerate(SI.columns):
            out[g][str(h)] = dict(p=rnd(p[j]), lo=rnd(p[j] + rq[0]), hi=rnd(p[j] + rq[1]), c={k: rnd(Z0[j, n_] * w[n_]) for n_, k in enumerate(keys)})
        res[h]["coef"] = {k: rnd(w[n_]) for n_, k in enumerate(keys)}
    F = fund.get("fund", {})
    for j, g in enumerate(SI.columns):
        o = out[g]
        o["now"] = {k: rnd(feats[k].loc[asof, g]) for k in ("r1", "r3", "r6")}
        o["now"]["b200"] = rnd(B.loc[asof, g], 3)
        o["beta"] = {k: rnd(betas[k].loc[asof, g], 3) for k in betas}
        L = [F[s] for s in groups[g] if s in F]
        qg = []
        for f in L:
            q = [x for x in (f.get("q") or []) if x.get("ni") is not None]
            if len(q) >= 2:
                lastq = q[-1]; d0 = dt.date.fromisoformat(lastq["d"])
                prev = [x for x in q[:-1] if 330 <= (d0 - dt.date.fromisoformat(x["d"])).days <= 400]
                if prev and prev[-1]["ni"] and prev[-1]["ni"] > 0: qg.append(lastq["ni"] / prev[-1]["ni"] - 1)
        mdn = lambda v: rnd(float(np.median(v)), 4) if len(v) >= 3 else None
        o["results"] = dict(n=len(qg), profit_g=mdn(qg), profit_up=rnd(np.mean([x > 0 for x in qg]), 3) if len(qg) >= 3 else None,
                            rev_g=mdn([f["revg"] for f in L if f.get("revg") is not None]), pe=mdn([f["pe"] for f in L if f.get("pe") and f["pe"] > 0]))
    secs = sorted(out.values(), key=lambda o: -(o.get("21", {}).get("p") or 0))
    track = {str(h): dict(alpha=res[h]["alpha"], train=res[h]["train"], test=res[h]["test"], coef=res[h]["coef"]) for h in H}
    return str(asof.date()), secs, track


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--synthetic", action="store_true"); ap.add_argument("--out", default="forecast.json"); a = ap.parse_args()
    M, stocks, sec, fund = synthetic() if a.synthetic else download()
    c, F, Y, nb, C = market_frame(M, stocks)
    best, table = market(F, Y)
    asof, last, now = today_market(c, F, Y, best["cols"], best["k"])
    track = {}
    for h in H:
        tr, te, rows = best["res"][h]
        track[str(h)] = dict(train=tr, test=te, series=[dict(d=str(r["d"].date()), a=rnd(r["a"]), q=[rnd(x) for x in r["q"]]) for r in rows])
    sasof, secs, strack = sectors(c, M, stocks, sec, C, fund)
    out = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), synthetic=bool(a.synthetic), split=SPLIT,
               nifty=dict(asof=str(asof.date()), last=rnd(last, 2), set=best["set"], k=best["k"], inputs=best["cols"], h=now, track=track, variants=table,
                          breadth_n=int(nb.fillna(0).iloc[-1]), first=str(F[best["cols"]].dropna().index[0].date())),
               drivers=drivers(F, Y, asof), feat={k: dict(label=v[0], unit=v[1]) for k, v in FEAT.items()},
               sectors=dict(asof=sasof, list=secs, track=strack, feat=SFEAT))
    (ROOT / a.out).write_text(json.dumps(out, separators=(",", ":"), default=str, allow_nan=False))
    for h in H:
        t = track[str(h)]["test"]; o = now[str(h)]
        print(f"::notice::Nifty {h}d ({best['set']}, K={best['k']}): median {o['q'][2]:+.2%}, 10-90% {o['q'][0]:+.2%}..{o['q'][4]:+.2%}, up {o['pup']:.0%} (all history {o['base']['pup']:.0%}) | 2019+ test: skill {t['skill']}, Brier skill {t['bskill']}, 80% band held {t['cover80']}, hit {t['hit']} vs always-up {t['hit_always_up']}")
        s = strack[str(h)]["test"]
        print(f"::notice::Sectors {h}d alpha={strack[str(h)]['alpha']}: 2019+ IC {s and s['ic']} (t {s and s['t']}, momentum alone {s and s['ic_mom']}), top3-bottom3 {s and s['spread']} hit {s and s['spread_hit']}")
    print("::notice::Sector estimate 21d: " + ", ".join(f"{o['name']} {o['21']['p']:+.1%}" for o in secs))
    print("::notice::Variants: " + " | ".join(f"{v['set']}/{v['k']}: sel {v['sel_skill']} test {v['test']}" for v in table))


if __name__ == "__main__":
    main()
