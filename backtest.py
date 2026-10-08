"""Backtest the MA crossover rule: buy when close crosses above the MA, sell when it crosses below.
Usage: python screener/backtest.py --top 100 --years 5      (or --symbols RELIANCE,TCS)"""
import argparse, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import ROOT, load_cfg, moving_avg, nse_universe, fetch

def trades(df, kind, n, cost):
    close = df["Close"].dropna()
    m = moving_avg(close, kind, n)
    above = close > m
    ready = m.shift(1).notna()
    up = above & ~above.shift(1, fill_value=False) & ready
    dn = ~above & above.shift(1, fill_value=False) & ready
    out, entry, d0 = [], None, None
    for d in close.index:
        if entry is None and up[d]:
            entry, d0 = close[d], d
        elif entry is not None and dn[d]:
            out.append(dict(entry=d0, exit=d, days=(d - d0).days, ret=close[d] / entry - 1 - cost))
            entry = None
    return out, (close.iloc[-1] / close[close.index > m.dropna().index[0]].iloc[0] - 1) if m.notna().any() else 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols"); ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--years", type=int, default=5); ap.add_argument("--cost", type=float, default=0.002,
                    help="round-trip cost as a fraction (0.002 = 0.2%%)")
    a = ap.parse_args(); c = load_cfg()
    items = [dict(symbol=s, yahoo=s + ".NS") for s in a.symbols.split(",")] if a.symbols else nse_universe()[:a.top]
    raw = fetch([u["yahoo"] for u in items], period=f"{a.years}y")
    data = {u["symbol"]: raw[u["yahoo"]] for u in items if u["yahoo"] in raw}
    rows, bh = [], []
    for s, df in data.items():
        t, b = trades(df, c["ma_type"], c["ma_period"], a.cost)
        rows += [dict(symbol=s, **x) for x in t]; bh.append(b)
    if not rows: print("No trades found"); return
    r = pd.DataFrame(rows); r.to_csv(ROOT / "backtest.csv", index=False)
    w = r[r.ret > 0]
    print(f"{c['ma_type']}-{c['ma_period']} crossover | {len(data)} stocks | {a.years}y | cost {a.cost:.2%}")
    print(f"Trades: {len(r)}   Win rate: {len(w)/len(r):.1%}")
    print(f"Avg return/trade: {r.ret.mean():.2%}   Median: {r.ret.median():.2%}")
    print(f"Avg win: {w.ret.mean():.2%}   Avg loss: {r[r.ret<=0].ret.mean():.2%}   Avg hold: {r.days.mean():.0f} days")
    print(f"Best: {r.ret.max():.1%}   Worst: {r.ret.min():.1%}")
    print(f"Buy-and-hold average over same data: {sum(bh)/len(bh):.1%}")
    print("Past results do not predict future returns. Not financial advice.")

if __name__ == "__main__":
    main()
