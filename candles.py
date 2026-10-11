"""Do classic candlestick patterns still work on Indian stocks? A test of 20 textbook patterns, each in three settings.

Same method as the strategy library (strategies_x.py):
  * every NSE stock at ₹20 or more with trading (about 1,900), about 15 years of daily adjusted prices;
  * the signal is the pattern's last candle, at the close; the trade is bought at the next day's open;
  * a trade counts only if, on the signal day, the price was ₹20+ and the stock traded at least ₹50 lakh a day (20-day median);
  * trades touching a one-day jump beyond -30% / +45% (unadjusted corporate action or bad data) are set aside;
  * each trade is compared with other stocks bought on the SAME day with the same exits (the same-day control),
    which removes the market's own move; 0.4% costs per round trip;
  * the exit (stop / target, 10-day limit) is picked on the years before 2020 only, and judged on 2020 onwards;
  * confidence is judged on monthly averages (stocks signalling on the same day are not independent).

Bullish patterns are judged as buys: did the stock do better than the same-day control?
Bearish patterns are judged as warnings: over the next 10 days (no stop or target), did the stock do worse than the control?

Settings: "alone" is the textbook shape with the textbook prior move (a reversal needs something to reverse);
the two "in context" settings add where the candle appears (bullish: in an uptrend after a dip, or at a rising 44-day average;
bearish: after a run-up, or in a downtrend).

python candles.py            writes candles.json
python candles.py --synthetic   offline smoke test on made-up prices
"""
import argparse, datetime as dt, json, logging, math, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import strategies as S
import dma44_audit as A
import strategies_x as X

log = logging.getLogger("cdl")
ROOT = S.ROOT
COST = X.COST
SPLIT_YEAR = X.SPLIT_YEAR
MAX_HOLD = 10
TIME_ONLY = (99, 99)                       # no stop, no target: sold at the close of the 10th day
EXITS = [(3, 6), (4, 8), (5, 10), (7, 14), TIME_ONLY]
G = {}


# ---------------- the patterns ----------------
def parts(df):
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    up = h - pd.concat([o, c], axis=1).max(axis=1); lo = pd.concat([o, c], axis=1).min(axis=1) - l
    ab = body.shift(1).rolling(10, min_periods=8).mean()          # typical body of the previous 10 days
    bull, bear = c > o, c < o
    fell = c.shift(1) < c.shift(6)                                # textbook prior move: down over the 5 days before
    rose = c.shift(1) > c.shift(6)
    return o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose


def P_hammer(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (lo >= 2 * body) & (up <= 0.1 * rng) & (body <= 0.35 * rng) & (body > 0) & fell
def P_invhammer(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (up >= 2 * body) & (lo <= 0.1 * rng) & (body <= 0.35 * rng) & (body > 0) & fell
def P_bull_engulf(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bear.shift(1) & bull & (o <= c.shift(1)) & (c >= o.shift(1)) & (body > body.shift(1)) & fell
def P_piercing(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    mid = (o.shift(1) + c.shift(1)) / 2
    return bear.shift(1) & (body.shift(1) >= ab) & bull & (o < c.shift(1)) & (c > mid) & (c < o.shift(1)) & fell
def P_bull_harami(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bear.shift(1) & (body.shift(1) >= ab) & bull & (o >= c.shift(1)) & (c <= o.shift(1)) & (body <= 0.5 * body.shift(1)) & fell
def P_morning_star(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    mid2 = (o.shift(2) + c.shift(2)) / 2; top1 = pd.concat([o.shift(1), c.shift(1)], axis=1).max(axis=1)
    return bear.shift(2) & (body.shift(2) >= ab) & (body.shift(1) <= 0.3 * body.shift(2)) & (top1 <= c.shift(2) * 1.002) & bull & (c > mid2) & (c.shift(3) < c.shift(8))
def P_soldiers(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    one = lambda k: bull.shift(k) & (body.shift(k) >= 0.6 * ab) & (up.shift(k) <= 0.3 * rng.shift(k))
    opens_in = lambda k: (o.shift(k) >= o.shift(k + 1)) & (o.shift(k) <= c.shift(k + 1))
    return one(0) & one(1) & one(2) & (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & opens_in(0) & opens_in(1)
def P_dragonfly(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (body <= 0.1 * rng) & (up <= 0.1 * rng) & (lo >= 0.6 * rng) & fell
def P_doji_low(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (body <= 0.05 * rng) & (rng >= 0.8 * (d["High"] - d["Low"]).shift(1).rolling(10).mean()) & fell
def P_bull_marubozu(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bull & (body >= 0.9 * rng) & (body >= 1.5 * ab)
def P_tweezer_bot(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bear.shift(1) & bull & ((l - l.shift(1)).abs() <= 0.002 * c) & fell
def P_three_inside_up(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    har = bear.shift(2) & (body.shift(2) >= ab.shift(1)) & bull.shift(1) & (o.shift(1) >= c.shift(2)) & (c.shift(1) <= o.shift(2)) & (body.shift(1) <= 0.5 * body.shift(2))
    return har & bull & (c > o.shift(2)) & (c.shift(3) < c.shift(8))
def P_shooting_star(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (up >= 2 * body) & (lo <= 0.1 * rng) & (body <= 0.35 * rng) & (body > 0) & rose
def P_hanging_man(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (lo >= 2 * body) & (up <= 0.1 * rng) & (body <= 0.35 * rng) & (body > 0) & rose
def P_bear_engulf(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bull.shift(1) & bear & (o >= c.shift(1)) & (c <= o.shift(1)) & (body > body.shift(1)) & rose
def P_dark_cloud(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    mid = (o.shift(1) + c.shift(1)) / 2
    return bull.shift(1) & (body.shift(1) >= ab) & bear & (o > c.shift(1)) & (c < mid) & (c > o.shift(1)) & rose
def P_bear_harami(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return bull.shift(1) & (body.shift(1) >= ab) & bear & (o <= c.shift(1)) & (c >= o.shift(1)) & (body <= 0.5 * body.shift(1)) & rose
def P_evening_star(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    mid2 = (o.shift(2) + c.shift(2)) / 2; bot1 = pd.concat([o.shift(1), c.shift(1)], axis=1).min(axis=1)
    return bull.shift(2) & (body.shift(2) >= ab) & (body.shift(1) <= 0.3 * body.shift(2)) & (bot1 >= c.shift(2) * 0.998) & bear & (c < mid2) & (c.shift(3) > c.shift(8))
def P_crows(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    one = lambda k: bear.shift(k) & (body.shift(k) >= 0.6 * ab) & (lo.shift(k) <= 0.3 * rng.shift(k))
    opens_in = lambda k: (o.shift(k) <= o.shift(k + 1)) & (o.shift(k) >= c.shift(k + 1))
    return one(0) & one(1) & one(2) & (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & opens_in(0) & opens_in(1)
def P_gravestone(d):
    o, h, l, c, body, rng, up, lo, ab, bull, bear, fell, rose = parts(d)
    return (body <= 0.1 * rng) & (lo <= 0.1 * rng) & (up >= 0.6 * rng) & rose


# id, name, side, candles in the pattern, function, plain description (shown on the page)
PATTERNS = [
    ("hammer", "Hammer", "bull", 1, P_hammer, "After a fall, a small body near the top of the day's range with a long lower shadow at least twice the body: sellers pushed the price down and buyers brought it back."),
    ("invhammer", "Inverted hammer", "bull", 1, P_invhammer, "After a fall, a small body near the bottom of the range with a long upper shadow at least twice the body."),
    ("bull_engulf", "Bullish engulfing", "bull", 2, P_bull_engulf, "After a fall, a red candle followed by a bigger green candle whose body covers the red body."),
    ("piercing", "Piercing line", "bull", 2, P_piercing, "After a fall, a long red candle, then a green candle that opens below the red close and closes above the middle of the red body."),
    ("bull_harami", "Bullish harami", "bull", 2, P_bull_harami, "After a fall, a long red candle followed by a small green candle whose body sits inside the red body."),
    ("morning_star", "Morning star", "bull", 3, P_morning_star, "After a fall, a long red candle, a small candle below it, then a green candle closing above the middle of the first."),
    ("soldiers", "Three white soldiers", "bull", 3, P_soldiers, "Three solid green candles in a row, each opening inside the previous body and closing higher, near the day's high."),
    ("dragonfly", "Dragonfly doji", "bull", 1, P_dragonfly, "After a fall, open and close at about the same price near the day's high, with a long lower shadow."),
    ("doji_low", "Doji after a fall", "bull", 1, P_doji_low, "After a fall, a candle whose open and close are almost the same (indecision), on a normal-sized range."),
    ("bull_marubozu", "Bullish marubozu", "bull", 1, P_bull_marubozu, "A long green candle with almost no shadows: it opened near the low and closed near the high."),
    ("tweezer_bot", "Tweezer bottom", "bull", 2, P_tweezer_bot, "After a fall, a red candle and a green candle with the same low (within 0.2%)."),
    ("three_inside_up", "Three inside up", "bull", 3, P_three_inside_up, "A bullish harami followed by a third green candle closing above the first candle's open."),
    ("shooting_star", "Shooting star", "bear", 1, P_shooting_star, "After a rise, a small body near the bottom of the range with a long upper shadow at least twice the body: buyers pushed up and sellers took it back."),
    ("hanging_man", "Hanging man", "bear", 1, P_hanging_man, "After a rise, the hammer shape: small body near the top, long lower shadow."),
    ("bear_engulf", "Bearish engulfing", "bear", 2, P_bear_engulf, "After a rise, a green candle followed by a bigger red candle whose body covers the green body."),
    ("dark_cloud", "Dark cloud cover", "bear", 2, P_dark_cloud, "After a rise, a long green candle, then a red candle that opens above the green close and closes below the middle of the green body."),
    ("bear_harami", "Bearish harami", "bear", 2, P_bear_harami, "After a rise, a long green candle followed by a small red candle whose body sits inside the green body."),
    ("evening_star", "Evening star", "bear", 3, P_evening_star, "After a rise, a long green candle, a small candle above it, then a red candle closing below the middle of the first."),
    ("crows", "Three black crows", "bear", 3, P_crows, "Three solid red candles in a row, each opening inside the previous body and closing lower, near the day's low."),
    ("gravestone", "Gravestone doji", "bear", 1, P_gravestone, "After a rise, open and close at about the same price near the day's low, with a long upper shadow."),
]


def contexts(d):
    c, l = d["Close"], d["Low"]; m44, m200 = S.sma(c, 44), S.sma(c, 200)
    return {
        "alone": pd.Series(True, index=d.index),
        "uptrend": (c > m200) & (m200 > m200.shift(20)),                                  # bullish: in a rising long-term trend (the pattern itself needs a dip)
        "dma44": (l <= m44 * 1.01) & (c >= m44 * 0.99) & (m44 > m44.shift(5)),             # bullish: touching a rising 44-day average
        "runup": c.shift(1) >= c.shift(11) * 1.08,                                          # bearish: up 8% or more in the 10 days before
        "downtrend": (c < m200) & (m200 < m200.shift(20)),                                  # bearish: in a falling long-term trend
    }


CTX = {"bull": ["alone", "uptrend", "dma44"], "bear": ["alone", "runup", "downtrend"]}
CTX_NAME = {"alone": "On its own", "uptrend": "In an uptrend (above a rising 200-day average)", "dma44": "At a rising 44-day average",
            "runup": "After a run-up (8%+ in 10 days)", "downtrend": "In a downtrend (below a falling 200-day average)"}
RULES = [(f"{pid}:{cx}", pid, cx) for pid, nm, side, k, fn, ds in PATTERNS for cx in CTX[side]]
PMAP = {p[0]: p for p in PATTERNS}


def signals(df):
    cx = contexts(df); out = {}
    for pid, nm, side, k, fn, ds in PATTERNS:
        try: base = fn(df).fillna(False).astype(bool)
        except Exception: continue
        for c in CTX[side]: out[f"{pid}:{c}"] = (base & cx[c].fillna(False)).to_numpy(bool)
    return out


# ---------------- the test (pass 1: control; pass 2: patterns) ----------------
def base_work(args):
    key, df = args
    P, o, h, l, c = X.stock_arrays(df); n = len(o); out = {}
    for g in EXITS:
        tr = X.fast_trades(o, h, l, c, range(60, n - 1, 5), g[0], g[1], MAX_HOLD, overlap=True)
        out[g] = [(P["dates"][e], r - COST) for s, e, x, r, w in tr if P["elig"][s] and A.clean_window(P, s - 60, x)]
    return key, out


def init(dates, base_mean):
    X.init(dates, base_mean); G.update(X.G)


def sig_work(args):
    key, df = args
    P, o, h, l, c = X.stock_arrays(df)
    d2i, base, y2i, m2i = G["d2i"], G["base"], G["y2i"], G["m2i"]
    gi = [d2i.get(d) for d in P["dates"]]
    res, ny, nm, today = {}, len(y2i), len(m2i), []
    sig = signals(df); last = len(o) - 1
    for rid, pid, cx in RULES:
        if rid not in sig: continue
        en = np.flatnonzero(sig[rid])
        if len(en) and en[-1] == last and P["elig"][last]: today.append(rid)
        exits = EXITS if PMAP[pid][2] == "bull" else [TIME_ONLY]
        for g in exits:
            tr = X.fast_trades(o, h, l, c, en, g[0], g[1], MAX_HOLD)
            if not tr: continue
            Y = np.zeros((ny, X.NF)); M = np.zeros((nm, 3)); bm = base[g]
            for s, e, x, r, w in tr:
                if not P["elig"][s] or not A.clean_window(P, s - 60, x): continue
                r -= COST; d = P["dates"][e]; yi, mi = y2i[d[:4]], m2i[d[:7]]; j = gi[e]
                b = bm[j] if j is not None and bm[j] == bm[j] else None
                row = Y[yi]; row[0] += 1; row[1] += r; row[2] += r * r; row[3] += r > 0; row[4] += max(r, 0); row[5] += min(r, 0); row[8 + w] += 1
                if b is not None:
                    df_ = r - b; row[6] += df_; row[7] += df_ * df_; row[11] += 1; M[mi, 0] += 1; M[mi, 1] += df_
                M[mi, 2] += r
            res[(rid, g)] = (Y, M)
    return key, res, today


def verdict(side, tr, te, mt, yrs):
    """plain verdict from the later (2020+) period, the earlier period and the monthly t"""
    if not te or te["n"] < 100 or te.get("edge") is None: return "few", "Too few trades from 2020 on to judge"
    e, t, e0 = te["edge"], (mt or {}).get("t"), (tr or {}).get("edge")
    ty = [v for y, v in yrs.items() if int(y) >= SPLIT_YEAR and v["n"] >= 30 and v.get("edge") is not None]
    if side == "bull":
        good = sum(1 for v in ty if v["edge"] > 0)
        if e > 0 and t is not None and t >= 2 and (e0 or 0) > 0: return "works", f"Better than the same-day control from 2020 on, month after month (how sure {t}), and also before 2020; better in {good} of {len(ty)} years"
        if e > 0 and t is not None and t >= 1: return "weak", f"A little better than the control from 2020 on, but not reliably (how sure {t})"
        if e < 0 and t is not None and t <= -2: return "worse", f"Did worse than the control from 2020 on (how sure {t}): the opposite of what the pattern promises"
        return "none", f"No real difference from the control from 2020 on (how sure {t})"
    bad = sum(1 for v in ty if v["edge"] < 0)
    if e < 0 and t is not None and t <= -2 and (e0 or 0) < 0: return "works", f"Stocks did worse than the control over the next 10 days, month after month (how sure {t}), and also before 2020; worse in {bad} of {len(ty)} years"
    if e < 0 and t is not None and t <= -1: return "weak", f"Stocks did a little worse than the control, but not reliably (how sure {t})"
    if e > 0 and t is not None and t >= 2: return "worse", f"Stocks did better than the control afterwards (how sure {t}): the opposite of the warning"
    return "none", f"No real difference from the control (how sure {t})"


def synthetic():
    rng = np.random.default_rng(3); d = pd.bdate_range("2011-01-03", "2026-10-09"); out = {}
    for i in range(80):
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(d)))); o = c * np.exp(rng.normal(0, 0.008, len(d)))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.008, len(d)))); l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.008, len(d))))
        out[f"NSE:S{i:02d}"] = pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, Volume=rng.integers(2e5, 2e6, len(d)).astype(float)), index=d)
    return out, str(d[-1].date())


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--nse", type=int, default=2600); ap.add_argument("--years", type=int, default=15)
    ap.add_argument("--synthetic", action="store_true"); ap.add_argument("--out", default="candles.json"); a = ap.parse_args()
    if a.synthetic: data, day = synthetic()
    else:
        import dma44_deep as DD
        nse, _, day = DD.universes(a.nse, 0); data, _ = DD.fetch_all(nse, [], a.years)
        if len(data) < int(os.environ.get("SX_MIN", 400)): raise SystemExit("too few stocks downloaded; not updating")
    for k, df in data.items():
        if getattr(df.index, "tz", None) is not None: df.index = df.index.tz_localize(None)
    log.info("stocks: %d", len(data))
    dates = sorted({x for df in data.values() for x in df.index.strftime("%Y-%m-%d")}); d2i = {d: i for i, d in enumerate(dates)}
    bsum = {g: np.zeros(len(dates)) for g in EXITS}; bcnt = {g: np.zeros(len(dates)) for g in EXITS}
    with ProcessPoolExecutor() as ex:
        for key, out in ex.map(base_work, data.items(), chunksize=16):
            for g, rows in out.items():
                for d, r in rows: j = d2i[d]; bsum[g][j] += r; bcnt[g][j] += 1
    base_mean = {g: np.where(bcnt[g] >= 5, bsum[g] / np.maximum(bcnt[g], 1), np.nan) for g in EXITS}
    log.info("control trades: %d", int(sum(v.sum() for v in bcnt.values())))
    years = sorted({d[:4] for d in dates}); months = sorted({d[:7] for d in dates})
    acc, today = {}, {}
    with ProcessPoolExecutor(initializer=init, initargs=(dates, base_mean)) as ex:
        for key, res, td in ex.map(sig_work, data.items(), chunksize=8):
            for sg, (Y, M) in res.items():
                if sg in acc: acc[sg][0] += Y; acc[sg][1] += M; acc[sg][2] += 1
                else: acc[sg] = [Y.copy(), M.copy(), 1]
            for rid in td: today.setdefault(rid, []).append(key.split(":", 1)[1])
    yi_tr = [i for i, y in enumerate(years) if int(y) < SPLIT_YEAR]; yi_te = [i for i, y in enumerate(years) if int(y) >= SPLIT_YEAR]
    mi_te = [i for i, m in enumerate(months) if int(m[:4]) >= SPLIT_YEAR]
    nyears_te = max(1, len({y for y in years if int(y) >= SPLIT_YEAR}))
    rules = []
    for rid, pid, cx in RULES:
        p = PMAP[pid]; side = p[2]; exits = EXITS if side == "bull" else [TIME_ONLY]; best = None; grid = []
        for g in exits:
            if (rid, g) not in acc: continue
            Y, M, _ = acc[(rid, g)]; tr, te = X.summ(Y[yi_tr].sum(0)), X.summ(Y[yi_te].sum(0))
            grid.append(dict(stop=g[0], target=g[1], train_edge=tr and tr.get("edge"), test_edge=te and te.get("edge"), test_n=te and te["n"]))
            if tr and tr["n"] >= 100 and tr.get("edge") is not None and (best is None or tr["edge"] > best[0]): best = (tr["edge"], g)
        if best is None and grid: best = (None, exits[-1])
        if best is None: continue
        g = best[1]; Y, M, nst = acc[(rid, g)]
        yrs = {y: s for i, y in enumerate(years) if (s := X.summ(Y[i]))}
        trn, tst, mt = X.summ(Y[yi_tr].sum(0)), X.summ(Y[yi_te].sum(0)), X.monthly_t(M[mi_te])
        tm = (rid, TIME_ONLY); t10 = X.summ(acc[tm][0][yi_te].sum(0)) if tm in acc else None
        v, why = verdict(side, trn, tst, mt, yrs)
        rules.append(dict(id=rid, pattern=pid, ctx=cx, side=side, exit=dict(stop=g[0], target=g[1], max_hold=MAX_HOLD, time_only=g == TIME_ONLY),
                          train=trn, test=tst, monthly_test=mt, hold10=t10, years=yrs, grid=grid, per_year=round((tst or {}).get("n", 0) / nyears_te),
                          verdict=v, why=why, today=sorted(today.get(rid, []))[:60], today_n=len(today.get(rid, [])),
                          stars=X.rate_x(trn, tst, mt, yrs)[0] if side == "bull" else None))
    out = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), price_date=day, stocks=len(data), first_date=dates[0], split_year=SPLIT_YEAR, cost_pct=COST * 100,
               max_hold=MAX_HOLD, exits=[list(g) for g in EXITS], synthetic=bool(a.synthetic),
               filters=dict(min_price=A.MIN_PX, min_traded_value=A.MIN_VAL, jump_lo=A.JUMP_LO, jump_hi=A.JUMP_HI),
               patterns=[dict(id=p[0], name=p[1], side=p[2], candles=p[3], text=p[5]) for p in PATTERNS], contexts=CTX_NAME, rules=rules)
    (ROOT / a.out).write_text(json.dumps(out, separators=(",", ":")))
    cnt = {}
    for r in rules: cnt[(r["side"], r["verdict"])] = cnt.get((r["side"], r["verdict"]), 0) + 1
    print("::notice::verdicts " + json.dumps({f"{k[0]}/{k[1]}": v for k, v in sorted(cnt.items())}))
    ok = [r["id"] for r in rules if r["verdict"] in ("works", "weak")]
    print("::notice::working or weak: " + ", ".join(ok))


if __name__ == "__main__":
    main()
