"""Share-level outlook for the next 1 and 3 months, plus seasonal (calendar-month) patterns, tested on years the model did not see.

python stock_outlook.py              downloads prices and writes stock_outlook.json
python stock_outlook.py --synthetic  offline smoke test (made-up prices; the output is meaningless)

Universe: NSE shares in the equity list (no ETFs), about 20 years of adjusted daily prices. On each date only shares at ₹20+ that
traded at least ₹50 lakh a day (20-day median) take part, so the past is not picked with today's turnover.

What is estimated: each share's return over the next 21 and 63 trading days AGAINST THE AVERAGE SHARE that day (the median of all
eligible shares), so the market's own move is taken out. Inputs, each ranked across shares on the day (so one extreme number cannot dominate):
  r1    last month's return (short-term reversal)
  r3    last 3 months' return
  r6x   6-month return, skipping the last month (momentum)
  r12x  12-month return, skipping the last month (momentum)
  vs200 distance from the 200-day average
  hi52  distance from the 52-week high
  vol   3-month volatility of daily returns
  seas  seasonality: how the share did against the average share over the same calendar window in each of the last 10 years
  sec   its sector's 3-month return
A ridge regression on these, refitted every month on past data only. Settings are fixed in advance; 2019 onwards is reported as the test.

Seasonality tables: for every share, each calendar month's average return, how often it rose, and how it did against the Nifty 50.
"""
import argparse, datetime as dt, json, logging, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("so")
H = (21, 63)
SPLIT = "2019-01-01"
STEP = 5                     # a cross-section every 5 trading days
REFIT = 4                    # refit every 4 cross-sections (about a month)
MIN_PX, MIN_VAL = 20.0, 5e6
FEATS = ["r1", "r3", "r6x", "r12x", "vs200", "hi52", "vol", "seas", "sec"]
LABEL = {"r1": "Last month's move", "r3": "Last 3 months' move", "r6x": "6-month momentum (skipping the last month)",
         "r12x": "12-month momentum (skipping the last month)", "vs200": "Distance from the 200-day average", "hi52": "Distance from the 52-week high",
         "vol": "Volatility (3 months)", "seas": "Seasonality: same weeks in past years", "sec": "Its sector's last 3 months"}
SEAS_MIN = 5                 # a calendar month needs at least 5 years before its average is shown
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def rnd(x, n=4):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


# ---------------- data ----------------
def download(years):
    import dma44_deep as DD, insights as I
    nse, _, day = DD.universes(2600, 0)
    data, _ = DD.fetch_all(nse, [], years)
    if len(data) < int(os.environ.get("SX_MIN", 400)): raise SystemExit("too few stocks downloaded; not updating")
    nifty = I.yfdl(["^NSEI"], "max").get("^NSEI")
    sec = {}
    try:
        F = json.loads((ROOT / "fund.json").read_text()).get("fund", {}); sec = {s: o.get("sec") for s, o in F.items() if o.get("sec")}
    except Exception: pass
    try:
        for s, v in json.loads((ROOT / "names.json").read_text()).items():
            if isinstance(v, list) and len(v) > 3 and v[3] and s not in sec: sec[s] = v[3]
    except Exception: pass
    return {k.split(":", 1)[1]: d for k, d in data.items()}, (nifty["Close"] if nifty is not None else None), sec


def synthetic():
    rng = np.random.default_rng(5); d = pd.bdate_range("2006-01-02", "2026-10-09"); data = {}
    mkt = np.cumsum(rng.normal(0.0004, 0.011, len(d)))
    for i in range(300):
        st = int(rng.integers(0, 2000)); c = 100 * np.exp(0.8 * mkt + np.cumsum(rng.normal(0.0002, 0.02, len(d))))
        df = pd.DataFrame(dict(Open=c, High=c * 1.01, Low=c * 0.99, Close=c, Volume=np.full(len(d), 2e5)), index=d).iloc[st:]
        data[f"S{i:03d}"] = df
    secs = ["Technology", "Energy", "Healthcare", "Industrials", "Financial Services", "Utilities"]
    return data, pd.Series(10000 * np.exp(mkt), index=d), {s: secs[i % 6] for i, s in enumerate(data)}


# ---------------- arrays ----------------
def build(data, sec):
    syms = sorted(data)
    C = pd.DataFrame({s: data[s]["Close"] for s in syms}).sort_index()
    C = C[~C.index.duplicated()]
    V = pd.DataFrame({s: data[s]["Volume"] for s in syms}).reindex(C.index)
    dates = C.index
    R = C.pct_change(fill_method=None)
    bad = ((R < -0.30) | (R > 0.45)).astype(float)                     # unadjusted corporate action or bad data
    val = (C * V).rolling(20, min_periods=15).median()
    elig = (C >= MIN_PX) & (val >= MIN_VAL)
    f = {}
    f["r1"] = C / C.shift(21) - 1
    f["r3"] = C / C.shift(63) - 1
    f["r6x"] = C.shift(21) / C.shift(126) - 1
    f["r12x"] = C.shift(21) / C.shift(252) - 1
    f["vs200"] = C / C.rolling(200, min_periods=200).mean() - 1
    f["hi52"] = C / C.rolling(252, min_periods=200).max() - 1
    f["vol"] = R.rolling(63, min_periods=50).std()
    badpast = bad.rolling(252, min_periods=1).max()                    # a bad print in the last year spoils the momentum inputs
    for k in ("r3", "r6x", "r12x", "vs200", "hi52"): f[k] = f[k].where(badpast < 1)
    # target: forward return against the median eligible share that day (winsorised), invalid if a bad print falls inside the window
    E = {}
    for h in H:
        fw = C.shift(-h) / C - 1
        badf = bad[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1)
        fw = fw.where((badf < 1) & elig)
        lo, hi = fw.quantile(0.01, axis=1), fw.quantile(0.99, axis=1)
        fw = fw.clip(lo, hi, axis=0)
        E[h] = fw.sub(fw.median(axis=1), axis=0)
    # seasonality: mean of the same-window excess return in each of the last 10 years (needs 5)
    pos = pd.Series(np.arange(len(dates)), index=dates)
    for h in H:
        acc = np.zeros(C.shape); cnt = np.zeros(C.shape); Ev = E[h].to_numpy()
        for k in range(1, 11):
            back = dates - pd.DateOffset(years=k)
            j = pos.reindex(back, method="pad").to_numpy()             # last trading day on or before the same date k years ago
            ok = ~np.isnan(j); jj = np.where(ok, j, 0).astype(int)
            x = Ev[jj]; x[~ok] = np.nan
            m = np.isfinite(x); acc[m] += x[m]; cnt[m] += 1
        f[f"seas{h}"] = pd.DataFrame(np.where(cnt >= 5, acc / np.maximum(cnt, 1), np.nan), index=dates, columns=C.columns)
        f[f"seasn{h}"] = pd.DataFrame(cnt, index=dates, columns=C.columns)
    # sector 3-month return (equal weight of eligible members)
    secs = pd.Series({s: sec.get(s) for s in syms})
    sr = pd.DataFrame(np.nan, index=dates, columns=C.columns)
    r3e = f["r3"].where(elig)
    for g, members in secs.dropna().groupby(secs.dropna()).groups.items():
        L = list(members)
        if len(L) < 5: continue
        m = r3e[L].mean(axis=1).where(r3e[L].notna().sum(axis=1) >= 5)
        for s in L: sr[s] = m
    f["sec"] = sr
    return syms, dates, C, R, elig, f, E


def ranks(row, ok):
    """cross-sectional rank in [-0.5, 0.5] among eligible shares; missing -> 0 (the middle)"""
    out = np.zeros(len(row)); m = ok & np.isfinite(row)
    if m.sum() >= 20:
        r = pd.Series(row[m]).rank(pct=True).to_numpy() - 0.5
        out[m] = r
    return out


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 20: return np.nan
    ra, rb = pd.Series(a[m]).rank().to_numpy(), pd.Series(b[m]).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def xsec(f, E, elig, h, i):
    ok = elig.iloc[i].to_numpy(bool)
    cols = []
    for k in FEATS:
        src = f[f"seas{h}"] if k == "seas" else f[k]
        cols.append(ranks(src.iloc[i].to_numpy(float), ok))
    X = np.column_stack(cols + [np.ones(len(ok))])
    y = E[h].iloc[i].to_numpy(float) if E is not None else None
    return X, y, ok


def walk(f, E, elig, dates, h):
    first = 260
    idx = list(range(first, len(dates) - 1, STEP))
    XtX = np.zeros((len(FEATS) + 1,) * 2); Xty = np.zeros(len(FEATS) + 1); pend = []   # cross-sections waiting for their outcome
    lam = 1e-3; w = None; out = []
    raw = {k: [] for k in FEATS}
    for n, i in enumerate(idx):
        # add every past cross-section whose h-day outcome is known by day i
        while pend and pend[0][0] + h < i:
            _, Xp, yp = pend.pop(0); m = np.isfinite(yp)
            XtX += Xp[m].T @ Xp[m]; Xty += Xp[m].T @ yp[m]
        X, y, ok = xsec(f, E, elig, h, i)
        m = ok & np.isfinite(y)
        if n % REFIT == 0 and XtX[-1, -1] > 20000:
            w = np.linalg.solve(XtX + lam * XtX[-1, -1] * np.diag([1] * len(FEATS) + [0]), Xty)
        if w is not None and m.sum() >= 50:
            p = X @ w
            out.append(dict(d=dates[i], p=p[m], y=y[m]))
            for j, k in enumerate(FEATS): raw[k].append(spearman(X[m, j], y[m]))
        pend.append((i, X[ok], y[ok]))
    return out, raw, w


def score(rows, raw, h, test=True):
    sel = [n for n, r in enumerate(rows) if (str(r["d"].date()) >= SPLIT) == test]
    if not sel: return None
    ic = np.array([spearman(rows[n]["p"], rows[n]["y"]) for n in sel])
    sp = []
    for n in sel:
        p, y = rows[n]["p"], rows[n]["y"]; q = max(5, len(p) // 10); o = np.argsort(p)
        sp.append(y[o[-q:]].mean() - y[o[:q]].mean())
    # each decile of the estimate (1 = lowest, 10 = highest): average realised return against the average share, and how often it was positive
    D = np.full((len(sel), 10), np.nan)
    for r_, n in enumerate(sel):
        p, y = rows[n]["p"], rows[n]["y"]; rk = pd.Series(p).rank(pct=True).to_numpy(); dq = np.minimum(9, (rk * 10).astype(int))
        for d in range(10):
            m_ = dq == d
            if m_.sum() >= 5: D[r_, d] = y[m_].mean() - y.mean()          # against the average share that day
    stp = max(1, h // STEP); Dn = D[::stp]
    deciles = [dict(d=d + 1, mean=rnd(np.nanmean(D[:, d])), pos=rnd(np.nanmean(D[:, d] > 0), 3),
                    se=rnd(np.nanstd(Dn[:, d], ddof=1) / np.sqrt(np.isfinite(Dn[:, d]).sum()), 5)) for d in range(10)]
    sp = np.array(sp); step = max(1, h // STEP); ni = ic[::step]; ni = ni[np.isfinite(ni)]
    t = float(ni.mean() / (ni.std(ddof=1) / np.sqrt(len(ni)))) if len(ni) > 3 and ni.std() > 0 else None
    single, single_t = {}, {}
    for k in FEATS:
        v = np.array(raw[k])[sel]; single[k] = rnd(np.nanmean(v), 3); nv = v[::step]; nv = nv[np.isfinite(nv)]
        single_t[k] = rnd(float(nv.mean() / (nv.std(ddof=1) / np.sqrt(len(nv)))), 2) if len(nv) > 3 and nv.std() > 0 else None
    return dict(n=len(sel), start=str(rows[sel[0]]["d"].date()), end=str(rows[sel[-1]]["d"].date()), ic=rnd(np.nanmean(ic), 3), ic_pos=rnd(np.nanmean(ic > 0), 3),
                t=rnd(t, 2), spread=rnd(sp.mean()), spread_hit=rnd((sp > 0).mean(), 3), n_indep=int(len(ni)), single=single, single_t=single_t, deciles=deciles,
                stocks=int(np.median([len(rows[n]["p"]) for n in sel])))


# ---------------- seasonality tables ----------------
def month_table(close):
    m = close.resample("ME").last().pct_change(fill_method=None).dropna()
    m = m[m.index < pd.Timestamp.today().normalize().replace(day=1)]          # complete months only
    return m


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--synthetic", action="store_true"); ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--out", default="stock_outlook.json"); a = ap.parse_args()
    data, nifty, sec = synthetic() if a.synthetic else download(a.years)
    for k, d in data.items():
        if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
    log.info("shares: %d", len(data))
    syms, dates, C, R, elig, f, E = build(data, sec)
    track, coef, today = {}, {}, {}
    last = len(dates) - 1
    while last > 0 and elig.iloc[last].sum() < 50: last -= 1
    vol_now = f["vol"].iloc[last].to_numpy(float)
    for h in H:
        rows, raw, w = walk(f, E, elig, dates, h)
        track[str(h)] = dict(test=score(rows, raw, h, True), train=score(rows, raw, h, False))
        # final fit on everything whose outcome is known, then today's cross-section
        XtX = np.zeros((len(FEATS) + 1,) * 2); Xty = np.zeros(len(FEATS) + 1); resid = []
        for i in range(260, last - h, STEP):
            X, y, ok = xsec(f, E, elig, h, i); m = ok & np.isfinite(y)
            XtX += X[m].T @ X[m]; Xty += X[m].T @ y[m]
        w = np.linalg.solve(XtX + 1e-3 * XtX[-1, -1] * np.diag([1] * len(FEATS) + [0]), Xty)
        for i in range(260, last - h, STEP * 4):
            X, y, ok = xsec(f, E, elig, h, i); m = ok & np.isfinite(y)
            v = f["vol"].iloc[i].to_numpy(float)[m]; e = (y[m] - X[m] @ w) / (v * np.sqrt(h)); resid.append(e[np.isfinite(e)])
        rq = np.quantile(np.concatenate(resid), [0.1, 0.9])
        coef[str(h)] = {k: rnd(w[j], 5) for j, k in enumerate(FEATS)}
        X, _, ok = xsec(f, None, elig, h, last)
        if h == 21: X21 = X
        p = X @ w; pr = pd.Series(p[ok]).rank(pct=True).to_numpy(); pi = np.flatnonzero(ok)
        for n_, j in enumerate(pi):
            s = syms[j]; o = today.setdefault(s, {})
            sc = vol_now[j] * np.sqrt(h)
            o[str(h)] = dict(p=float(p[j]), pct=float(pr[n_]), lo=float(p[j] + rq[0] * sc), hi=float(p[j] + rq[1] * sc), c={k: float(X[j, q] * w[q]) for q, k in enumerate(FEATS)})
        log.info("h=%d test %s", h, track[str(h)]["test"])
    # seasonality: per share, per calendar month (complete years only), against the Nifty 50
    nm = month_table(nifty) if nifty is not None else None
    nifty_seas = []
    if nm is not None:
        for mi in range(12):
            v = nm[nm.index.month == mi + 1]
            o_ = nm[nm.index.month != mi + 1]; se = np.sqrt(v.var(ddof=1) / len(v) + o_.var(ddof=1) / len(o_)) if len(v) > 2 else np.nan
            nifty_seas.append(dict(m=MONTHS[mi], avg=rnd(v.mean()), med=rnd(v.median()), up=rnd((v > 0).mean(), 3), n=int(len(v)),
                                   t=rnd((v.mean() - o_.mean()) / se, 2) if se and np.isfinite(se) and se > 0 else None))
    out_s = {}
    for j, s in enumerate(syms):
        c = C[s].dropna()
        if len(c) < 260: continue
        mt = month_table(c)
        ex = mt - nm.reindex(mt.index) if nm is not None else mt * np.nan
        sm, su, sx, sb, sn, st = [], [], [], [], [], []
        for mi in range(12):
            v = mt[mt.index.month == mi + 1]; e = ex[ex.index.month == mi + 1].dropna()
            ok_ = (v > -0.6) & (v < 1.5); v = v[ok_]; e = e[(e > -0.6) & (e < 1.5)]                # a month beyond -60% / +150% is treated as bad data
            enough = len(e) >= SEAS_MIN
            sm.append(round(float(v.mean()) * 1000) if len(v) >= SEAS_MIN else None); su.append(round(float((v > 0).mean()) * 100) if len(v) >= SEAS_MIN else None)
            sx.append(round(float(e.mean()) * 1000) if enough else None); sb.append(round(float((e > 0).mean()) * 100) if enough else None); sn.append(int(len(e)))
            st.append(round(float(e.mean() / (e.std(ddof=1) / np.sqrt(len(e)))) * 10) if enough and e.std(ddof=1) > 0 else None)
        o = today.get(s, {})
        bp = lambda v: None if v is None or not np.isfinite(v) else int(round(v * 10000))    # basis points keep the file small
        row = dict(sm=sm, su=su, sx=sx, sb=sb, st=st, n=max(sn), sec=sec.get(s))
        if "21" in o and "63" in o:
            row["o"] = [bp(o["21"]["p"]), round(o["21"]["pct"] * 100), bp(o["21"]["lo"]), bp(o["21"]["hi"]), bp(o["63"]["p"]), round(o["63"]["pct"] * 100), bp(o["63"]["lo"]), bp(o["63"]["hi"])]
            row["c"] = [bp(o["21"]["c"][k]) for k in FEATS]; row["c3"] = [bp(o["63"]["c"][k]) for k in FEATS]
            row["x"] = [int(round((X21[j_, q] + 0.5) * 100)) for q in range(len(FEATS))] if (j_ := syms.index(s)) is not None else None   # percentile of each input today
            row["ss"] = [bp(f["seas21"].iloc[last, j]), bp(f["seas63"].iloc[last, j]), int(f["seasn21"].iloc[last, j])]
            r21 = (c / c.shift(21) - 1).tail(756).dropna(); r63 = (c / c.shift(63) - 1).tail(756).dropna()
            if len(r21) > 100: row["typ"] = [bp(r21.quantile(0.1)), bp(r21.quantile(0.9)), bp(r63.quantile(0.1)), bp(r63.quantile(0.9))]
        out_s[s] = row
    # sector seasonality, year by year: each sector's equal-weighted month return minus the average sector's that month,
    # then for each calendar month the mean over years and its t (years are independent draws)
    sec_seas, sec_t = {}, {}
    MR = C.resample("ME").last().pct_change(fill_method=None)
    MR = MR[MR.index < pd.Timestamp.today().normalize().replace(day=1)].where((MR > -0.6) & (MR < 1.5))
    gs = pd.Series({s_: sec.get(s_) for s_ in MR.columns}).dropna()
    SR = pd.DataFrame({g: MR[list(L)].mean(axis=1).where(MR[list(L)].notna().sum(axis=1) >= 8) for g, L in gs.groupby(gs).groups.items() if len(L) >= 8})
    if not SR.empty:
        D = SR.sub(SR.mean(axis=1), axis=0)
        for g in D.columns:
            av, tt = [], []
            for mi in range(12):
                v = D[g][D.index.month == mi + 1].dropna()
                if len(v) >= SEAS_MIN and v.std(ddof=1) > 0: av.append(rnd(v.mean())); tt.append(rnd(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))), 2))
                else: av.append(None); tt.append(None)
            sec_seas[g], sec_t[g] = av, tt
    fmt = dict(o="21-day estimate vs the average share, its percentile, low, high; then the same for 63 days (basis points, percent)",
               c="contributions of each input to the 21-day estimate (basis points, order of feats)", c3="the same for 63 days",
               sm="average return by calendar month (tenths of a percent)", su="share of years it rose (percent)", sx="average return against the Nifty 50 (tenths of a percent)",
               sb="share of years it beat the Nifty 50 (percent)", st="t of the average against the Nifty across years (x10); months with under 5 years are null", n="years of history", ss="seasonality input now: same 21 / 63 days in past years vs the average share (basis points), years used",
               x="percentile of each input today among eligible shares (0-100, order of feats; 50 = missing)", typ="its own 21-day and 63-day moves over the last 3 years: 10th and 90th percentile (basis points)")
    out = dict(fmt=fmt, updated=dt.datetime.now(dt.timezone.utc).isoformat(), asof=str(dates[last].date()), synthetic=bool(a.synthetic), split=SPLIT,
               shares=len(syms), eligible_today=int(elig.iloc[last].sum()), first=str(dates[0].date()), feats=FEATS, label=LABEL,
               track=track, coef=coef, nifty_seas=nifty_seas, sector_seas=sec_seas, sector_seas_t=sec_t, months=MONTHS, s=out_s)
    (ROOT / a.out).write_text(json.dumps(out, separators=(",", ":"), allow_nan=False))
    for h in H:
        t = track[str(h)]["test"] or {}; tr = track[str(h)]["train"] or {}
        print(f"::notice::shares {h}d: 2019+ IC {t.get('ic')} (t {t.get('t')}, positive {t.get('ic_pos')}), top-minus-bottom tenth {t.get('spread')} hit {t.get('spread_hit')}, ~{t.get('stocks')} shares | before 2019 IC {tr.get('ic')}")
        print(f"::notice::single inputs {h}d (2019+ IC): {t.get('single')} | coef {coef[str(h)]}")
    print(f"::notice::written {len(out_s)} shares, {sum(1 for r in out_s.values() if 'o' in r)} with an estimate; size {(ROOT / a.out).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
