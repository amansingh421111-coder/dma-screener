"""Audit and expanded test of the "44-DMA buy zone (rising)" rule.

Rule (unchanged from strategies.py): first day the close is 0 to 5% above a rising 44-day simple average
(the average is higher than 5 days earlier). Buy at the next open. Exit at -8% stop, +20% target or the close
of the 40th trading day. 0.4% costs per round trip.

What this script adds over the earlier tests:
  * more stocks (every NSE stock at ₹20+ with trading, plus BSE-only stocks) and about 12 years of history;
  * a liquidity filter applied on the signal day itself (no use of today's turnover to pick past trades);
  * a bad-data filter: one-day jumps beyond what exchange price bands allow are treated as unadjusted
    corporate actions or Yahoo errors, and trades touching them are set aside (results are shown both ways);
  * a second control: random other stocks bought on the SAME day with the same exits, which removes the
    effect of market timing (signals bunch up after rising markets);
  * statistics that do not assume every trade is independent (monthly averages, block bootstrap by month);
  * results split into the years before any earlier test, the years where the -8%/+20% exit was picked,
    and the later fair-test years.
Writes dma44_audit.json.
"""
import argparse, datetime as dt, json, logging, math, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import strategies as S
import dma44_deep as DD

log = logging.getLogger("audit")
ROOT = S.ROOT
STOP, TGT, HOLD, COST = 8, 20, 40, 0.004
MIN_PX, MIN_VAL = 20.0, 5e6            # ₹20 price, ₹50 lakh median daily traded value over 20 days, on the signal day
JUMP_LO, JUMP_HI = 0.70, 1.45          # a one-day move outside -30% / +45% is beyond normal price bands: treated as bad data
CONTROLS = 3                           # random same-day stocks per signal
CHOSEN_FROM, CHOSEN_TO = "2020-10-01", "2024-05-21"   # where the earlier tests picked the -8%/+20% exit


def one_exit(o, h, l, c, ei, sp, tp, mh):
    """Same exit logic as strategies.simulate, for one entry. Returns (exit index, exit price, why) or None if still open."""
    n = len(o); ep = o[ei]; stop, tgt = ep * (1 - sp / 100), ep * (1 + tp / 100); last = ei + mh - 1
    for k in range(ei, min(n, last + 1)):
        if not (np.isfinite(l[k]) and np.isfinite(h[k]) and np.isfinite(o[k])): continue
        if k > ei and o[k] <= stop: return k, o[k], "stop"
        if k > ei and o[k] >= tgt: return k, o[k], "target"
        if l[k] <= stop: return k, stop, "stop"
        if h[k] >= tgt: return k, tgt, "target"
        if k == last and np.isfinite(c[k]): return k, c[k], "time"
    return None


def prep(df):
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    m = pd.Series(c).rolling(44).mean().to_numpy()
    sig = np.zeros(len(c), bool)
    z = (c >= m) & (c <= m * 1.05) & (m > np.r_[np.full(5, np.nan), m[:-5]])
    z = np.nan_to_num(z, nan=0).astype(bool); sig[1:] = z[1:] & ~z[:-1]; sig[0] = z[0]
    pc = np.r_[np.nan, c[:-1]]
    with np.errstate(divide="ignore", invalid="ignore"):
        jump = (o / pc < JUMP_LO) | (o / pc > JUMP_HI) | (c / pc < JUMP_LO) | (c / pc > JUMP_HI) | (c <= 0) | (o <= 0)
    jump = np.nan_to_num(jump, nan=0).astype(bool)
    jc = np.cumsum(jump)                                   # jumps up to and including day k
    val = pd.Series(c * v).rolling(20, min_periods=15).median().to_numpy()
    elig = (c >= MIN_PX) & (val >= MIN_VAL)
    return dict(o=o, h=h, l=l, c=c, sig=sig, jc=jc, elig=np.nan_to_num(elig, nan=0).astype(bool), dates=df.index.strftime("%Y-%m-%d").to_numpy())


def clean_window(P, a, b):
    """True if no bad-data jump between day a and day b (inclusive)."""
    a = max(a, 1); return P["jc"][b] - P["jc"][a - 1] == 0


def trade(P, s, sp=STOP, tp=TGT, mh=HOLD):
    """Entry the day after signal day s. Returns dict or None."""
    ei = s + 1
    if ei >= len(P["o"]) or not np.isfinite(P["o"][ei]) or P["o"][ei] <= 0: return None
    x = one_exit(P["o"], P["h"], P["l"], P["c"], ei, sp, tp, mh)
    if x is None: return None
    k, xp, why = x
    return dict(s=s, ei=ei, xk=k, ret=float(xp / P["o"][ei] - 1 - COST), why=why, days=int(k - ei + 1))


def work(args):
    key, df, nifty_ok = args
    P = prep(df); n = len(P["o"]); out = dict(sig=[], base=[], raw=[])
    reg = nifty_ok.reindex(df.index, method="ffill").fillna(False).to_numpy(bool)
    i = 0
    for s in np.flatnonzero(P["sig"]):                     # signal trades, one at a time per stock (as before)
        if s < i or s >= n - 1: continue
        t = trade(P, s)
        if t is None: break
        i = t["xk"]
        row = (P["dates"][t["ei"]], round(t["ret"], 5), t["why"], t["days"], bool(reg[s]))
        out["raw"].append(row + (bool(P["elig"][s]),))   # before the new filters, for the comparison
        if not P["elig"][s] or not clean_window(P, s - 60, t["xk"]): continue
        out["sig"].append(row)
    i = 0
    for s in range(60, n - 1, 5):                          # control A: same stock, every 5th day, same exits
        if s < i: continue
        t = trade(P, s)
        if t is None: break
        i = t["xk"]
        if not P["elig"][s] or not clean_window(P, s - 60, t["xk"]): continue
        out["base"].append((P["dates"][t["ei"]], round(t["ret"], 5)))
    # per-day arrays for control B (same-day random stocks)
    ok = P["elig"].copy(); ok[:60] = False
    return key, out, dict(dates=P["dates"], ok=ok, sig=P["sig"]), P


def stats(r):
    r = np.asarray(r, float)
    if len(r) == 0: return None
    w, lo = r[r > 0], r[r <= 0]
    return dict(n=int(len(r)), win=round(float((r > 0).mean()), 4), avg=round(float(r.mean()), 5), med=round(float(np.median(r)), 5),
                pf=None if lo.sum() >= 0 else round(float(w.sum() / -lo.sum()), 3), worst=round(float(r.min()), 4), best=round(float(r.max()), 4))


def edge_naive(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 30 or len(b) < 30: return None
    e = a.mean() - b.mean(); se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return dict(edge=round(float(e), 5), t=round(float(e / se), 2) if se else None)


def edge_monthly(A, B):
    """A, B: lists of (date, ret). Edge judged on monthly averages: months are the independent units."""
    ma, mb = {}, {}
    for d, r in A: ma.setdefault(d[:7], []).append(r)
    for d, r in B: mb.setdefault(d[:7], []).append(r)
    diffs = [np.mean(ma[m]) - np.mean(mb[m]) for m in sorted(ma) if m in mb and len(ma[m]) >= 3 and len(mb[m]) >= 3]
    if len(diffs) < 6: return None
    d = np.array(diffs); t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if d.std(ddof=1) else None
    rng = np.random.default_rng(11); bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    return dict(months=len(d), positive=int((d > 0).sum()), mean_month_edge=round(float(d.mean()), 5), t=None if t is None else round(float(t), 2),
                lo95=round(float(np.percentile(bs, 2.5)), 5), hi95=round(float(np.percentile(bs, 97.5)), 5))


def summarize(sig, base, ctrl, lo="0000", hi="9999", pick=lambda x: True):
    A = [x for x in sig if lo <= x[0] < hi and pick(x)]
    Bs = [x for x in base if lo <= x[0] < hi]
    C = [x for x in ctrl if lo <= x[0] < hi and pick(x)]
    ra = [x[1] for x in A]
    return dict(signals=stats(ra), control_same_stock=stats([x[1] for x in Bs]), control_same_day=stats([x[1] for x in C]),
                edge_vs_same_stock=edge_naive(ra, [x[1] for x in Bs]), edge_vs_same_day=edge_naive(ra, [x[1] for x in C]),
                monthly_vs_same_day=edge_monthly([(x[0], x[1]) for x in A], [(x[0], x[1]) for x in C]),
                monthly_vs_same_stock=edge_monthly([(x[0], x[1]) for x in A], [(x[0], x[1]) for x in Bs]),
                exits=None if not A else {k: round(sum(1 for x in A if x[2] == k) / len(A), 3) for k in ("target", "stop", "time")})


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=2500); ap.add_argument("--bse", type=int, default=1200)
    ap.add_argument("--years", type=int, default=12); a = ap.parse_args()
    nse, bse, day = DD.universes(a.nse, a.bse); log.info("universe: %d NSE, %d BSE-only", len(nse), len(bse))
    import time
    got = S.adjusted_download([s + ".NS" for s in nse], a.years, budget=5400)
    data, grp = {}, {}
    for s in nse:
        if s + ".NS" in got: data["NSE:" + s] = got[s + ".NS"]; grp["NSE:" + s] = "nse"
    gb = S.adjusted_download([c + ".BO" for _, c, _ in bse], a.years, budget=3000)
    for s, c, _ in bse:
        if c + ".BO" in gb: data["BSE:" + s] = gb[c + ".BO"]; grp["BSE:" + s] = "bse"
    for k, d in data.items():
        if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
    log.info("downloaded: %d NSE, %d BSE", sum(v == "nse" for v in grp.values()), sum(v == "bse" for v in grp.values()))
    if sum(v == "nse" for v in grp.values()) < int(os.environ.get("AUDIT_MIN", 300)): raise SystemExit("too few NSE stocks downloaded; not updating")
    _, nok = S.nifty_regime(a.years)

    res, days, PP = {}, {}, {}
    with ProcessPoolExecutor() as ex:
        for key, out, dd, P in ex.map(work, [(k, d, nok) for k, d in data.items()], chunksize=8):
            res[key] = out; days[key] = dd; PP[key] = P
    log.info("signal and same-stock control trades done")

    # control B: for each signal, CONTROLS random other eligible stocks of the same exchange group, entered on the same day
    rng = np.random.default_rng(2024)
    bydate = {}
    for key, dd in days.items():
        for j in np.flatnonzero(dd["ok"] & ~dd["sig"]): bydate.setdefault((grp[key], dd["dates"][j]), []).append((key, j))
    ctrl = {"nse": [], "bse": []}; sig_rows = {"nse": [], "bse": []}
    for key, out in res.items():
        g = grp[key]; P = PP[key]; dts = days[key]["dates"]; pos = {d: j for j, d in enumerate(dts)}
        for row in out["sig"]:
            sig_rows[g].append(row + (key,))
            ed = row[0]; j_e = pos[ed]; sd = dts[j_e - 1]                     # signal day = day before entry
            pool = bydate.get((g, sd), [])
            if not pool: continue
            for idx in rng.choice(len(pool), size=min(CONTROLS, len(pool)), replace=False):
                k2, s2 = pool[idx]; P2 = PP[k2]
                t = trade(P2, s2)
                if t is None or not clean_window(P2, s2 - 60, t["xk"]): continue
                ctrl[g].append((P2["dates"][t["ei"]], round(t["ret"], 5), t["why"], t["days"], row[4]))
    log.info("same-day controls done")

    first = min(min(r[0] for r in v["sig"]) for v in res.values() if v["sig"])
    periods = [("all", "All years", "0000", "9999"), ("before", f"Before {CHOSEN_FROM[:4]} (never used by any earlier test)", "0000", CHOSEN_FROM),
               ("chosen", "Oct 2020 to May 2024 (where the -8%/+20% exit was picked)", CHOSEN_FROM, CHOSEN_TO), ("later", "May 2024 onwards (the earlier fair test)", CHOSEN_TO, "9999")]
    base = {g: [x for k, v in res.items() if grp[k] == g for x in v["base"]] for g in ("nse", "bse")}
    out = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, years=a.years, first_trade=first,
               rule="First day the close is 0 to 5% above a rising 44-day average; buy next open; -8% stop, +20% target, 40 trading days; 0.4% costs.",
               stocks=dict(nse=sum(v == "nse" for v in grp.values()), bse=sum(v == "bse" for v in grp.values())),
               filters=dict(min_price=MIN_PX, min_traded_value=MIN_VAL, jump_lo=JUMP_LO, jump_hi=JUMP_HI, controls_per_signal=CONTROLS), groups={})
    for g in ("nse", "bse", "both"):
        S_ = sig_rows["nse"] + sig_rows["bse"] if g == "both" else sig_rows[g]
        B_ = base["nse"] + base["bse"] if g == "both" else base[g]
        C_ = ctrl["nse"] + ctrl["bse"] if g == "both" else ctrl[g]
        raw = [x for k, v in res.items() if g == "both" or grp[k] == g for x in v["raw"]]
        G = dict(periods={pid: dict(label=lbl, **summarize(S_, B_, C_, lo, hi)) for pid, lbl, lo, hi in periods},
                 regime={k: summarize(S_, B_, C_, pick=f) for k, f in (("nifty_above_200", lambda x: x[4]), ("nifty_below_200", lambda x: not x[4]))},
                 years={}, raw=dict(all_trades=stats([x[1] for x in raw]), excluded_illiquid=sum(1 for x in raw if not x[5]),
                                    excluded_bad_data=len(raw) - sum(1 for x in raw if not x[5]) - len(S_)))
        for y in sorted({x[0][:4] for x in S_}):
            G["years"][y] = summarize(S_, B_, C_, f"{y}-01-01", f"{y}-12-31~")
            G["years"][y] = {k: G["years"][y][k] for k in ("signals", "control_same_day", "edge_vs_same_day", "control_same_stock", "edge_vs_same_stock")}
        out["groups"][g] = G
    # exit grid on NSE signals vs same-day controls (all years), to see whether the exit choice matters
    grid = []
    sig_by = {}
    for r in sig_rows["nse"]: sig_by.setdefault(r[5], []).append(r[0])
    for sp, tp in S.GRID["swing"]:
        A, C = [], []
        rng2 = np.random.default_rng(99)
        for key, eds in sig_by.items():
            P = PP[key]; pos = {d: j for j, d in enumerate(P["dates"])}
            for ed in eds:
                t = trade(P, pos[ed] - 1, sp, tp)
                if t is None: continue
                A.append((ed, t["ret"]))
                pool = bydate.get(("nse", P["dates"][pos[ed] - 1]), [])
                for idx in rng2.choice(len(pool), size=min(CONTROLS, len(pool)), replace=False) if pool else []:
                    k2, s2 = pool[idx]; t2 = trade(PP[k2], s2, sp, tp)
                    if t2 and clean_window(PP[k2], s2 - 60, t2["xk"]): C.append((PP[k2]["dates"][t2["ei"]], t2["ret"]))
        grid.append(dict(stop=sp, target=tp, n=len(A), avg=round(float(np.mean([x[1] for x in A])), 5) if A else None,
                         edge=edge_naive([x[1] for x in A], [x[1] for x in C]), monthly=edge_monthly(A, C)))
    out["grid_nse"] = grid
    (ROOT / "dma44_audit.json").write_text(json.dumps(out, separators=(",", ":")))
    log.info("written dma44_audit.json")


if __name__ == "__main__":
    main()
