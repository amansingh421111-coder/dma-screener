"""Expanded test of every strategy in the library.

Same rules and exits as strategies.py, on far more data and with the fixes found in the 44-DMA audit:
  * every NSE stock at ₹20 or more with trading (about 1,900), about 15 years of daily prices;
  * a trade counts only if, on the signal day, the price was ₹20+ and the stock traded at least ₹50 lakh a day
    (20-day median), so past trades are not picked with today's turnover;
  * trades touching a one-day jump beyond -30% / +45% (unadjusted split, bonus, demerger or a data error) are set aside;
  * two controls: (a) the same stock entered every 5th trading day with the same exits, and (b) the average of
    stocks entered on the SAME day with the same exits, which removes market timing;
  * confidence judged on monthly averages as well as single trades.
The exit (stop / target) for each strategy is picked on the years before SPLIT_YEAR only, by edge over control (b),
and judged on SPLIT_YEAR onwards. Writes strategies_x.json.
"""
import argparse, datetime as dt, json, logging, math, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import strategies as S
import dma44_deep as DD
import dma44_audit as A

log = logging.getLogger("sx")
ROOT = S.ROOT
COST = 0.004
SPLIT_YEAR = 2020
COMBOS = [(k, g) for k in S.GRID for g in S.GRID[k]]
F = dict(n=0, sum=1, ss=2, win=3, pos=4, neg=5, dsum=6, dss=7, tgt=8, stp=9, tim=10, cn=11)   # per-year fields
NF = len(F)
G = {}   # worker globals: dates index, base means


def fast_trades(o, h, l, c, en, sp, tp, mh, overlap=False):
    """Same logic as strategies.simulate (next-open entry, gap fills, stop before target on the same day, one trade at a time).
    Returns list of (signal idx, entry idx, exit idx, return before costs, why)."""
    n = len(o); out = []; i = 0
    for s in en:
        if s < i or s >= n - 1: continue
        ei = s + 1; ep = o[ei]
        if not (ep == ep) or ep <= 0: continue
        stop, tgt = ep * (1 - sp / 100), ep * (1 + tp / 100); last = min(n - 1, ei + mh - 1); hit = None
        for k in range(ei, last + 1):
            ok, hk, lk = o[k], h[k], l[k]
            if not (ok == ok and hk == hk and lk == lk): continue
            if k > ei and ok <= stop: hit = (k, ok, 0); break
            if k > ei and ok >= tgt: hit = (k, ok, 1); break
            if lk <= stop: hit = (k, stop, 0); break
            if hk >= tgt: hit = (k, tgt, 1); break
            if k == ei + mh - 1 and c[k] == c[k]: hit = (k, c[k], 2); break
        if hit is None: break
        out.append((s, ei, hit[0], hit[1] / ep - 1, hit[2]))
        if not overlap: i = hit[0]
    return out


def init(dates, base_mean):
    G["d2i"] = {d: i for i, d in enumerate(dates)}; G["base"] = base_mean
    G["years"] = sorted({d[:4] for d in dates}); G["y2i"] = {y: i for i, y in enumerate(G["years"])}
    G["months"] = sorted({d[:7] for d in dates}); G["m2i"] = {m: i for i, m in enumerate(G["months"])}


def stock_arrays(df):
    P = A.prep(df)
    return P, P["o"].tolist(), P["h"].tolist(), P["l"].tolist(), P["c"].tolist()


def base_work(args):
    """Pass 1: control (a), every 5th day in this stock, for every exit combination."""
    key, df = args
    P, o, h, l, c = stock_arrays(df); n = len(o); out = {}
    for kind, g in COMBOS:
        # every 5th day, each entry independent of the others: a trade still open does not block the next entry,
        # otherwise stocks that were just stopped out would be over-represented on any given day
        tr = fast_trades(o, h, l, c, range(60, n - 1, 5), g[0], g[1], S.MAX_HOLD[kind], overlap=True)
        out[(kind, g)] = [(P["dates"][e], r - COST) for s, e, x, r, w in tr if P["elig"][s] and A.clean_window(P, s - 60, x)]
    return key, out


def sig_work(args):
    """Pass 2: every strategy, every exit combination, aggregated by year and month (with the same-day control matched by date)."""
    key, df, mom = args
    if mom is not None: S.MOMSIG[key] = mom
    df = df.copy(); df.attrs["key"] = key
    P, o, h, l, c = stock_arrays(df)
    d2i, base, y2i, m2i = G["d2i"], G["base"], G["y2i"], G["m2i"]
    gi = [d2i.get(d) for d in P["dates"]]
    res, ny, nm = {}, len(y2i), len(m2i)
    for st in S.STRATS:
        try: en = np.flatnonzero(st["fn"](df).fillna(False).to_numpy(bool))
        except Exception: continue
        for g in S.GRID[st["kind"]]:
            tr = fast_trades(o, h, l, c, en, g[0], g[1], S.MAX_HOLD[st["kind"]])
            if not tr: continue
            Y = np.zeros((ny, NF)); M = np.zeros((nm, 3)); bm = base[(st["kind"], g)]
            for s, e, x, r, w in tr:
                if not P["elig"][s] or not A.clean_window(P, s - 60, x): continue
                r -= COST; d = P["dates"][e]; yi, mi = y2i[d[:4]], m2i[d[:7]]; j = gi[e]
                b = bm[j] if j is not None and bm[j] == bm[j] else None
                row = Y[yi]; row[0] += 1; row[1] += r; row[2] += r * r; row[3] += r > 0; row[4] += max(r, 0); row[5] += min(r, 0); row[8 + w] += 1
                if b is not None:
                    df_ = r - b; row[6] += df_; row[7] += df_ * df_; row[11] += 1; M[mi, 0] += 1; M[mi, 1] += df_
                M[mi, 2] += r
            res[(st["id"], g)] = (Y, M)
    return key, res


def summ(Y, Bs=None):
    """Y: summed year rows (n, sum, ss, win, pos, neg, dsum, dss, tgt, stp, tim, cn)."""
    n = Y[0]
    if n < 1: return None
    avg = Y[1] / n; out = dict(n=int(n), avg=round(avg, 5), win=round(Y[3] / n, 4), pf=None if Y[5] >= 0 else round(Y[4] / -Y[5], 3),
                               exits=dict(target=round(Y[8] / n, 3), stop=round(Y[9] / n, 3), time=round(Y[10] / n, 3)))
    cn = Y[11]
    if cn >= 2:
        e = Y[6] / cn; var = max(Y[7] / cn - e * e, 0) * cn / (cn - 1)
        out.update(ctrl=round(avg - e, 5), edge=round(e, 5), t=round(e / math.sqrt(var / cn), 2) if var > 0 else None)
    if Bs is not None and Bs[0] >= 1: out["same_stock"] = round(Bs[1] / Bs[0], 5)
    return out


def monthly_t(M):
    d = np.array([m[1] / m[0] for m in M if m[0] >= 3])
    if len(d) < 6 or d.std(ddof=1) == 0: return None
    return dict(months=int(len(d)), positive=int((d > 0).sum()), t=round(float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))), 2), mean=round(float(d.mean()), 5))


def rate_x(train, test, mt, yrs):
    """Score out of 5, same arithmetic as the original library, judged against the same-day control on the later period.
    Confidence uses the monthly t (stocks signalling on the same day are not independent)."""
    if not test or test["n"] < 100: return 0.0, [["Fewer than 100 trades from %d on: no score" % SPLIT_YEAR, 0]]
    e, a, pf, n = test.get("edge") or 0, test["avg"], test.get("pf") or 0, test["n"]
    ty = [v for y, v in yrs.items() if int(y) >= SPLIT_YEAR and v["n"] >= 30 and v.get("edge") is not None]
    yp = sum(1 for v in ty if v["edge"] > 0); t = mt["t"] if mt else None; P = []
    P.append(["Better than the same-day control from %d on: 2.5 points at +1.5%% or more, 2 at +0.8%%, 1.5 at +0.4%%, 1 at +0.1%%, 0.5 above 0" % SPLIT_YEAR, 2.5 if e >= 0.015 else 2.0 if e >= 0.008 else 1.5 if e >= 0.004 else 1.0 if e >= 0.001 else 0.5 if e > 0 else 0])
    P.append(["Average profit per trade after costs is above zero: 0.5 point", 0.5 if a > 0 else 0])
    P.append(["Profit factor (money won / money lost): 0.5 point at 1.3 or more, 0.25 at 1.15", 0.5 if pf >= 1.3 else 0.25 if pf >= 1.15 else 0])
    P.append(["Number of trades: 0.5 point at 3,000 or more, 0.25 at 1,000", 0.5 if n >= 3000 else 0.25 if n >= 1000 else 0])
    P.append(["Also better than the control in the years where the exit was chosen: 0.5 point", 0.5 if train and (train.get("edge") or 0) > 0 else 0])
    P.append(["Better than the control in at least 75%% of the years from %d on: 0.5 point" % SPLIT_YEAR, 0.5 if len(ty) >= 3 and yp / len(ty) >= 0.75 else 0])
    pts = sum(x[1] for x in P)
    if e <= 0 and pts > 1.0: P.append(["Cap: not better than the control, so the score cannot exceed 1", 1.0 - pts]); pts = 1.0
    elif (t is None or t < 1) and pts > 1.5: P.append(["Cap: judged month by month the edge is within normal luck (monthly t below 1): score cannot exceed 1.5", 1.5 - pts]); pts = 1.5
    elif (t is None or t < 2) and pts > 2.5: P.append(["Cap: judged month by month the edge is not yet solid (monthly t below 2): score cannot exceed 2.5", 2.5 - pts]); pts = 2.5
    return round(min(5.0, pts) * 2) / 2, P


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=2600); ap.add_argument("--years", type=int, default=15); a = ap.parse_args()
    nse, _, day = DD.universes(a.nse, 0); log.info("universe: %d NSE", len(nse))
    data, _ = DD.fetch_all(nse, [], a.years)
    for k, d in data.items():
        if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
    log.info("downloaded %d stocks", len(data))
    if len(data) < int(os.environ.get("SX_MIN", 400)): raise SystemExit("too few stocks downloaded; not updating")
    dates = sorted({x for d in data.values() for x in d.index.strftime("%Y-%m-%d")}); d2i = {d: i for i, d in enumerate(dates)}
    # cross-sectional momentum signal (6-month momentum leaders), computed on all stocks together as in strategies.py
    closes = pd.DataFrame({k: d["Close"] for k, d in data.items()}).sort_index().ffill(limit=5)
    rank = closes.pct_change(126, fill_method=None).rank(axis=1, pct=True)
    pm = pd.Series(closes.index.to_period("M"), index=closes.index); firstday = pm.ne(pm.shift(1)).to_numpy()
    mom = {k: ((rank[k] >= 0.9) & firstday & (closes[k] > S.sma(closes[k], 200))).fillna(False) for k in data}
    del closes, rank
    # pass 1: control (a); its date averages are control (b)
    bsum = {cg: np.zeros(len(dates)) for cg in COMBOS}; bcnt = {cg: np.zeros(len(dates)) for cg in COMBOS}; byear = {}
    with ProcessPoolExecutor() as ex:
        for key, out in ex.map(base_work, data.items(), chunksize=16):
            for cg, rows in out.items():
                for d, r in rows:
                    j = d2i[d]; bsum[cg][j] += r; bcnt[cg][j] += 1
                    yy = byear.setdefault(cg, {}).setdefault(d[:4], [0, 0.0]); yy[0] += 1; yy[1] += r
    base_mean = {cg: np.where(bcnt[cg] >= 5, bsum[cg] / np.maximum(bcnt[cg], 1), np.nan) for cg in COMBOS}
    log.info("pass 1 done: %d control trades", int(sum(v.sum() for v in bcnt.values())))
    # pass 2: strategies
    years = sorted({d[:4] for d in dates}); months = sorted({d[:7] for d in dates})
    acc = {}
    with ProcessPoolExecutor(initializer=init, initargs=(dates, base_mean)) as ex:
        for key, res in ex.map(sig_work, ((k, d, mom[k]) for k, d in data.items()), chunksize=8):
            for sg, (Y, M) in res.items():
                if sg in acc: acc[sg][0] += Y; acc[sg][1] += M; acc[sg][2] += 1
                else: acc[sg] = [Y.copy(), M.copy(), 1]
    log.info("pass 2 done")
    old = {}
    try: old = {s["id"]: s for s in json.loads((ROOT / "strategies.json").read_text())["strategies"]}
    except Exception: pass
    yi_train = [i for i, y in enumerate(years) if int(y) < SPLIT_YEAR]; yi_test = [i for i, y in enumerate(years) if int(y) >= SPLIT_YEAR]
    mi_test = [i for i, m in enumerate(months) if int(m[:4]) >= SPLIT_YEAR]
    out = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, years_of_data=a.years, first_date=dates[0], split_year=SPLIT_YEAR,
               stocks=len(data), cost_pct=COST * 100, filters=dict(min_price=A.MIN_PX, min_traded_value=A.MIN_VAL, jump_lo=A.JUMP_LO, jump_hi=A.JUMP_HI),
               control_trades=int(sum(v.sum() for v in bcnt.values())), strategies=[])
    for st in S.STRATS:
        kind = st["kind"]; best = None; grid = []
        for g in S.GRID[kind]:
            if (st["id"], g) not in acc: continue
            Y, M, nst = acc[(st["id"], g)]
            tr, te = summ(Y[yi_train].sum(0)), summ(Y[yi_test].sum(0))
            grid.append(dict(stop=g[0], target=g[1], train_n=tr and tr["n"], train_edge=tr and tr.get("edge"), test_n=te and te["n"], test_edge=te and te.get("edge"), test_avg=te and te["avg"]))
            if tr and tr["n"] >= 100 and tr.get("edge") is not None and (best is None or tr["edge"] > best[0]): best = (tr["edge"], g)
        if best is None: continue
        g = best[1]; Y, M, nst = acc[(st["id"], g)]; by = byear.get((kind, g), {})
        yrs = {}
        for i, y in enumerate(years):
            s_ = summ(Y[i], by.get(y))
            if s_: yrs[y] = s_
        o = old.get(st["id"], {})
        trn, tst, mtt = summ(Y[yi_train].sum(0)), summ(Y[yi_test].sum(0)), monthly_t(M[mi_test])
        stars, parts = rate_x(trn, tst, mtt, yrs)
        out["strategies"].append(dict(id=st["id"], name=st["name"], kind=kind, params=dict(stop=g[0], target=g[1], max_hold=S.MAX_HOLD[kind]), stocks=nst, stars=stars, score_parts=parts,
            train=summ(Y[yi_train].sum(0)), test=summ(Y[yi_test].sum(0)), all=summ(Y.sum(0)),
            monthly_test=monthly_t(M[mi_test]), monthly_all=monthly_t(M), years=yrs, grid=grid,
            grid_positive=sum(1 for x in grid if (x["test_edge"] or 0) > 0), grid_n=len(grid),
            orig=dict(n=(o.get("train") or {}).get("n", 0) + (o.get("test") or {}).get("n", 0), params=o.get("params"))))
    (ROOT / "strategies_x.json").write_text(json.dumps(out, separators=(",", ":")))
    log.info("written strategies_x.json: %d strategies", len(out["strategies"]))


if __name__ == "__main__":
    main()
