"""Approaching shares: what history says about shares sitting 0-2% BELOW their 44-day average (the screener's "Approaching" list).

python approach.py                 downloads about 12 years of NSE prices and writes approach.json
python approach.py --synthetic 300 offline smoke test on made-up prices (the output is meaningless)

Every trading day since the data begins, each NSE share that met the screener's rules (price ₹50+, 20-day average volume 1 lakh+
shares) and closed 0-2% below its 44-DMA is one "approaching" case (at most one every 5 days per share, so a share sitting in the
zone for weeks is not counted many times). For each case, with a buy at the NEXT day's open (the list is known only after the close):
  crossed     did it close at or above its 44-DMA within the next 10 trading days, and after how many days
  r10, r20    return after 10 and 20 trading days, after 0.4% costs
  excess      r20 minus the median r20 of every eligible share bought on the same day (takes out the market's own move)
  best, worst the highest high and lowest low within 20 days
  wait        the alternative: wait for the close above the 44-DMA, buy at the next open, sell on the same day 20
What was known on the day (the inputs), each tested on its own in fifths (quintiles) and together in a model:
  dist (how far below the 44-DMA), slope (the 44-DMA's change over 10 days), vs200, rsi, volx (day's volume / 20-day average),
  v5 (5-day / 20-day volume), liq (median ₹ traded a day), r5, r21, r63, r126 (returns, the last three ranked against all shares
  that day: relative strength), fromhi (distance from the 52-week high), below (days since it was last above the 44-DMA),
  atr (daily range, % of price), clv (where it closed in the day's range), stars (the screener's 0-3 rating), breadth (share of all
  shares above their 200-DMA that day).
Model: a logistic regression for "crossed within 10 days" and a ridge regression for the 20-day excess return, on the inputs
turned into percentiles of the training cases. Refitted at the start of every year on cases whose 20 days had already finished;
tested on the following year only. The settings below are fixed in advance and were not tuned on the test years.
Today's list is scored with the latest fit. Each share's "similar cases" figures are the actual results of past TEST cases with
the same model rank (tenth), so they are not the model's own claim. Nothing here is a recommendation.
"""
import argparse, datetime as dt, json, logging, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("ap")
COST = 0.004; NEAR = 0.02; COOL = 5; HZ = 10; H = 20
MIN_PRICE = 50; MIN_VOL = 1e5
TEST_FROM = 2017; RIDGE = 30.0; L2 = 1.0
FEATS = ["dist", "slope", "vs200", "rsi", "volx", "v5", "liq", "r5", "r21", "r63", "r126", "fromhi", "below", "atr", "clv", "stars", "breadth"]
NAMES = {"dist": "Distance below the 44-DMA", "slope": "44-DMA direction (10-day change)", "vs200": "Price vs its 200-DMA", "rsi": "RSI (14 days)",
         "volx": "Day's volume vs its 20-day average", "v5": "5-day volume vs 20-day volume", "liq": "Liquidity (median ₹ traded a day)",
         "r5": "Last 5 days' return", "r21": "1-month return vs all shares", "r63": "3-month return vs all shares", "r126": "6-month return vs all shares",
         "fromhi": "Distance from the 52-week high", "below": "Days below the 44-DMA", "atr": "Daily price range (ATR, % of price)",
         "clv": "Where it closed in the day's range", "stars": "Screener rating (0-3 stars)", "breadth": "Market breadth (shares above their 200-DMA)"}


def rsi_w(c, n=14):
    d = np.diff(c, prepend=np.nan); up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    with np.errstate(divide="ignore", invalid="ignore"): return np.where(dn > 0, 100 - 100 / (1 + up / dn), 100.0)


def per_stock(df):
    """Feature and outcome columns for every day of one share (numpy arrays aligned with df.index)."""
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    n = len(c); S = lambda x, w: pd.Series(x).rolling(w).mean().to_numpy()
    ma = S(c, 44); m200 = S(c, 200); v20p = np.r_[np.nan, S(v, 20)[:-1]]   # previous 20 days, as the screener does
    v20 = S(v, 20); v5 = S(v, 5); tv = c * v / 1e7
    liq = pd.Series(tv).rolling(20, min_periods=10).median().to_numpy()
    pc = np.r_[np.nan, c[:-1]]; tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    hi = pd.Series(c).rolling(252, min_periods=120).max().to_numpy()
    sh = lambda x, k: np.r_[np.full(k, np.nan), x[:-k]]
    above = c >= ma; below = np.zeros(n)
    run = 0
    for i in range(n):
        run = 0 if (above[i] or np.isnan(ma[i])) else run + 1; below[i] = run
    rng = h - l; body = np.abs(c - o)
    with np.errstate(divide="ignore", invalid="ignore"):
        pos = np.where(rng > 0, (c - l) / rng, 0.5)
        lw = np.minimum(o, c) - l
        name_bull = (c > o) & ~((rng > 0) & (body / rng < 0.15))
        hammer = (lw >= 2 * body) & (pos >= 0.6) & (body > 0)
        volx = v / v20p
        stars = (name_bull | hammer).astype(int) + (pos >= 0.67).astype(int) + (volx >= 1.5).astype(int)
        F = dict(dist=c / ma - 1, slope=ma / sh(ma, 10) - 1, vs200=c / m200 - 1, rsi=rsi_w(c), volx=volx, v5=v5 / v20,
                 liq=np.log10(np.maximum(liq, 1e-3)), r5=c / sh(c, 5) - 1, r21=c / sh(c, 21) - 1, r63=c / sh(c, 63) - 1, r126=c / sh(c, 126) - 1,
                 fromhi=c / hi - 1, below=below, atr=atr / c, clv=pos, stars=stars.astype(float))
    ok = (c >= MIN_PRICE) & (v20 >= MIN_VOL) & np.isfinite(ma)
    # outcomes: buy at the next open
    def fwd(x, k): return np.r_[x[k:], np.full(k, np.nan)]
    e = fwd(o, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r10 = fwd(c, HZ) / e - 1 - COST; r20 = fwd(c, H) / e - 1 - COST
        W = np.lib.stride_tricks.sliding_window_view
        pad = lambda x: np.r_[x, np.full(H, np.nan)]
        hw = W(pad(h), H + 1)[:n, 1:]; lw_ = W(pad(l), H + 1)[:n, 1:]
        best = np.nanmax(np.where(np.isnan(hw), -np.inf, hw), axis=1) / e - 1
        worst = np.nanmin(np.where(np.isnan(lw_), np.inf, lw_), axis=1) / e - 1
        cw = W(pad(c), H + 1)[:n, 1:HZ + 1]; mw = W(pad(ma), H + 1)[:n, 1:HZ + 1]
        hit = cw >= mw; crossed = hit.any(axis=1); dcross = np.where(crossed, hit.argmax(axis=1) + 1, np.nan)
        # wait for the close above, buy at the next open, sell at the close of day 20
        ow = W(pad(o), H + 1)[:n, :]
        k = np.where(crossed, hit.argmax(axis=1) + 2, 0)
        ew = ow[np.arange(n), np.clip(k, 0, H)]
        rwait = np.where(crossed, fwd(c, H) / ew - 1 - COST, np.nan)
    done = np.r_[np.ones(max(n - H, 0), bool), np.zeros(min(H, n), bool)]
    return F, dict(r10=r10, r20=r20, best=best, worst=worst, crossed=crossed.astype(float), dcross=dcross, rwait=rwait), ok, done


def build(data):
    """One table of approaching cases (finished and today's), plus the same-day median 20-day return of every eligible share."""
    rows, allr, brd = [], [], []; MOM = {"r21": [], "r63": [], "r126": []}
    for key, df in data.items():
        df = df.dropna(subset=["Close"])
        if len(df) < 260: continue
        F, Y, ok, done = per_stock(df)
        d = df.index
        allr.append(pd.Series(np.where(ok, Y["r20"], np.nan), index=d, name=key))
        brd.append(pd.Series(np.where(ok & np.isfinite(F["vs200"]), (F["vs200"] > 0).astype(float), np.nan), index=d, name=key))
        for k in MOM: MOM[k].append(pd.Series(np.where(ok, F[k], np.nan), index=d, name=key))
        zone = ok & (F["dist"] >= -NEAR) & (F["dist"] < 0)
        idx = np.where(zone)[0]; keep = []; last = -10 ** 9
        for i in idx:
            if i - last >= COOL or i == len(df) - 1: keep.append(i); last = i
        if not keep: continue
        keep = np.array(keep)
        t = pd.DataFrame({k: F[k][keep] for k in F}, index=d[keep])
        for k in Y: t["y_" + k] = Y[k][keep]
        t["done"] = done[keep]; t["key"] = key; t["last"] = keep == len(df) - 1
        rows.append(t)
    ev = pd.concat(rows); ev.index.name = "date"; ev = ev.reset_index()
    med = pd.concat(allr, axis=1).median(axis=1)
    breadth = pd.concat(brd, axis=1).mean(axis=1)
    ev["mkt20"] = ev["date"].map(med); ev["y_excess"] = ev["y_r20"] - ev["mkt20"]
    ev["breadth"] = ev["date"].map(breadth)
    for k in ("r21", "r63", "r126"):   # relative strength: percentile among all eligible shares that day
        R = pd.concat(MOM[k], axis=1).rank(axis=1, pct=True)
        st = R.stack(); st.index.names = ["date", "key"]; st.name = k
        ev = ev.drop(columns=k).merge(st.reset_index(), on=["date", "key"], how="left")
    return ev


# ---- models on percentile inputs ----
def qmap(train, x, q=20):
    """Each input becomes its percentile among the training cases (in steps of 5%), centred on 0."""
    edges = np.nanquantile(train, np.linspace(0, 1, q + 1)[1:-1])
    out = (np.searchsorted(edges, x, side="right") + 0.5) / q - 0.5
    return np.where(np.isnan(x), 0.0, out)


def design(tr, te):
    Xtr = np.column_stack([qmap(tr[f].to_numpy(float), tr[f].to_numpy(float)) for f in FEATS])
    Xte = np.column_stack([qmap(tr[f].to_numpy(float), te[f].to_numpy(float)) for f in FEATS])
    return Xtr, Xte


def logit_fit(X, y, l2=L2, it=30):
    Xb = np.column_stack([np.ones(len(X)), X]); w = np.zeros(Xb.shape[1]); R = np.eye(len(w)) * l2; R[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-Xb @ w)); g = Xb.T @ (p - y) + R @ w
        Hm = (Xb * (p * (1 - p))[:, None]).T @ Xb + R
        step = np.linalg.solve(Hm, g); w -= step
        if np.abs(step).max() < 1e-7: break
    return w


def ridge_fit(X, y, lam=RIDGE):
    Xb = np.column_stack([np.ones(len(X)), X]); R = np.eye(Xb.shape[1]) * lam * len(X) / 1000; R[0, 0] = 0
    return np.linalg.solve(Xb.T @ Xb + R, Xb.T @ y)


def pred(w, X): return np.column_stack([np.ones(len(X)), X]) @ w


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else None


def summ(d):
    if not len(d): return None
    r = d["y_r20"]; w = d["y_rwait"]
    return dict(n=int(len(d)), crossed=round(float(d["y_crossed"].mean()), 4), days=round(float(d["y_dcross"].median()), 1) if d["y_crossed"].any() else None,
                r10=round(float(d["y_r10"].mean()), 5), r20=round(float(r.mean()), 5), med20=round(float(r.median()), 5), win=round(float((r > 0).mean()), 4),
                excess=round(float(d["y_excess"].mean()), 5), best=round(float(d["y_best"].median()), 4), worst=round(float(d["y_worst"].median()), 4),
                bad10=round(float(r.quantile(0.1)), 4), wait=round(float(w.mean()), 5) if w.notna().any() else None, wait_n=int(w.notna().sum()))


def run(data, day):
    ev = build(data); ev["year"] = ev["date"].dt.year
    fin = ev[ev["done"] & ev["y_r20"].notna() & ev["y_excess"].notna()].copy()
    fin = fin[fin[FEATS].notna().sum(axis=1) >= len(FEATS) - 3]
    log.info("cases: %d finished, %d today", len(fin), int(ev["last"].sum()))
    first = int(fin["year"].min()); years = sorted(y for y in fin["year"].unique() if y >= max(TEST_FROM, first + 3))
    fin["p_cross"] = np.nan; fin["p_ex"] = np.nan
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01") - pd.tseries.offsets.BDay(H + 1)
        tr = fin[fin["date"] < cut]; te = fin["year"] == y
        if len(tr) < 2000: continue
        Xtr, Xte = design(tr, fin[te])
        fin.loc[te, "p_cross"] = 1 / (1 + np.exp(-pred(logit_fit(Xtr, tr["y_crossed"].to_numpy()), Xte)))
        fin.loc[te, "p_ex"] = pred(ridge_fit(Xtr, tr["y_excess"].to_numpy()), Xte)
    test = fin[fin["p_ex"].notna()].copy()
    # rank (tenth) of the model's estimate within each test year, so every year counts the same
    test["dec"] = test.groupby("year")["p_ex"].transform(lambda s: np.ceil(s.rank(pct=True) * 10).clip(1, 10)).astype(int)
    test["decx"] = test.groupby("year")["p_cross"].transform(lambda s: np.ceil(s.rank(pct=True) * 10).clip(1, 10)).astype(int)
    deciles = {int(k): summ(g) for k, g in test.groupby("dec")}
    deciles_x = {int(k): summ(g) for k, g in test.groupby("decx")}
    # monthly: top tenth minus all cases, for how sure
    test["ym"] = test["date"].dt.to_period("M")
    mt = test.groupby("ym").apply(lambda g: g.loc[g["dec"] >= 9, "y_excess"].mean() - g["y_excess"].mean() if (g["dec"] >= 9).sum() >= 3 else np.nan)
    mb = test.groupby("ym").apply(lambda g: g.loc[g["dec"] <= 2, "y_excess"].mean() - g["y_excess"].mean() if (g["dec"] <= 2).sum() >= 3 else np.nan)
    by_year = {int(y): dict(all=summ(g), top=summ(g[g["dec"] >= 9]), bottom=summ(g[g["dec"] <= 2])) for y, g in test.groupby("year")}
    # each input on its own: fifths, reported before and from 2020 so stability can be seen
    fac = {}
    for f in FEATS:
        x = fin[f]
        if x.notna().sum() < 1000: continue
        try: q = pd.qcut(x.rank(method="first"), 5, labels=False) + 1
        except ValueError: continue
        rows = []
        for b in range(1, 6):
            g = fin[q == b]
            rows.append(dict(b=b, lo=round(float(x[q == b].min()), 4), hi=round(float(x[q == b].max()), 4), early=summ(g[g["year"] < 2020]), late=summ(g[g["year"] >= 2020])))
        lt = [r["late"]["excess"] for r in rows if r["late"]]; et = [r["early"]["excess"] for r in rows if r["early"]]
        fac[f] = dict(name=NAMES[f], rows=rows, spread_late=round(lt[-1] - lt[0], 5) if len(lt) == 5 else None, spread_early=round(et[-1] - et[0], 5) if len(et) == 5 else None,
                      cross_spread=round(rows[-1]["late"]["crossed"] - rows[0]["late"]["crossed"], 4) if rows[0]["late"] and rows[-1]["late"] else None)
    # latest fit on everything finished, for today's list
    Xall, _ = design(fin, fin.iloc[:1])
    wl = logit_fit(Xall, fin["y_crossed"].to_numpy()); wr = ridge_fit(Xall, fin["y_excess"].to_numpy())
    today = ev[ev["last"] & (ev["date"] == ev["date"].max())].copy()
    out_today = []
    if len(today):
        _, Xt = design(fin, today)
        pc = 1 / (1 + np.exp(-pred(wl, Xt))); px = pred(wr, Xt)
        # tenth of today's estimate against the most recent test year's estimates
        ref = test.loc[test["year"] == test["year"].max(), "p_ex"].to_numpy()
        refx = test.loc[test["year"] == test["year"].max(), "p_cross"].to_numpy()
        dec = np.clip(np.ceil(np.searchsorted(np.sort(ref), px) / max(len(ref), 1) * 10), 1, 10).astype(int)
        decx = np.clip(np.ceil(np.searchsorted(np.sort(refx), pc) / max(len(refx), 1) * 10), 1, 10).astype(int)
        for i, (_, r) in enumerate(today.iterrows()):
            contrib = sorted(((f, float(wr[j + 1] * Xt[i, j])) for j, f in enumerate(FEATS)), key=lambda z: -abs(z[1]))
            out_today.append(dict(key=r["key"], symbol=r["key"].split(":")[1], p_cross=round(float(pc[i]), 3), dec=int(dec[i]), decx=int(decx[i]),
                                  x={f: (None if pd.isna(r[f]) else round(float(r[f]), 4)) for f in FEATS},
                                  pull=[[f, round(v, 5)] for f, v in contrib[:5]]))
        out_today.sort(key=lambda z: (-z["dec"], -z["p_cross"]))
    coef = dict(cross={f: round(float(wl[j + 1]), 3) for j, f in enumerate(FEATS)}, excess={f: round(float(wr[j + 1]) * 100, 3) for j, f in enumerate(FEATS)})
    tt = dict(top=tstat(mt.values), bottom=tstat(mb.values), months=int(mt.notna().sum()),
              top_better_months=int((mt > 0).sum()))
    base = dict(all=summ(fin), test=summ(test), early=summ(fin[fin["year"] < 2020]), late=summ(fin[fin["year"] >= 2020]),
                this_year=summ(fin[fin["year"] == int(day[:4])]))
    return dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, first_date=str(fin["date"].min().date()), stocks=len(data),
                settings=dict(near_pct=NEAR * 100, cooldown=COOL, cross_days=HZ, hold_days=H, cost_pct=COST * 100, test_from=int(years[0]) if years else None,
                              min_price=MIN_PRICE, min_vol=MIN_VOL),
                names=NAMES, base=base, deciles=deciles, deciles_cross=deciles_x, by_year=by_year, t=tt, factors=fac, coef=coef, today=out_today)


def synthetic(n, years, seed=3):
    rng = np.random.default_rng(seed); idx = pd.bdate_range(end=dt.date.today(), periods=int(252 * years)); data = {}
    for i in range(n):
        r = rng.normal(0.0004, 0.018, len(idx)) + 0.003 * np.sin(np.arange(len(idx)) / (20 + i % 30))
        c = 200 * np.exp(np.cumsum(r)); o = c * np.exp(rng.normal(0, 0.006, len(idx)))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.008, len(idx)))); l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.008, len(idx))))
        data[f"NSE:S{i}"] = pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, Volume=rng.integers(2e5, 3e6, len(idx)).astype(float)), index=idx)
    return data


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=2600); ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--synthetic", type=int, default=0); ap.add_argument("--out", default="approach.json"); a = ap.parse_args()
    if a.synthetic:
        data = synthetic(a.synthetic, a.years); day = max(d.index[-1] for d in data.values()).strftime("%Y-%m-%d")
    else:
        import dma44_deep as DD
        nse, _, day = DD.universes(a.nse, 0); log.info("universe: %d NSE", len(nse))
        data, _ = DD.fetch_all(nse, [], a.years)
        for k, d in data.items():
            if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
        if len(data) < int(os.environ.get("AP_MIN", 400)): raise SystemExit("too few stocks downloaded; not updating")
    out = run(data, str(day))
    (ROOT / a.out).write_text(json.dumps(out, separators=(",", ":"), allow_nan=False, default=lambda o: None))
    b = out["base"]; log.info("written %s: %d finished cases, test %s", a.out, b["all"]["n"], json.dumps(b["test"]))
    for k in sorted(out["deciles"]): log.info("tenth %2d %s", k, json.dumps(out["deciles"][k]))
    log.info("t %s", out["t"])


if __name__ == "__main__":
    main()
