"""Market and stock insights: plain numbers plus rule-based readings, each tied to the NISM workbook section it comes from.

python insights.py               daily: market, sectors, global, news headlines, technical readings for the covered stocks
python insights.py --fund        also refresh company financials (slow; run weekly, or automatically when older than 6 days)

Writes insights.json (market page) and fund.json (per-stock numbers).
Nothing here is a recommendation. Readings say what a number is and what the cited NISM text says such a number usually indicates.
"""
import argparse, datetime as dt, html, json, logging, re, time, email.utils
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import strategies as S

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("ins")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

INDIA = [("^NSEI", "Nifty 50"), ("^BSESN", "Sensex"), ("^NSEBANK", "Nifty Bank"), ("^NSEMDCP50", "Nifty Midcap 50"), ("^INDIAVIX", "India VIX")]
GLOBAL = [("^GSPC", "S&P 500 (US)"), ("^IXIC", "Nasdaq (US)"), ("^FTSE", "FTSE 100 (UK)"), ("^GDAXI", "DAX (Germany)"), ("^N225", "Nikkei 225 (Japan)"),
          ("^HSI", "Hang Seng (Hong Kong)"), ("000001.SS", "Shanghai Composite (China)")]
MACRO = [("INR=X", "US dollar in rupees"), ("DX-Y.NYB", "US dollar index"), ("BZ=F", "Brent crude ($ a barrel)"), ("GC=F", "Gold ($ an ounce)"),
         ("HG=F", "Copper ($ a pound)"), ("^TNX", "US 10-year bond yield (%)")]
SECTORS = [("^CNXIT", "IT"), ("^NSEBANK", "Banks"), ("^CNXAUTO", "Auto"), ("^CNXFMCG", "FMCG"), ("^CNXPHARMA", "Pharma"), ("^CNXMETAL", "Metal"),
           ("^CNXREALTY", "Realty"), ("^CNXENERGY", "Energy"), ("^CNXPSUBANK", "PSU banks"), ("^CNXINFRA", "Infrastructure"), ("^CNXMEDIA", "Media"),
           ("NIFTY_FIN_SERVICE.NS", "Financial services")]

# NISM references used in the readings (workbook, section, what the section says) -- shown on the page
REFS = {
    "trend": ("NISM Series XV (Research Analyst) workbook, §15.4 Understanding Market Trends", "A primary trend is the long movement of a year or more: bull (sustained rise), bear (prolonged decline) or sideways. 50- or 100-day averages, trendlines, MACD and higher highs / higher lows are listed as the tools to identify it."),
    "dow": ("NISM Series XV, §15.3 The Dow Theory", "Six tenets, including: the market has three trends (primary, secondary, minor); indices must confirm each other (Nifty and Sensex should move together); volume should rise in the direction of the trend; a trend stays in force until a clear reversal."),
    "ma": ("NISM Series XV, §15.9.1 Moving Averages", "When the average points up the trend is up. When a stock trades at or near a rising average this could be a good time to buy, and vice versa. Price > 13 EMA > 21 EMA > 34 EMA describes an uptrend; the reverse a downtrend."),
    "macd": ("NISM Series XV, §15.9.2 MACD", "MACD = 12-day EMA minus 26-day EMA; the signal line is its 9-day EMA. An uptrend is likely to continue while MACD is above the signal line and both are rising. The zero line separates confirmed bull and bear phases."),
    "rsi": ("NISM Series XV, §15.9.3 RSI", "Above 70 is usually called overbought and below 30 oversold. In a bull market RSI rarely falls below 44-45; in a bear market it rarely rises above 50-55. RSI can stay overbought or oversold for long periods in strong trends."),
    "adx": ("NISM Series XV, §15.9.4 ADX", "ADX measures trend strength, not direction. Below 25 is a weak or no trend; a rising ADX above 25 is a strong trend. +DMI above -DMI with a rising ADX is described as a buy signal; avoid crossovers when ADX is weak."),
    "rsc": ("NISM Series XV, §15.9.5 Relative Strength Comparative", "Compares a stock (or sector) with a benchmark such as the Nifty 50, normalised to 100: above 100 means it is outperforming, below 100 underperforming."),
    "obv": ("NISM Series XV, §15.9.6 On Balance Volume", "OBV adds volume on up days and subtracts it on down days. It should rise with rising prices; OBV above its 20-period average with a fresh upturn is read as fresh momentum."),
    "sr": ("NISM Series XV, §15.7 Support and Resistance", "Support is a level where a fall tends to pause, resistance where a rise tends to pause. Moving averages act as dynamic support and resistance; breakouts need volume confirmation."),
    "commod_eq": ("NISM Series XV, §4.10 Impact of commodity market on equity market", "Rising commodity prices raise input costs and squeeze margins of companies that use them; falling prices help. Rising crude helps oil producers and hurts airlines and logistics. A fall in copper may signal slowing industrial demand, dragging metal and infrastructure stocks."),
    "intl": ("NISM Series XV, §11.4 International and domestic markets", "Crude oil prices on international exchanges directly affect fuel prices and inflation in importing countries like India. A weaker rupee makes imports more expensive and amplifies global price rises."),
    "dollar": ("NISM Series XV, §11.3 Currency and dollar index", "Most commodities are priced in US dollars. A stronger dollar usually reduces global demand and pushes commodity prices down; a weaker dollar supports them. Weak emerging-market currencies raise the cost of imported commodities."),
    "macro_ind": ("NISM Series XV, §11.7 Macroeconomic indicators and commodities", "Rising inflation typically pushes investors toward precious metals like gold as a hedge. Higher interest rates strengthen currencies and often reduce commodity prices."),
    "geo": ("NISM Series XV, §11.8 Government policies and geopolitical impacts", "Conflicts in oil-producing regions often disrupt supply and lift crude prices. Trade wars and sanctions restrict the flow of energy, metals and farm goods. Tensions over shipping routes or pipelines add a risk premium."),
    "cad": ("NISM Series XV, §5.3.6 Fiscal policy, balance of payments", "A high current account deficit weakens the currency, makes imports and capital goods dearer and foreign borrowing costlier. A weaker currency makes exports more competitive."),
    "fpi": ("NISM Series XV, §5.3.5 FDI and FPI flows", "Foreign portfolio money is considered 'hot money' because it can be pulled out at any time, which can create systemic risk; FDI is long-term and stable."),
    "rates": ("NISM Series XV, §5.3.3 Inflation and interest rates", "Higher rates reduce investment and can slow the economy; real estate and auto are hit harder because buyers borrow. Higher inflation reduces discretionary income and demand across the board."),
    "global": ("NISM Series XV, §5.3.9 Globalisation", "Integrated economies mean a problem in one part of the world affects other parts; the 2008 US credit crisis is the example given."),
    "emh": ("NISM Series XXI-B (Portfolio Managers) workbook, §13.2 Efficient markets", "In the semi-strong form of market efficiency, prices already reflect all public information such as results, dividends, corporate restructuring, economic and political news, so acting on news after it is public should not give above-average risk-adjusted returns. The evidence is mixed."),
    "bias": ("NISM Series XV, §12.10 Behavioural biases", "Herd mentality, confirmation bias, anchoring, loss aversion and projection bias (projecting the recent past far into the future) are listed as the main biases investors should guard against."),
    "pe": ("NISM Series XV, §10.7.2 Price to Earnings", "All else equal, a P/E above the peer group and the market is considered expensive and below it undervalued; but companies with higher growth or lower risk should trade at a premium, and lower growth or higher risk at a discount."),
    "peg": ("NISM Series XV, §10.7.3 PEG ratio", "P/E divided by the growth rate. Peter Lynch's rule of thumb: below 1 may be treated as undervalued. A rule of thumb may not suit every case; compare PEG across peers."),
    "ev": ("NISM Series XV, §10.7.4-10.7.5 EV/EBITDA and EV/Sales", "Neutral to the capital structure; lower is cheaper all else equal, with premiums for growth or lower risk. P/E and EV/EBITDA cannot be used when profits are negative; EV/Sales then helps, if a turnaround is likely."),
    "dy": ("NISM Series XV, §10.7.1 Dividend yield", "Dividend per share / price. A high dividend yield can look like value but may reflect limited growth avenues; compare it with company fundamentals."),
    "pb": ("NISM Series XV, §10.8 Asset-based valuation", "Price to book compares the price with the balance-sheet value of equity; read it together with ROE."),
    "roe": ("NISM Series XV, §8.11.2 Return ratios", "ROE = profit after tax / net worth, 'the single most important parameter for an equity investor to start digging'. Higher is better. ROCE = EBIT / capital employed."),
    "dupont": ("NISM Series XV, §8.12 DuPont analysis", "ROE = net margin x asset turnover x leverage. A higher ROE from margin or efficiency is a reason to cheer; from higher leverage it brings higher risk."),
    "margin": ("NISM Series XV, §8.11.1 Profitability ratios", "EBITDA margin and PAT margin. A higher margin than peers indicates greater efficiency; a trend of rising margins means improving profitability; very high margins rarely last as competitors enter."),
    "de": ("NISM Series XV, §8.11.3 Leverage ratios", "High debt is risky in a downturn. On a most conservative basis a debt/equity of 1 or less is the benchmark, then judge by industry, track record and capital needs."),
    "icr": ("NISM Series XV, §8.11.3 Interest coverage", "EBIT / interest. A high ratio is comfortable; below 1 or negative means earnings do not cover interest, and such businesses may get into significant problems if they do not turn around."),
    "cr": ("NISM Series XV, §8.11.4 Liquidity ratios", "Current ratio = current assets / current liabilities. Above 1 means current assets exceed current liabilities. Below 1 is not always a red flag: companies with bargaining power often run on customers' money."),
    "growth": ("NISM Series XV, §8.13 Forecasting and §10.7.2", "Investors pay higher P/E for above-average expected growth. Past trends are facts; future trends are only assumptions."),
    "promoter": ("NISM Series XV, §7.6.3 Promoter holdings", "Track the promoter group's shareholding and its changes. Pledging is not necessarily a governance concern, but a high pledged share can aggravate falls if lenders sell."),
    "peer": ("NISM Series XV, §8.14 Peer comparison", "Ratios compared with companies of the same sector show where the company stands against peers; peer comparison is critical before any research report."),
    "beta": ("NISM Series XV, §12.5 Market risk (beta)", "Beta measures how much a stock tends to move with the market; above 1 moves more than the market, below 1 less."),
    "corp": ("NISM Series XV, Chapter 9 Corporate actions", "Dividends, rights, bonus, splits, buybacks, mergers, demergers and delisting change the share count or structure and need to be read for their effect on value."),
    "eic": ("NISM Series X-A (Investment Adviser Level 1), §8.5 Equity research and stock selection", "Fundamental analysis covers Economy, Industry and Company (E-I-C). Top-down starts with the economy, then industries, then companies; bottom-up starts with the company."),
}

NEWS_Q = {
    "market": ["Sensex Nifty stock market", "RBI repo rate monetary policy", "FPI FII flows Indian equities", "India inflation CPI GDP growth", "SEBI order", "India quarterly results earnings"],
    "global": ["geopolitical tensions oil prices", "US Federal Reserve interest rates", "tariffs trade war", "sanctions war conflict markets", "China economy stocks", "OPEC crude output"],
}
FEEDS = {"market": ["https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "https://www.livemint.com/rss/markets", "https://www.moneycontrol.com/rss/marketreports.xml"]}
TAGS = [("Results", r"\b(q[1-4]|quarter|results?|earnings|profit|revenue|net loss|ebitda)\b"), ("RBI / rates", r"\b(rbi|repo|monetary policy|rate cut|rate hike|mpc)\b"),
        ("Inflation", r"\b(inflation|cpi|wpi)\b"), ("Foreign flows", r"\b(fpi|fii|foreign investors?|outflows?|inflows?)\b"), ("Crude / energy", r"\b(crude|oil|opec|brent|gas)\b"),
        ("Currency", r"\b(rupee|dollar|forex|currency)\b"), ("US Fed", r"\b(fed|federal reserve|powell|treasury)\b"), ("Trade / tariffs", r"\b(tariffs?|trade war|trade deal|exports?|imports?)\b"),
        ("Conflict", r"\b(war|attack|missile|conflict|military|strike[sd]?|ceasefire|tensions?)\b"), ("Sanctions", r"\bsanction"), ("Elections / politics", r"\b(election|poll|parliament|government|minister|budget)\b"),
        ("China", r"\bchina|chinese|beijing\b"), ("Regulator", r"\b(sebi|regulator|penalty|ban|probe|nclt|court)\b"), ("IPO / fundraise", r"\b(ipo|qip|listing|fund ?rais|rights issue|ofs)\b"),
        ("Corporate action", r"\b(dividend|bonus|split|buyback|merger|demerger|acquisition|acquire|stake)\b"), ("Orders / deals", r"\b(order|contract|deal|wins?|bags?)\b"),
        ("Ratings / brokers", r"\b(rating|upgrade|downgrade|target price|brokerage|buy call|sell call)\b"), ("Management", r"\b(ceo|cfo|md|chairman|resign|appoint)\b")]


def tag(title):
    t = title.lower(); return [nm for nm, rx in TAGS if re.search(rx, t)][:3]


def parse_rss(xml, default_src=""):
    out = []
    for it in re.findall(r"<item\b.*?</item>", xml, re.S | re.I):
        g = lambda k: (re.search(rf"<{k}\b[^>]*>(.*?)</{k}>", it, re.S | re.I) or [None, ""])[1]
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", g("title"))).strip()
        link = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", g("link"))).strip()
        src = html.unescape(re.sub(r"<[^>]+>", "", g("source"))).strip() or default_src
        pd_ = g("pubDate").strip(); ts = None
        try: ts = email.utils.parsedate_to_datetime(pd_).astimezone(dt.timezone.utc).isoformat()
        except Exception: pass
        if src and title.endswith(" - " + src): title = title[: -len(src) - 3]
        if title and link.startswith("http"): out.append(dict(t=title[:220], u=link[:600], s=src[:60], d=ts))
    return out


def gnews(q, days=4):
    u = "https://news.google.com/rss/search"
    r = requests.get(u, params=dict(q=f"{q} when:{days}d", hl="en-IN", gl="IN", ceid="IN:en"), headers=UA, timeout=25); r.raise_for_status()
    return parse_rss(r.text)


def collect_news():
    out = {}
    for k, qs in NEWS_Q.items():
        items = []
        for q in qs:
            try: items += [dict(x, q=q) for x in gnews(q)]
            except Exception as e: log.warning("news %s: %s", q, str(e)[:80])
            time.sleep(1)
        for f in FEEDS.get(k, []):
            try:
                r = requests.get(f, headers=UA, timeout=25); r.raise_for_status()
                src = re.sub(r"^www\.", "", requests.utils.urlparse(f).netloc).split(".")[0].title()
                items += [dict(x, q="feed") for x in parse_rss(r.text, src)]
            except Exception as e: log.warning("feed %s: %s", f, str(e)[:80])
        seen, uniq = set(), []
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5)).isoformat()
        nowi = dt.datetime.now(dt.timezone.utc)
        for x in items:   # some feeds label Indian time as UTC: a time in the future is shifted back by 5h30
            try:
                d_ = dt.datetime.fromisoformat(x["d"]) if x.get("d") else None
                if d_ and d_ > nowi + dt.timedelta(minutes=10): x["d"] = (d_ - dt.timedelta(minutes=330)).isoformat()
            except Exception: pass
        for x in sorted(items, key=lambda x: x.get("d") or "", reverse=True):
            key = re.sub(r"\W+", "", x["t"].lower())[:70]
            if key in seen or (x.get("d") and x["d"] < cutoff): continue
            x["g"] = tag(x["t"])
            if k == "global" and not x["g"]: continue          # untagged world items are mostly unrelated noise
            seen.add(key); uniq.append(x)
        out[k] = uniq[:60]
    return out


# ---------------- price series ----------------
def yfdl(tickers, period="2y"):
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i + 40]
        for attempt in range(2):
            try:
                d = yf.download(chunk, period=period, interval="1d", group_by="ticker", threads=True, progress=False, auto_adjust=True)
                for t in chunk:
                    try:
                        try: x = d[t]
                        except KeyError:
                            if len(chunk) > 1: raise
                            x = d
                        if hasattr(x.columns, "levels"): x.columns = x.columns.get_level_values(-1)
                        x = x[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                        if len(x) > 30:
                            if getattr(x.index, "tz", None) is not None: x.index = x.index.tz_localize(None)
                            out[t] = x
                    except Exception: pass
                break
            except Exception as e: log.warning("download retry %s", str(e)[:80]); time.sleep(3)
    return out


def ret(c, n):
    return None if len(c) <= n or not c.iloc[-1 - n] else round(float(c.iloc[-1] / c.iloc[-1 - n] - 1) * 100, 2)


def series_stats(df):
    c = df["Close"].dropna(); m50, m200 = S.sma(c, 50), S.sma(c, 200)
    f = lambda v: None if v is None or not np.isfinite(v) else round(float(v), 4)
    return dict(last=f(c.iloc[-1]), d1=ret(c, 1), w1=ret(c, 5), m1=ret(c, 21), m3=ret(c, 63), y1=ret(c, 252),
                vs50=f((c.iloc[-1] / m50.iloc[-1] - 1) * 100) if len(c) >= 50 else None, vs200=f((c.iloc[-1] / m200.iloc[-1] - 1) * 100) if len(c) >= 200 else None,
                s200=f((m200.iloc[-1] / m200.iloc[-21] - 1) * 100) if len(c) >= 221 else None,
                hi52=f((c.iloc[-1] / c.tail(252).max() - 1) * 100), lo52=f((c.iloc[-1] / c.tail(252).min() - 1) * 100),
                spark=[round(float(x), 2) for x in c.tail(60)], date=str(c.index[-1].date()))


def tech(df, nifty=None):
    """technical readings for one stock (the page recomputes the same numbers for stocks outside the list)"""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    n = len(c); f = lambda x: None if x is None or not np.isfinite(x) else round(float(x), 2)
    last = lambda s: f(s.iloc[-1]) if len(s) else None
    sm = lambda k: S.sma(c, k)
    o = dict(p=f(c.iloc[-1]), d1=ret(c, 1), m1=ret(c, 21), m3=ret(c, 63), m6=ret(c, 126), y1=ret(c, 252), date=str(c.index[-1].date()))
    for k in (20, 44, 50, 200):
        o[f"vs{k}"] = f((c.iloc[-1] / sm(k).iloc[-1] - 1) * 100) if n >= k else None
    o["s44"] = f((sm(44).iloc[-1] / sm(44).iloc[-6] - 1) * 100) if n >= 50 else None
    o["s200"] = f((sm(200).iloc[-1] / sm(200).iloc[-21] - 1) * 100) if n >= 221 else None
    o["rsi"] = last(S.rsi(c))
    macd = S.ema(c, 12) - S.ema(c, 26); sig = S.ema(macd, 9)
    o["macd"], o["msig"] = last(macd), last(sig); o["mup"] = bool(macd.iloc[-1] > macd.iloc[-2]) if n > 30 else None; o["sup"] = bool(sig.iloc[-1] > sig.iloc[-2]) if n > 30 else None
    if n > 40:
        adx, pdi, mdi = S.adx_di(df); o["adx"], o["pdi"], o["mdi"] = last(adx), last(pdi), last(mdi); o["adxup"] = bool(adx.iloc[-1] > adx.iloc[-6]) if np.isfinite(adx.iloc[-6]) else None
    e13, e21, e34 = S.ema(c, 13).iloc[-1], S.ema(c, 21).iloc[-1], S.ema(c, 34).iloc[-1]; p = c.iloc[-1]
    o["ema"] = "up" if p > e13 > e21 > e34 else "down" if p < e13 < e21 < e34 else "mixed"
    o["hi52"] = f((p / c.tail(252).max() - 1) * 100); o["lo52"] = f((p / c.tail(252).min() - 1) * 100)
    o["volx"] = f(v.iloc[-1] / v.shift(1).rolling(20).mean().iloc[-1]) if n > 21 and v.shift(1).rolling(20).mean().iloc[-1] else None
    obv = (np.sign(c.diff().fillna(0)) * v).cumsum(); o["obv"] = bool(obv.iloc[-1] > obv.rolling(20).mean().iloc[-1]) if n > 21 else None
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1); o["atr"] = f(tr.rolling(14).mean().iloc[-1] / p * 100) if n > 15 else None
    o["lo20"], o["hi20"] = f(l.tail(20).min()), f(h.tail(20).max())
    if nifty is not None:
        nn = nifty.reindex(c.index).ffill(); r = c / nn
        if len(r.dropna()) > 130 and np.isfinite(r.iloc[-127]): o["rsc"] = f(r.iloc[-1] / r.iloc[-127] * 100)
        if len(r.dropna()) > 253 and np.isfinite(r.iloc[-253]): o["rsc1y"] = f(r.iloc[-1] / r.iloc[-253] * 100)
    return o


# ---------------- fundamentals ----------------
FKEYS = dict(mcap="marketCap", pe="trailingPE", fpe="forwardPE", pb="priceToBook", evebitda="enterpriseToEbitda", evs="enterpriseToRevenue", roe="returnOnEquity",
             roa="returnOnAssets", de="debtToEquity", cr="currentRatio", qr="quickRatio", npm="profitMargins", opm="operatingMargins", ebm="ebitdaMargins",
             revg="revenueGrowth", epsg="earningsGrowth", dy="trailingAnnualDividendYield", payout="payoutRatio", beta="beta", ins="heldPercentInsiders",
             inst="heldPercentInstitutions", fcf="freeCashflow", ocf="operatingCashflow", cash="totalCash", debt="totalDebt", rev="totalRevenue", ni="netIncomeToCommon")


def one_fund(sym):
    import yfinance as yf
    for attempt in range(3):
        try:
            t = yf.Ticker(sym + ".NS"); info = t.get_info() or {}
            o = {k: info.get(v) for k, v in FKEYS.items()}
            o = {k: (round(float(v), 4) if isinstance(v, (int, float)) and np.isfinite(v) else None) for k, v in o.items()}
            if o.get("de") is not None: o["de"] = round(o["de"] / 100, 3)       # Yahoo gives debt/equity in percent
            if not o.get("dy"):   # Yahoo's trailing yield is often 0 for Indian stocks: fall back to the annual dividend rate / price
                dr, px_ = info.get("dividendRate"), info.get("currentPrice") or info.get("regularMarketPrice")
                o["dy"] = round(dr / px_, 4) if isinstance(dr, (int, float)) and isinstance(px_, (int, float)) and dr > 0 and px_ > 0 else None
            try:
                b = t.balance_sheet
                if b is not None and not b.empty:
                    col = sorted(b.columns)[-1]; g = lambda nm: float(b.loc[nm, col]) if nm in b.index and np.isfinite(b.loc[nm, col]) else None
                    eq, ca, cl = g("Stockholders Equity") or g("Common Stock Equity"), g("Current Assets"), g("Current Liabilities")
                    if o.get("roe") is None and eq and eq > 0 and o.get("ni") is not None: o["roe"], o["roe_src"] = round(o["ni"] / eq, 4), "profit / latest equity"
                    if o.get("cr") is None and ca and cl and cl > 0: o["cr"] = round(ca / cl, 2)
            except Exception: pass
            if o.get("roe") is None and o.get("pe") and o.get("pb") and o["pe"] > 0 and o["pb"] > 0: o["roe"], o["roe_src"] = round(o["pb"] / o["pe"], 4), "P/B divided by P/E"
            o["sec"], o["ind"], o["name"] = info.get("sector"), info.get("industry"), info.get("longName") or info.get("shortName")
            try:
                q = t.quarterly_income_stmt
                if q is not None and not q.empty:
                    q = q.loc[:, sorted(q.columns)]
                    def row(*names):
                        for nm in names:
                            if nm in q.index: return q.loc[nm]
                        return None
                    rv, pr = row("Total Revenue", "Operating Revenue"), row("Net Income", "Net Income Common Stockholders")
                    o["q"] = [dict(d=str(c.date()), rev=None if rv is None or not np.isfinite(rv[c]) else float(rv[c]), ni=None if pr is None or not np.isfinite(pr[c]) else float(pr[c])) for c in q.columns[-6:]]
            except Exception: pass
            try:
                a = t.income_stmt
                if a is not None and not a.empty:
                    col = sorted(a.columns)[-1]
                    ebit = a.loc["EBIT", col] if "EBIT" in a.index else a.loc["Operating Income", col] if "Operating Income" in a.index else None
                    it = a.loc["Interest Expense", col] if "Interest Expense" in a.index else None
                    if ebit is not None and it is not None and np.isfinite(ebit) and np.isfinite(it) and abs(it) > 0: o["icr"] = round(float(ebit / abs(it)), 2)
                    o["fy"] = str(col.date())
            except Exception: pass
            return sym, o
        except Exception as e:
            if "Too Many" in str(e) or "429" in str(e): time.sleep(20 * (attempt + 1))
            else: time.sleep(2)
    return sym, None


def fund_all(syms, budget=3000):
    out, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = []
        for s in syms: futs.append(ex.submit(one_fund, s))
        for k, fu in enumerate(futs):
            remaining = budget - (time.time() - t0)
            if remaining <= 0: log.warning("fundamentals time budget reached at %d", k); break
            try:
                s, o = fu.result(timeout=max(1, remaining))
                if o: out[s] = o
            except Exception: pass
            if k % 100 == 0: log.info("fundamentals %d/%d", k, len(syms))
        for fu in futs: fu.cancel()
    return out


def med(vals):
    v = [x for x in vals if x is not None and np.isfinite(x)]; return round(float(np.median(v)), 4) if len(v) >= 3 else None


def sector_medians(F):
    by = {}
    for s, o in F.items():
        if o.get("sec"): by.setdefault(o["sec"], []).append(o)
    out = {}
    for sec, L in by.items():
        out[sec] = dict(n=len(L), pe=med([o["pe"] for o in L if o.get("pe") and o["pe"] > 0]), pb=med([o.get("pb") for o in L]), evebitda=med([o["evebitda"] for o in L if o.get("evebitda") and o["evebitda"] > 0]),
                        roe=med([o.get("roe") for o in L]), de=med([o.get("de") for o in L]), opm=med([o.get("opm") for o in L]), npm=med([o.get("npm") for o in L]),
                        revg=med([o.get("revg") for o in L]), dy=med([o.get("dy") for o in L]))
    return out


# ---------------- market readings ----------------
def ob(area, text, tone, ref=None, data=None):
    return dict(area=area, text=text, tone=tone, ref=ref, data=data)


def market_readings(M, sect, breadth, news):
    R = []; g = lambda k: M.get(k) or {}
    n, sx = g("^NSEI"), g("^BSESN")
    if n.get("vs200") is not None:
        up = n["vs200"] > 0; rising = (n.get("s200") or 0) > 0
        state = "uptrend (bull)" if up and rising else "downtrend (bear)" if not up and not rising else "mixed / sideways"
        R.append(ob("Trend", f"Nifty 50 is {abs(n['vs200']):.1f}% {'above' if up else 'below'} its 200-day average, and that average is {'rising' if rising else 'falling'} ({(n.get('s200') or 0):+.1f}% over 20 days). By the moving-average test the primary trend reads as {state}.", "pos" if up and rising else "neg" if not up and not rising else "neu", "trend"))
    if n.get("m1") is not None and sx.get("m1") is not None:
        same = (n["m1"] >= 0) == (sx["m1"] >= 0)
        R.append(ob("Trend", f"Over one month the Nifty 50 moved {n['m1']:+.1f}% and the Sensex {sx['m1']:+.1f}%: {'the two indices confirm each other' if same else 'the two indices disagree, so the move is not confirmed'}.", "neu", "dow"))
    ni = M.get("_nifty_tech") or {}
    if ni.get("rsi") is not None:
        r = ni["rsi"]; txt = f"Nifty 50 RSI (14) is {r:.0f}. "
        txt += "That is above 70, the usual overbought line." if r > 70 else "That is below 30, the usual oversold line." if r < 30 else "That is below the 44-45 zone that a bull market rarely falls under." if r < 44 else "That is above the 50-55 zone that a bear market rarely rises over." if r > 55 else "That is in the middle band (44-55), which by itself does not separate a bull from a bear phase."
        R.append(ob("Momentum", txt, "neg" if r < 44 else "pos" if r > 55 else "neu", "rsi"))
    if ni.get("macd") is not None:
        a, s_ = ni["macd"], ni["msig"]
        R.append(ob("Momentum", f"Nifty 50 MACD is {'above' if a > s_ else 'below'} its signal line and {'above' if a > 0 else 'below'} zero.", "pos" if a > s_ and a > 0 else "neg" if a < s_ and a < 0 else "neu", "macd"))
    if breadth:
        R.append(ob("Breadth", f"{breadth['above200']:.0f}% of the {breadth['n']} covered stocks are above their 200-day average and {breadth['above50']:.0f}% above their 50-day average.", "pos" if breadth["above200"] > 60 else "neg" if breadth["above200"] < 40 else "neu", None))
    if sect:
        rk = sorted([x for x in sect if x.get("rel3") is not None], key=lambda x: -x["rel3"])
        if len(rk) >= 4:
            lead = ", ".join(f"{x['name']} ({x['rel3']:+.1f}%)" for x in rk[:3]); lag = ", ".join(f"{x['name']} ({x['rel3']:+.1f}%)" for x in rk[-3:])
            R.append(ob("Sectors", f"Against the Nifty 50 over 3 months, the strongest sectors were {lead}; the weakest were {lag}.", "neu", "rsc"))
    b = g("BZ=F")
    if b.get("m1") is not None:
        x = b["m1"]
        if x >= 5: R.append(ob("Commodities", f"Brent crude is up {x:.1f}% in a month (${b['last']:.1f}). Rising crude raises input costs for users such as airlines, paints and logistics and helps oil producers; as an importer, India feels it in fuel prices and inflation.", "neg", "commod_eq"))
        elif x <= -5: R.append(ob("Commodities", f"Brent crude is down {abs(x):.1f}% in a month (${b['last']:.1f}). Falling crude lowers input costs for users such as airlines, paints and logistics and squeezes oil producers; for an importer like India it eases fuel prices and inflation.", "pos", "commod_eq"))
        else: R.append(ob("Commodities", f"Brent crude moved {x:+.1f}% in a month (${b['last']:.1f}), a modest change.", "neu", "intl"))
    u = g("INR=X")
    if u.get("m1") is not None:
        x = u["m1"]
        if x >= 1: R.append(ob("Currency", f"The rupee weakened {x:.1f}% against the dollar in a month (₹{u['last']:.2f}). A weaker rupee makes imports (crude, capital goods) dearer and helps exporters' rupee earnings.", "neg", "cad"))
        elif x <= -1: R.append(ob("Currency", f"The rupee strengthened {abs(x):.1f}% against the dollar in a month (₹{u['last']:.2f}). Imports get cheaper; exporters earn fewer rupees per dollar.", "pos", "cad"))
        else: R.append(ob("Currency", f"The rupee was steady against the dollar ({x:+.1f}% in a month, ₹{u['last']:.2f}).", "neu", "cad"))
    d = g("DX-Y.NYB")
    if d.get("m1") is not None and abs(d["m1"]) >= 1.5:
        R.append(ob("Currency", f"The US dollar index {'rose' if d['m1'] > 0 else 'fell'} {abs(d['m1']):.1f}% in a month. A {'stronger dollar usually weighs on' if d['m1'] > 0 else 'weaker dollar usually supports'} dollar-priced commodities.", "neu", "dollar"))
    au = g("GC=F")
    if au.get("m1") is not None and abs(au["m1"]) >= 4:
        R.append(ob("Commodities", f"Gold {'rose' if au['m1'] > 0 else 'fell'} {abs(au['m1']):.1f}% in a month (${au['last']:.0f}). Gold is the usual hedge investors turn to when inflation worries rise.", "neu", "macro_ind"))
    cu = g("HG=F")
    if cu.get("m1") is not None and abs(cu["m1"]) >= 5:
        R.append(ob("Commodities", f"Copper {'rose' if cu['m1'] > 0 else 'fell'} {abs(cu['m1']):.1f}% in a month. NISM reads a fall in copper as a possible sign of slowing industrial demand, weighing on metal and infrastructure stocks{'; a rise is the opposite reading' if cu['m1'] > 0 else ''}.", "pos" if cu["m1"] > 0 else "neg", "commod_eq"))
    t = g("^TNX")
    if t.get("last") is not None and t.get("m1") is not None:
        bp = t["last"] * t["m1"] / (100 + t["m1"]) * 100
        R.append(ob("Global rates", f"The US 10-year yield is {t['last']:.2f}% ({bp:+.0f} basis points in a month). Foreign portfolio money, which NISM calls 'hot money' that can leave at any time, watches global rates.", "neu", "fpi"))
    gl = [g(k) for k, _ in GLOBAL]; dn = sum(1 for x in gl if (x.get("m1") or 0) <= -5); upn = sum(1 for x in gl if (x.get("m1") or 0) >= 5)
    if dn >= 3: R.append(ob("Global", f"{dn} of {len(GLOBAL)} major world indices fell 5% or more in a month. Integrated economies mean trouble in one region spreads to others.", "neg", "global"))
    elif upn >= 3: R.append(ob("Global", f"{upn} of {len(GLOBAL)} major world indices rose 5% or more in a month.", "pos", "global"))
    vx = g("^INDIAVIX")
    if vx.get("last") is not None: R.append(ob("Volatility", f"India VIX (expected 30-day volatility of the Nifty) is {vx['last']:.1f}, {(vx.get('m1') or 0):+.0f}% in a month.", "neg" if (vx.get("m1") or 0) > 20 else "neu", None))
    th = {t["id"]: t for t in (news or {}).get("themes", [])}
    cov = sorted([(t["name"], sum(x["n"] for x in t["stories"])) for k, t in th.items() if k in ("geo", "trade", "energy", "politics", "people")], key=lambda x: -x[1])
    cov = [f"{nm.lower()} ({c} reports)" for nm, c in cov if c][:3]
    if cov: R.append(ob("Geopolitics", f"The most heavily reported world themes of the last {(news or {}).get('days', 3)} days: {', '.join(cov)}. Conflicts in oil regions, sanctions and trade wars mainly reach Indian stocks through crude prices, the rupee and supply chains.", "neu", "geo"))
    return R


def clean(o):
    """JSON cannot carry NaN or infinity: turn them into null"""
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)): return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.bool_): return bool(o)
    return o


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--fund", action="store_true"); ap.add_argument("--top", type=int, default=800); a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    # 1. market series
    tick = sorted({k for k, _ in INDIA + GLOBAL + MACRO + SECTORS})
    raw = yfdl(tick, "2y"); M = {}
    for k in tick:
        if k in raw:
            try: M[k] = series_stats(raw[k])
            except Exception as e: log.warning("%s: %s", k, e)
    nifty = raw["^NSEI"]["Close"] if "^NSEI" in raw else None
    if "^NSEI" in raw: M["_nifty_tech"] = tech(raw["^NSEI"])
    sect = []
    for k, nm in SECTORS:
        x = M.get(k)
        if x and M.get("^NSEI"): sect.append(dict(k=k, name=nm, m1=x.get("m1"), m3=x.get("m3"), rel1=None if x.get("m1") is None else round(x["m1"] - M["^NSEI"]["m1"], 2), rel3=None if x.get("m3") is None else round(x["m3"] - M["^NSEI"]["m3"], 2), vs200=x.get("vs200")))
    # 2. covered stocks: technicals daily
    from screen import load_bhav, BHAV
    load_bhav(); b = BHAV.get("NSE"); syms = []
    if b: syms = [k for k, v in sorted(((k, v) for k, v in b[1].items() if (v[3] or 0) >= 20 and (v[6] or 0) > 0), key=lambda kv: -kv[1][6])][:a.top]
    old = {}
    try: old = json.loads((ROOT / "fund.json").read_text())
    except Exception: pass
    px = yfdl([s + ".NS" for s in syms], "2y") if syms else {}
    stocks = {}
    for s in syms:
        d = px.get(s + ".NS")
        if d is None or len(d) < 60: continue
        try: stocks[s] = dict(t=tech(d, nifty))
        except Exception as e: log.warning("tech %s: %s", s, e)
    breadth = None
    if stocks:
        v2 = [x["t"]["vs200"] for x in stocks.values() if x["t"].get("vs200") is not None]; v5 = [x["t"]["vs50"] for x in stocks.values() if x["t"].get("vs50") is not None]
        breadth = dict(n=len(stocks), above200=round(100 * np.mean([x > 0 for x in v2]), 1) if v2 else None, above50=round(100 * np.mean([x > 0 for x in v5]), 1) if v5 else None)
    # 3. fundamentals: weekly
    F = old.get("fund", {}); fdate = old.get("fund_updated")
    stale = not fdate or (now - dt.datetime.fromisoformat(fdate)).days >= 6
    if a.fund or stale:
        log.info("refreshing fundamentals for %d stocks", len(stocks))
        newF = fund_all(list(stocks))
        if len(newF) > 0.3 * len(stocks): F, fdate = newF, now.isoformat()
        else: log.warning("fundamentals: only %d fetched, keeping the old set", len(newF))
    secmed = sector_medians(F) if F else {}
    big = sorted([(s, o) for s, o in F.items() if o.get("mcap") and o.get("ni")], key=lambda x: -x[1]["mcap"])[:50]
    mpe = round(sum(o["mcap"] for _, o in big) / sum(o["ni"] for _, o in big), 1) if big and sum(o["ni"] for _, o in big) > 0 else None
    # 4. news (organised by how it reaches share prices; company names matched against the covered list)
    import news as NW
    names = {k: (F.get(k) or {}).get("name") for k in stocks}
    news = NW.collect(names, 3, log)
    if F and stocks and M.get("^NSEI"):
        by = {}
        for s_, o in stocks.items():
            sec_ = (F.get(s_) or {}).get("sec")
            if sec_: by.setdefault(sec_, []).append(o["t"])
        nm1, nm3 = M["^NSEI"].get("m1"), M["^NSEI"].get("m3")
        cov = []
        for sec_, L in by.items():
            if len(L) < 5: continue
            m1_, m3_ = med([x.get("m1") for x in L]), med([x.get("m3") for x in L])
            cov.append(dict(name=sec_, n=len(L), kind="stocks", m1=m1_, m3=m3_, rel1=None if m1_ is None or nm1 is None else round(m1_ - nm1, 2), rel3=None if m3_ is None or nm3 is None else round(m3_ - nm3, 2),
                            above200=round(100 * np.mean([(x.get("vs200") or 0) > 0 for x in L]), 0)))
        sect = cov + [dict(x, kind="index") for x in sect]
    readings = market_readings(M, [x for x in sect if x.get("kind") != "index"] or sect, breadth, news)
    names = {s: (F.get(s) or {}).get("name") for s in stocks}
    out = dict(updated=now.isoformat(), price_date=(M.get("^NSEI") or {}).get("date"),
               groups=[dict(name="India", items=[dict(k=k, name=nm, **M[k]) for k, nm in INDIA if k in M]),
                       dict(name="World markets", items=[dict(k=k, name=nm, **M[k]) for k, nm in GLOBAL if k in M]),
                       dict(name="Currency, commodities and rates", items=[dict(k=k, name=nm, **M[k]) for k, nm in MACRO if k in M])],
               sectors=sect, breadth=breadth, market_pe=dict(pe=mpe, n=len(big)) if mpe else None, readings=readings, news=news, refs={k: dict(src=v[0], says=v[1]) for k, v in REFS.items()},
               nifty=dict(dates=[str(x.date()) for x in nifty.index[-300:]], close=[round(float(x), 2) for x in nifty.tail(300)]) if nifty is not None else None)
    (ROOT / "insights.json").write_text(json.dumps(clean(out), separators=(",", ":"), default=str, allow_nan=False))
    fund_out = dict(updated=now.isoformat(), fund_updated=fdate, universe=f"The {len(stocks)} most traded NSE stocks", sector_med=secmed,
                    stocks={s: dict(o, n=names.get(s)) for s, o in stocks.items()}, fund=F)
    (ROOT / "names.json").write_text(json.dumps({k: v for k, v in names.items() if v}, separators=(",", ":")))
    (ROOT / "fund.json").write_text(json.dumps(clean(fund_out), separators=(",", ":"), default=str, allow_nan=False))
    log.info("written insights.json (%d readings, %d stories in themes, %d top stories) and fund.json (%d stocks, %d with financials)", len(readings), sum(len(t["stories"]) for t in news["themes"]), len(news["top"]), len(stocks), len(F))


if __name__ == "__main__":
    main()
