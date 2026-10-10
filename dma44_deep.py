"""Deep test of one idea: buy a stock that is just above a RISING moving average (the "44-DMA buy zone").

What it does, on both exchanges separately:
  * NSE group: the most traded NSE stocks.   BSE group: the most traded stocks that are listed on the BSE only (not on the NSE).
  * 62 versions of the rule (average length, how far above it, how long it must have been rising, first day only or every day, extra filters)
  * every version is run with 4 different exits (3 fixed stop/target pairs and 1 trailing stop)
  * every version is compared with random entries in the same stocks, same period, same exit
  * the earlier 60% of the history is for choosing, the later 40% is for judging
  * the original rule also gets the eight extra checks, separately for NSE and for BSE

Usage: python dma44_deep.py [--nse 1000] [--bse 450] [--years 6] [--cost 0.004]
Output: dma44_deep.json
"""
import argparse, datetime as dt, json, logging, os, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import strategies as S

log = logging.getLogger("deep")
ROOT = S.ROOT
EXITS = [(5, 10, None), (8, 20, None), (12, 30, None), (12, 0, 12)]     # stop %, target %, trailing %
EXIT_LABEL = ["Stop −5%, target +10%", "Stop −8%, target +20%", "Stop −12%, target +30%", "Trailing stop 12% below the peak (no target)"]
MAXH = 40
FILTERS = [("vol15", "volume at least 1.5 times its 20-day average"), ("above200", "price above its 200-day average"), ("rsi60", "RSI (14) below 60"),
           ("rsi50", "RSI (14) above 50"), ("nifty_up", "only when the Nifty 50 is above its 200-day average"), ("nifty_dn", "only when the Nifty 50 is below its 200-day average"),
           ("near_high", "within 20% of its 52-week high"), ("steep", "the average rose at least 1% over 5 days")]
HEAD = dict(ma=44, zone=5, slope=5, first=True, filt="none")           # the rule as already tested on the Strategies page


def make_variants():
    v = [dict(ma=ma, zone=z, slope=k, first=f, filt="none") for ma in (30, 44, 60) for z in (3, 5, 8) for k in (3, 5, 10) for f in (True, False)]
    v += [dict(HEAD, filt=f) for f, _ in FILTERS]
    for x in v: x["id"] = f"ma{x['ma']}_z{x['zone']}_s{x['slope']}_{'first' if x['first'] else 'every'}_{x['filt']}"
    return v


def label(v):
    s = f"{v['ma']}-day average · 0 to {v['zone']}% above it · rising over {v['slope']} days · {'first day only' if v['first'] else 'every day in the zone'}"
    f = dict(FILTERS).get(v["filt"]); return s + (f" · {f}" if f else "")


VARS = make_variants()
NOK = None


def entry(df, v, reg):
    c = df["Close"]; m = S.sma(c, v["ma"]); cond = (c >= m) & (c <= m * (1 + v["zone"] / 100)) & (m > m.shift(v["slope"]))
    f = v["filt"]
    if f == "vol15": cond &= df["Volume"] >= 1.5 * df["Volume"].shift(1).rolling(20).mean()
    elif f == "above200": cond &= c > S.sma(c, 200)
    elif f == "rsi60": cond &= S.rsi(c) < 60
    elif f == "rsi50": cond &= S.rsi(c) > 50
    elif f == "nifty_up": cond &= pd.Series(reg, index=df.index)
    elif f == "nifty_dn": cond &= ~pd.Series(reg, index=df.index)
    elif f == "near_high": cond &= c >= 0.8 * c.rolling(252).max()
    elif f == "steep": cond &= m > m.shift(5) * 1.01
    cond = cond.fillna(False)
    return S.first(cond) if v["first"] else cond


def _init(nok):
    global NOK; NOK = nok


def _reg(df):
    return NOK.reindex(df.index, method="ffill").fillna(False).to_numpy(bool) if NOK is not None and len(NOK) else np.zeros(len(df), bool)


def _pack(tr, sidx):
    if not tr: return None
    return (np.fromiter((t["eo"] for t in tr), np.int64, len(tr)), np.fromiter((t["ret"] for t in tr), np.float32, len(tr)),
            np.fromiter((1 if t["up"] else 0 for t in tr), np.int8, len(tr)), sidx)


def work(item):
    key, sidx, df, cost = item
    reg = _reg(df); out = {}
    rnd = pd.Series(np.arange(len(df)) % 5 == 0, index=df.index)
    for ei, (st, tg, tr_) in enumerate(EXITS):
        t, _ = S.simulate(df, rnd, st, tg, MAXH, cost, reg, trail=tr_); p = _pack(t, sidx)
        if p: out[("c", ei)] = p
    for vi, v in enumerate(VARS):
        try: en = entry(df, v, reg)
        except Exception: continue
        if not en.any(): continue
        for ei, (st, tg, tr_) in enumerate(EXITS):
            t, _ = S.simulate(df, en, st, tg, MAXH, cost, reg, trail=tr_); p = _pack(t, sidx)
            if p: out[(vi, ei)] = p
    return key, out


def cat(parts):
    parts = [p for p in parts if p is not None]
    if not parts: return None
    return tuple(np.concatenate([p[i] if i < 3 else np.full(len(p[0]), p[3], np.int32) for p in parts]) for i in range(4))


def ms(a):
    """compact numbers for one set of trades (a = returns array)"""
    if a is None or len(a) == 0: return None
    w, lo = a[a > 0], a[a <= 0]
    return dict(n=int(len(a)), avg=round(float(a.mean()), 4), win=round(float((a > 0).mean()), 3), pf=None if lo.sum() >= 0 else round(float(w.sum() / -lo.sum()), 2))


def cmp(a, b):
    """trades a against random entries b: average, edge and t"""
    d = ms(a)
    if d is None or d["n"] < 30 or b is None or len(b) < 30: return dict(d or dict(n=0), edge=None, t=None)
    e = float(a.mean() - b.mean()); se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    return dict(d, edge=round(e, 4), t=None if se == 0 else round(e / se, 2), base=round(float(b.mean()), 4))


def cut(p, lo, hi):
    if p is None: return None
    m = (p[0] >= lo) & (p[0] < hi); return p[1][m] if m.any() else None


def aggregate(res, groups, split):
    """res[(vi,ei,grp)] and ctrl[(ei,grp)] are packed trades; groups = list of group names"""
    out = []
    for vi, v in enumerate(VARS):
        row = dict(id=v["id"], label=label(v), params={k: v[k] for k in ("ma", "zone", "slope", "first", "filt")}, r=[])
        for ei in range(len(EXITS)):
            g_ = {}
            for g in groups:
                a, b = res.get((vi, ei, g)), res.get(("c", ei, g))
                g_[g] = dict(tr=cmp(cut(a, 0, split), cut(b, 0, split)), te=cmp(cut(a, split, 10 ** 9), cut(b, split, 10 ** 9)))
            row["r"].append(g_)
        out.append(row)
    return out


def summarise(rows, groups):
    """Per exit and group: how many versions beat random later, and how the versions that looked best EARLIER did LATER."""
    out = []
    for ei in range(len(EXITS)):
        per = {}
        for g in groups:
            ok = [(i, r["r"][ei][g]) for i, r in enumerate(rows) if r["r"][ei][g]["te"].get("edge") is not None and r["r"][ei][g]["tr"].get("edge") is not None]
            pos = sum(1 for _, x in ok if x["te"]["edge"] > 0); sig = sum(1 for _, x in ok if (x["te"]["t"] or 0) >= 2)
            best = sorted([(i, x) for i, x in ok if x["tr"]["n"] >= 100], key=lambda y: -y[1]["tr"]["edge"])[:5]
            hi = next((i for i, r in enumerate(rows) if r["params"] == {k: HEAD[k] for k in ("ma", "zone", "slope", "first", "filt")}), None)
            per[g] = dict(tested=len(ok), positive=pos, strong=sig,
                          picked=[dict(i=i, id=rows[i]["id"], tr=x["tr"].get("edge"), te_edge=x["te"]["edge"], te_t=x["te"]["t"], te_n=x["te"]["n"]) for i, x in best],
                          avg_edge=round(float(np.mean([x["te"]["edge"] for _, x in ok])), 4) if ok else None, head=hi)
        out.append(per)
    return out


def regime(a, b, split):
    """headline rule, later period: edge when the Nifty was above vs below its 200-day average"""
    r = {}
    if a is None or b is None: return r
    ma, mb = a[0] >= split, b[0] >= split
    for nm, f in (("above", 1), ("below", 0)):
        x = a[1][ma & (a[2] == f)]; y = b[1][mb & (b[2] == f)]; r[nm] = cmp(x, y)
    return r


def headline_checks(data, groups_of, nok, split, cost, ranks):
    """The eight extra checks of the Strategies page, for the original rule, separately per exchange (uses the 12-combination stop/target grid)."""
    out = {}
    for g, keys in groups_of.items():
        tr_by_g = {gg: [] for gg in S.GRID["swing"]}; bt_by_g = {gg: [] for gg in S.GRID["swing"]}
        for key in keys:
            df = data[key]; sym = key; reg = nok.reindex(df.index, method="ffill").fillna(False).to_numpy(bool) if len(nok) else None
            en = entry(df, HEAD, reg if reg is not None else np.zeros(len(df), bool)); rnd = pd.Series(np.arange(len(df)) % 5 == 0, index=df.index)
            for gg in S.GRID["swing"]:
                a, _ = S.simulate(df, en, gg[0], gg[1], MAXH, cost, reg); b, _ = S.simulate(df, rnd, gg[0], gg[1], MAXH, cost, reg)
                tr_by_g[gg] += [dict(t, sym=sym) for t in a]; bt_by_g[gg] += [dict(t, sym=sym) for t in b]
        order = {k: i for i, k in enumerate(ranks[g])}
        best = None; inper = lambda x, lo, hi: [t for t in x if lo <= t["entry"] < hi]
        for gg, tr in tr_by_g.items():
            a = S.stats([t for t in tr if t["entry"] < split], inper(bt_by_g[gg], "0000", split))
            if a and a["n"] >= 60 and (best is None or a["edge"] > best[0]): best = (a["edge"], gg)
        gg = best[1] if best else (8, 20)
        test = [t for t in tr_by_g[gg] if t["entry"] >= split]; btest = inper(bt_by_g[gg], split, "9999")
        rb = S.compute_robust(tr_by_g, bt_by_g, gg, split, order, len(keys), cost)
        out[g] = dict(stop=gg[0], target=gg[1], robust=rb, test=S.stats(test, btest),
                      up=S.stats([t for t in test if t["up"]], [t for t in btest if t["up"]]) if test else None,
                      down=S.stats([t for t in test if t["up"] is False], [t for t in btest if t["up"] is False]) if test else None)
    return out


def universes(n_nse, n_bse):
    from screen import load_bhav, BHAV
    load_bhav(); nb, bb = BHAV.get("NSE"), BHAV.get("BSE")
    if not nb: raise SystemExit("official NSE file unavailable")
    nse = [k for k, v in sorted(((k, v) for k, v in nb[1].items() if (v[3] or 0) >= 20 and (v[6] or 0) > 0), key=lambda kv: -kv[1][6])][:n_nse]
    bse = []
    if bb:
        uni = pd.read_csv(ROOT / "universe_bse.csv", dtype=str).fillna("")
        for r in uni.to_dict("records"):
            v = bb[1].get(str(r["code"]).strip())
            if v and (v[3] or 0) >= 20 and (v[6] or 0) >= 0.05: bse.append((r["symbol"], str(r["code"]).strip(), v[6]))
        bse = sorted(bse, key=lambda x: -x[2])[:n_bse]
    return nse, bse, str(nb[0])


def fetch_all(nse, bse, years):
    data, grp = {}, {}
    got = S.adjusted_download([s + ".NS" for s in nse], years, budget=2400)
    for s in nse:
        if s + ".NS" in got: data["NSE:" + s] = got[s + ".NS"]; grp["NSE:" + s] = "nse"
    got = S.adjusted_download([c + ".BO" for _, c, _ in bse], years, budget=1500)
    miss = [(s, c) for s, c, _ in bse if c + ".BO" not in got and not s.isdigit()]
    if miss:
        alt = S.adjusted_download([s + ".BO" for s, _ in miss], years, budget=600)
        for s, c in miss:
            if s + ".BO" in alt: got[c + ".BO"] = alt[s + ".BO"]
    for s, c, _ in bse:
        if c + ".BO" in got: data["BSE:" + s] = got[c + ".BO"]; grp["BSE:" + s] = "bse"
    return data, grp


def run_core(data, grp, nok, cost, years, nse_n, bse_n, workers=None):
    longest = max(data.values(), key=len).index; split_d = longest[int(len(longest) * 0.6)]; split = split_d.toordinal(); split_s = str(split_d.date())
    keys = list(data); sidx = {k: i for i, k in enumerate(keys)}
    items = [(k, sidx[k], data[k], cost) for k in keys]
    res_l = {}
    t0 = time.time(); w = workers or max(1, min(os.cpu_count() or 1, 4))
    if w == 1:
        _init(nok); it = map(work, items)
    else:
        ex = ProcessPoolExecutor(max_workers=w, initializer=_init, initargs=(nok,)); it = ex.map(work, items, chunksize=6)
    done = 0
    for key, out in it:
        g = grp[key]
        for k, p in out.items():
            kk = (k[0], k[1], g) if k[0] != "c" else ("c", k[1], g)
            res_l.setdefault(kk, []).append(p); res_l.setdefault((kk[0], kk[1], "all"), []).append(p)
        done += 1
        if done % 100 == 0: log.info("%d/%d stocks, %ds", done, len(keys), time.time() - t0)
    res = {k: cat(v) for k, v in res_l.items()}
    groups = ["nse", "bse", "all"]
    rows = aggregate(res, groups, split); summ = summarise(rows, groups)
    hv = next(i for i, v in enumerate(VARS) if {k: v[k] for k in ("ma", "zone", "slope", "first", "filt")} == {k: HEAD[k] for k in ("ma", "zone", "slope", "first", "filt")})
    reg = {g: regime(res.get((hv, 1, g)), res.get(("c", 1, g)), split) for g in groups}
    tv = {}   # traded-value rank within each group (as the list order)
    gk = {"nse": [k for k in keys if grp[k] == "nse"], "bse": [k for k in keys if grp[k] == "bse"]}
    log.info("headline checks")
    hl = headline_checks(data, gk, nok, split_s, cost, gk)
    return dict(split=split_s, rows=rows, summary=summ, regime=reg, headline=hl, head_index=hv, n=dict(nse=len(gk["nse"]), bse=len(gk["bse"])),
                trades={g: {str(ei): int(len(res[(hv, ei, g)][0])) if (hv, ei, g) in res else 0 for ei in range(len(EXITS))} for g in groups})


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=1000); ap.add_argument("--bse", type=int, default=450)
    ap.add_argument("--years", type=int, default=6); ap.add_argument("--cost", type=float, default=0.004)
    a = ap.parse_args()
    nse, bse, day = universes(a.nse, a.bse); log.info("universe: %d NSE, %d BSE-only", len(nse), len(bse))
    data, grp = fetch_all(nse, bse, a.years)
    n_n, n_b = sum(1 for v in grp.values() if v == "nse"), sum(1 for v in grp.values() if v == "bse"); log.info("downloaded: %d NSE, %d BSE", n_n, n_b)
    if n_n < 200: raise SystemExit("too few NSE stocks downloaded; not updating")
    nc, nok = S.nifty_regime(a.years)
    out = run_core(data, grp, nok, a.cost, a.years, n_n, n_b)
    out.update(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, years=a.years, cost_pct=round(a.cost * 100, 2),
               exits=[dict(stop=e[0], target=e[1], trail=e[2], label=EXIT_LABEL[i]) for i, e in enumerate(EXITS)], max_hold=MAXH,
               universe=dict(nse=f"The {n_n} most traded NSE stocks (price ₹20 or more)", bse=f"The {n_b} most traded stocks listed on the BSE only, not on the NSE (price ₹20 or more, traded value ₹5 lakh a day or more)"),
               caveats=["Only stocks that trade today are included, so stocks that failed or were delisted are missing. This flatters every result, and probably the BSE group more than the NSE group.",
                        "Yahoo's prices for small BSE stocks have more gaps and errors than for NSE stocks. Entries are assumed filled at the next open; thinly traded stocks can fill worse in real life.",
                        "62 versions of the rule were tested. Some will look good by luck. Judge the group as a whole (how many versions are positive later), not only the best one.",
                        "Stock list and exits are the same for every version; the later 40% of the history was never used to choose anything."])
    (ROOT / "dma44_deep.json").write_text(json.dumps(out, separators=(",", ":")))
    log.info("written dma44_deep.json")


if __name__ == "__main__":
    main()
