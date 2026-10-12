"""Which stop loss and target worked best for each strategy, this year and in recent years.

For every strategy in the library (plus the screener's own Buy rule) the same entries are replayed with about 40 different
exit rules (exitrules.py): fixed percentages, volatility (ATR) based levels, trailing stops and a 44-DMA stop.
Because every rule sees exactly the same trades, the comparison is about the exit alone.

Data and filters as in the expanded strategy test: every NSE stock at Rs 20+ with trading, about 12 years of adjusted daily prices;
a trade counts only if on the signal day the price was Rs 20+ and the stock traded at least Rs 50 lakh a day (20-day median);
trades touching a one-day jump beyond -30% / +45% (unadjusted corporate actions, bad data) are set aside; 0.4% costs per trade.
A repeat signal in the same stock within 10 trading days is ignored. Only trades whose full window has passed are counted.

Choice of rule (as of the latest price date): average profit per trade after costs, in the current year (weight 3),
last year (weight 2) and the year before (weight 1). A year with fewer than 20 trades is left out.
Only rules that give every share the same percentage stop (fixed % or trailing %) are chosen by default; the best of all rules,
including volatility (ATR) scaled and 44-DMA stops, is recorded as chosen_vol for those who prefer it.
Also recorded: the rule with the best average over every year (chosen_all, chosen_vol_all), which a user can pick instead.
Walk-forward check: the same choice made month by month with only the data available at that time, then used on the next
month's trades, compared with the strategy's fixed library exit and with the rule that was best over all earlier years.
Writes exits.json.
"""
import argparse, datetime as dt, json, logging, math, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import strategies as S
import exitrules as X

log = logging.getLogger("exits")
ROOT = S.ROOT
COOLDOWN = 10
WEIGHTS = (3, 2, 1)
MIN_YEAR_N = 20
WF_FROM = 2016
LAG = {"swing": 3, "short": 2}          # months before a month's trades are all finished (60 / 25 trading days)
NF = 8                                   # n, sum, sumsq, wins, days, stop, target, time
G = {}


def s_screener(df):
    c = df["Close"]; m = S.sma(c, 44)
    return S.first((c >= m) & (c <= m * 1.05))


STRATS = [dict(id="screener", name="Screener Buy (first day 0–5% above the 44-DMA)", kind="swing", fn=s_screener,
               rule="First day the close is at or up to 5% above the 44-day average: the Buy list on the Screener tab.")] + list(S.STRATS)
KINDS = ("swing", "short")
SI = {k: [i for i, s in enumerate(STRATS) if s["kind"] == k] for k in KINDS}
RULES = {k: X.grid(k) for k in KINDS}
PCT_FAMS = ("fix", "trail")   # rules that put every share's stop at the same percentage (the default; volatility-scaled rules are an option)


def init(months):
    G["m2i"] = {m: i for i, m in enumerate(months)}; G["nm"] = len(months)


def one_stock(key, df, mom):
    import dma44_audit as A
    if mom is not None: S.MOMSIG[key] = mom
    df = df.copy(); df.attrs["key"] = key
    P = A.prep(df); o, h, l, c = P["o"], P["h"], P["l"], P["c"]; n = len(c)
    if n < 120: return {}
    At = X.atr14(h, l, c); M = X.sma(c, 44); m2i = G["m2i"]; out = {}
    for kind in KINDS:
        Hm = X.HMAX[kind]; rows = []
        for j, si in enumerate(SI[kind]):
            try: en = np.flatnonzero(STRATS[si]["fn"](df).fillna(False).to_numpy(bool))
            except Exception: continue
            lastk = -10 ** 9
            for s in en:
                if s - lastk < COOLDOWN: continue
                lastk = s
                ei = s + 1
                if s < 60 or ei + Hm > n or not P["elig"][s] or not A.clean_window(P, s - 60, ei + Hm - 1): continue
                ep = o[ei]
                if not (ep > 0) or not (At[s] == At[s]): continue
                rows.append((j, s))
        if not rows: continue
        J = np.array([r[0] for r in rows]); Ss = np.array([r[1] for r in rows]); E = Ss + 1
        idx = E[:, None] + np.arange(Hm)[None, :]; ep = o[E][:, None]
        O, H_, L_, C_ = o[idx] / ep, h[idx] / ep, l[idx] / ep, c[idx] / ep
        D = M[idx - 1] / ep; a = At[Ss] / ep[:, 0]
        ok = ~(np.isnan(O).any(1) | np.isnan(H_).any(1) | np.isnan(L_).any(1) | np.isnan(C_).any(1))
        if not ok.any(): continue
        O, H_, L_, C_, D, a, J, E = O[ok], H_[ok], L_[ok], C_[ok], D[ok], a[ok], J[ok], E[ok]
        mi = np.array([m2i[P["dates"][e][:7]] for e in E])
        acc = np.zeros((len(SI[kind]), len(RULES[kind]), G["nm"], NF))
        for ri, rule in enumerate(RULES[kind]):
            ret, kx, why, _, _ = X.simulate(O, H_, L_, C_, D, a, rule)
            r = ret - X.COST
            vals = np.stack([np.ones_like(r), r, r * r, (r > 0).astype(float), kx + 1.0, (why == 0).astype(float), (why == 1).astype(float), (why == 2).astype(float)], 1)
            np.add.at(acc[:, ri], (J, mi), vals)
        out[kind] = acc
    return out


def work(chunk):
    tot = {}
    for key, df, mom in chunk:
        try: res = one_stock(key, df, mom)
        except Exception as e: log.warning("%s: %s", key, e); continue
        for k, v in res.items():
            if k in tot: tot[k] += v
            else: tot[k] = v
    return tot


def stat(v):
    """v: summed NF fields -> dict"""
    n = v[0]
    if n < 1: return None
    avg = v[1] / n; sd = math.sqrt(max(v[2] / n - avg * avg, 0) * n / max(n - 1, 1))
    return dict(n=int(n), avg=round(avg, 5), win=round(v[3] / n, 3), days=round(v[4] / n, 1), sd=round(sd, 4),
                exits=[round(v[5] / n, 3), round(v[6] / n, 3), round(v[7] / n, 3)])


def score(byyear, cur):
    """byyear: {year: (R, NF) summed}. Returns (scores (R,), parts) using the current year (weight 3) and the two before."""
    ws, parts = [], []
    for w, y in zip(WEIGHTS, (cur, cur - 1, cur - 2)):
        v = byyear.get(y)
        if v is None or v[0, 0] < MIN_YEAR_N: continue
        ws.append((w, v[:, 1] / v[:, 0])); parts.append(dict(year=y, weight=w, n=int(v[0, 0])))
    if not ws or sum(p["n"] for p in parts) < 60: return None, parts
    tw = sum(w for w, _ in ws); return sum(w * s for w, s in ws) / tw, parts


def summarise(st, acc, months, lib_id, price_year):
    kind = st["kind"]; R = RULES[kind]; ids = [r["id"] for r in R]
    yrs = sorted({int(m[:4]) for m in months}); ym = {y: [i for i, m in enumerate(months) if int(m[:4]) == y] for y in yrs}
    byyear = {y: acc[:, ym[y]].sum(1) for y in yrs}
    sc, parts = score(byyear, price_year)
    fallback = None
    if sc is None:
        allv = sum(byyear[y] for y in yrs if y >= 2016)
        if allv[0, 0] < 60: return None
        sc = allv[:, 1] / allv[:, 0]; fallback = "Too few recent trades: all years from 2016 used, equally"
    li = ids.index(lib_id) if lib_id in ids else None
    PM = np.array([r["fam"] in PCT_FAMS for r in R])   # same percentage for every share: fixed % or trailing % rules
    neg = np.where(PM, 0.0, -np.inf)
    order = np.argsort(-(sc + neg)); best = int(order[0]); orderV = np.argsort(-sc); bestV = int(orderV[0])
    tot = acc.sum(1)
    sca = tot[:, 1] / np.maximum(tot[:, 0], 1); ba = int(np.argmax(sca + neg)); baV = int(np.argmax(sca))   # alternative: best over every year, all trades counted equally
    def row(i):
        return dict(rule=ids[i], score=round(float(sc[i]), 5), years={str(y): stat(byyear[y][i]) for y in (price_year, price_year - 1, price_year - 2) if y in byyear and byyear[y][i, 0] > 0},
                    all=stat(tot[i]))
    def walk_for(mask):
        """pick each month with the data finished by then (among the allowed rules), apply to that month's trades"""
        lag = LAG[kind]; mneg = np.where(mask, 0.0, -np.inf)
        wf = {"adaptive": np.zeros(2), "library": np.zeros(2), "longrun": np.zeros(2)}; wy = {}; diffs = []; picks = []
        mcum = np.cumsum(acc, axis=1); yidx = np.array([int(m[:4]) for m in months])
        for t, m in enumerate(months):
            y = int(m[:4])
            if y < WF_FROM or t - lag < 0: continue
            e = t - lag; cur = acc[:, t]
            if cur[0, 0] < 1: continue
            by = {}
            for yy in (y, y - 1, y - 2):
                sel = np.flatnonzero((yidx == yy) & (np.arange(len(months)) <= e))
                if len(sel): by[yy] = acc[:, sel].sum(1)
            s_, _ = score(by, y); tot_e = mcum[:, e]
            if s_ is None or tot_e[0, 0] < 60: continue
            pa = int(np.argmax(s_ + mneg)); pl = int(np.argmax(tot_e[:, 1] / tot_e[:, 0] + mneg))
            picks.append(ids[pa]); rec = wy.setdefault(y, np.zeros((3, 2)))
            for j, (nm, i) in enumerate((("adaptive", pa), ("library", li if li is not None else pa), ("longrun", pl))):
                wf[nm] += cur[i, :2]; rec[j] += cur[i, :2]
            if li is not None: diffs.append(cur[pa, 1] / cur[pa, 0] - cur[li, 1] / cur[li, 0])
        if not wf["adaptive"][0] > 0: return None
        d = np.array(diffs); tval = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))) if len(d) > 5 and d.std(ddof=1) > 0 else None
        return dict(start=WF_FROM, n=int(wf["adaptive"][0]), months=len(d), avg={k: round(v[1] / v[0], 5) for k, v in wf.items() if v[0] > 0},
                    years={str(y): [round(r[j, 1] / r[j, 0], 5) if r[j, 0] else None for j in range(3)] + [int(r[0, 0])] for y, r in sorted(wy.items())},
                    t_vs_library=None if tval is None else round(tval, 2), months_better=int((d > 0).sum()) if len(d) else 0,
                    distinct_picks=len(set(picks)), last_pick=picks[-1] if picks else None)
    walk, walkV = walk_for(PM), walk_for(np.ones(len(R), bool))
    pick = lambda i, sc_: dict(rule=ids[i], label=X.label(R[i]), score=round(float(sc_[i]), 5))
    allx = lambda i: dict(pick(i, sca), n=int(tot[i, 0]), days=round(float(tot[i, 4] / max(tot[i, 0], 1)), 1), recent_score=round(float(sc[i]), 5),
                          years={str(y): stat(byyear[y][i]) for y in (price_year, price_year - 1, price_year - 2) if y in byyear and byyear[y][i, 0] > 0})
    return dict(id=st["id"], name=st["name"], kind=kind, rule_text=st.get("rule"), library_rule=lib_id,
                chosen=dict(pick(best, sc), parts=parts, fallback=fallback), chosen_all=allx(ba),
                chosen_vol=dict(pick(bestV, sc), parts=parts, years=row(bestV)["years"]), chosen_vol_all=allx(baV),
                ranking=[row(int(i)) for i in order[:6]], library=row(li) if li is not None else None,
                table=[[ids[i], round(float(sc[i]), 5)] + [None if byyear.get(y) is None or byyear[y][i, 0] < 1 else round(float(byyear[y][i, 1] / byyear[y][i, 0]), 5) for y in (price_year, price_year - 1, price_year - 2)] +
                       [round(float(tot[i, 1] / tot[i, 0]), 5) if tot[i, 0] else None, round(float(tot[i, 4] / tot[i, 0]), 1) if tot[i, 0] else None] for i in orderV],
                trades_by_year={str(y): int(byyear[y][0, 0]) for y in yrs if byyear[y][0, 0] > 0}, walk=walk, walk_vol=walkV)


def run(data, day, years_n):
    dates = sorted({x for d in data.values() for x in d.index.strftime("%Y-%m-%d")}); months = sorted({d[:7] for d in dates})
    closes = pd.DataFrame({k: d["Close"] for k, d in data.items()}).sort_index().ffill(limit=5)
    rank = closes.pct_change(126, fill_method=None).rank(axis=1, pct=True)
    pm = pd.Series(closes.index.to_period("M"), index=closes.index); firstday = pm.ne(pm.shift(1)).to_numpy()
    mom = {k: ((rank[k] >= 0.9) & firstday & (closes[k] > S.sma(closes[k], 200))).fillna(False) for k in data}
    del closes, rank
    items = [(k, d, mom[k]) for k, d in data.items()]; chunks = [items[i:i + 40] for i in range(0, len(items), 40)]
    acc = {}
    with ProcessPoolExecutor(initializer=init, initargs=(months,)) as ex:
        for res in ex.map(work, chunks):
            for k, v in res.items():
                if k in acc: acc[k] += v
                else: acc[k] = v
    log.info("simulated: %s", {k: int(v[:, 0, :, 0].sum()) for k, v in acc.items()})
    lib = {}
    try:
        sx = json.loads((ROOT / "strategies_x.json").read_text())
        lib = {s["id"]: (s["params"]["stop"], s["params"]["target"]) for s in sx["strategies"]}
    except Exception: pass
    stars = {}
    try: stars = {s["id"]: s.get("stars") for s in json.loads((ROOT / "strategies.json").read_text())["strategies"]}
    except Exception: pass
    py = int(day[:4]); out = []
    for kind in KINDS:
        if kind not in acc: continue
        for j, si in enumerate(SI[kind]):
            st = STRATS[si]; sp, tp = lib.get(st["id"], (8, 20) if kind == "swing" else (6, 8))
            s_ = summarise(st, acc[kind][j], months, X.library_rule(kind, sp, tp), py)
            if s_: s_["stars"] = stars.get(st["id"]); out.append(s_)
    return dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, years_of_data=years_n, first_date=dates[0], stocks=len(data),
                cost_pct=X.COST * 100, cooldown=COOLDOWN, weights=list(WEIGHTS), min_year_n=MIN_YEAR_N, current_year=py,
                rules={k: [dict(r, label=X.label(r)) for r in RULES[k]] for k in KINDS}, default="screener", strategies=out)


def synthetic(n, years, seed=1):
    rng = np.random.default_rng(seed); idx = pd.bdate_range(end=dt.date.today(), periods=int(252 * years)); data = {}
    for i in range(n):
        r = rng.normal(0.0004, 0.02, len(idx)) + 0.002 * np.sin(np.arange(len(idx)) / (30 + i % 40))
        c = 100 * np.exp(np.cumsum(r)); o = c * np.exp(rng.normal(0, 0.006, len(idx)))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.008, len(idx)))); l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.008, len(idx))))
        data[f"NSE:S{i}"] = pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, Volume=rng.integers(2e5, 2e6, len(idx)).astype(float)), index=idx)
    return data


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=2600); ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--synthetic", type=int, default=0); ap.add_argument("--out", default="exits.json"); a = ap.parse_args()
    if a.synthetic:
        data = synthetic(a.synthetic, a.years); day = max(d.index[-1] for d in data.values()).strftime("%Y-%m-%d")
    else:
        import dma44_deep as DD
        nse, _, day = DD.universes(a.nse, 0); log.info("universe: %d NSE", len(nse))
        data, _ = DD.fetch_all(nse, [], a.years)
        for k, d in data.items():
            if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
        if len(data) < int(os.environ.get("EX_MIN", 400)): raise SystemExit("too few stocks downloaded; not updating")
    out = run(data, day, a.years)
    (ROOT / a.out).write_text(json.dumps(out, separators=(",", ":")))
    log.info("written %s: %d strategies", a.out, len(out["strategies"]))
    for s in out["strategies"]:
        w = s["walk"] or {}
        log.info("%-12s %-34s score %+.2f%%  walk adaptive %s library %s", s["id"], s["chosen"]["rule"], s["chosen"]["score"] * 100, (w.get("avg") or {}).get("adaptive"), (w.get("avg") or {}).get("library"))


if __name__ == "__main__":
    main()
