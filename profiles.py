"""Company profiles for the stock pages: what the company does, sector and industry, size and where it is based.

python profiles.py      writes profiles.json (weekly; the descriptions change rarely)

Source: Yahoo Finance's company profile (the business description it carries for each listed company), fetched with yfinance.
Covers the shares the app tracks closely: the covered list (fund.json) plus every share with an outlook estimate.
Nothing here is analysis; it is the company's own business description and basic facts, shown with the source named.
"""
import datetime as dt, json, logging, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("prof")


def one(sym):
    import yfinance as yf
    for attempt in range(3):
        try:
            info = yf.Ticker(sym + ".NS").get_info() or {}
            d = (info.get("longBusinessSummary") or "").strip()
            if not d and not info.get("industry"): return sym, None
            return sym, dict(d=d[:1600], ind=info.get("industry"), sec=info.get("sector"), emp=info.get("fullTimeEmployees"),
                             web=info.get("website"), city=info.get("city"), n=info.get("longName") or info.get("shortName"))
        except Exception as e:
            if "Too Many" in str(e) or "429" in str(e): time.sleep(20 * (attempt + 1))
            else: time.sleep(2)
    return sym, None


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    syms = set()
    try: syms |= set(json.loads((ROOT / "fund.json").read_text()).get("stocks", {}))
    except Exception: pass
    try: syms |= {s for s, r in json.loads((ROOT / "stock_outlook.json").read_text()).get("s", {}).items() if r.get("o")}
    except Exception: pass
    old = {}
    try: old = json.loads((ROOT / "profiles.json").read_text()).get("s", {})
    except Exception: pass
    syms = sorted(syms); out, t0 = {}, time.time()
    log.info("profiles for %d shares", len(syms))
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(one, s) for s in syms]
        for k, fu in enumerate(futs):
            left = 1800 - (time.time() - t0)
            if left <= 0: log.warning("time budget reached at %d", k); break
            try:
                s, o = fu.result(timeout=max(1, left))
                if o: out[s] = o
            except Exception: pass
            if k % 200 == 0: log.info("%d/%d", k, len(syms))
        for fu in futs: fu.cancel()
    for s, o in old.items():          # keep last week's profile for any share this run could not reach
        out.setdefault(s, o)
    if len(out) < 100: raise SystemExit("too few profiles; not updating")
    (ROOT / "profiles.json").write_text(json.dumps(dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(), source="Yahoo Finance company profile", s=out), separators=(",", ":"), ensure_ascii=False))
    print(f"::notice::profiles: {len(out)} shares, {sum(1 for o in out.values() if o.get('d'))} with a description, {(ROOT / 'profiles.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
