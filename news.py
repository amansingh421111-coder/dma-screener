"""Market-moving news, collected from Google News searches and organised by how it can reach share prices.

Honest limits, shown on the page:
  * posts on X / Truth Social are not read directly (X's API is paid and scraping is not allowed); they appear when
    reputable outlets report them, which is also when they tend to move markets
  * headlines are grouped and ranked by fixed rules (how many outlets carry the same story, how recent, source list);
    nothing is summarised or judged by a person or a model
"""
import datetime as dt, email.utils, html, re, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

# Outlets whose stories are kept. Matched against the domain Google News gives for each item.
SOURCES = {
    "reuters.com": "Reuters", "bloomberg.com": "Bloomberg", "ft.com": "Financial Times", "wsj.com": "Wall Street Journal", "cnbc.com": "CNBC", "apnews.com": "AP",
    "bbc.com": "BBC", "bbc.co.uk": "BBC", "nytimes.com": "New York Times", "washingtonpost.com": "Washington Post", "theguardian.com": "The Guardian", "economist.com": "The Economist",
    "aljazeera.com": "Al Jazeera", "cnn.com": "CNN", "politico.com": "Politico", "politico.eu": "Politico Europe", "axios.com": "Axios", "barrons.com": "Barron's",
    "marketwatch.com": "MarketWatch", "finance.yahoo.com": "Yahoo Finance", "fortune.com": "Fortune", "forbes.com": "Forbes", "businessinsider.com": "Business Insider",
    "asia.nikkei.com": "Nikkei Asia", "scmp.com": "South China Morning Post", "investing.com": "Investing.com", "in.investing.com": "Investing.com", "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge", "npr.org": "NPR", "foxbusiness.com": "Fox Business", "abcnews.go.com": "ABC News", "cbsnews.com": "CBS News", "nbcnews.com": "NBC News",
    "economictimes.indiatimes.com": "Economic Times", "livemint.com": "Mint", "business-standard.com": "Business Standard", "moneycontrol.com": "Moneycontrol",
    "thehindubusinessline.com": "BusinessLine", "financialexpress.com": "Financial Express", "ndtvprofit.com": "NDTV Profit", "businesstoday.in": "Business Today",
    "thehindu.com": "The Hindu", "indianexpress.com": "Indian Express", "hindustantimes.com": "Hindustan Times", "timesofindia.indiatimes.com": "Times of India",
    "ndtv.com": "NDTV", "zeebiz.com": "Zee Business", "cnbctv18.com": "CNBC-TV18", "outlookbusiness.com": "Outlook Business", "fortuneindia.com": "Fortune India",
    "thewire.in": "The Wire", "theprint.in": "ThePrint", "scroll.in": "Scroll", "rbi.org.in": "RBI", "pib.gov.in": "PIB (Government of India)", "sebi.gov.in": "SEBI",
}
JUNK = re.compile(r"(stocks? to (buy|watch)|top \d+ (stocks|picks)|stock picks|buy or sell|target price|multibagger|current affairs|quiz|horoscope|"
                  r"price today|rate today|check latest (rates|prices)|city-wise|current price of|prices on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|better .* stock:|stock (is|was) (rallying|falling) today|why is .* stock|live updates?:? .*gold|lottery|recipe|cricket|bollywood|box office|weather today|\bodds\b|prediction:)", re.I)

MARKET = r'\b(tariffs?|trade|market|stocks?|shares|economy|economic|rates?|inflation|oil|crude|diesel|gas|sanctions?|tax|budget|gst|deficit|spending|subsidy|visa|h-1b|investment|invest|deal|war|iran|china|india|fed\b|tesla|spacex|starlink|x\.?ai|crypto|bitcoin|dollar|rupee|ban|regulat|industry|companies|company|business|jobs|chips?|ai\b|semiconductor|bank|price|growth|recession|imports?|exports?)'

# Themes: how a kind of news reaches Indian share prices, with the NISM section the channel comes from.
THEMES = [
    dict(id="rates", name="Central banks and interest rates", ref="rates", sectors="Banks, NBFCs, real estate, autos (loan-funded demand); foreign flows",
         why="Rate decisions change borrowing costs and the return on bonds versus shares; foreign portfolio money reacts quickly.",
         q=["RBI monetary policy repo rate", "Federal Reserve interest rate decision", "ECB OR \"Bank of Japan\" interest rates"], kw=r"\b(rbi|repo|mpc|fed\b|federal reserve|powell|ecb|bank of japan|boj|rate (cut|hike)|interest rates?)\b"),
    dict(id="macro", name="Inflation, growth and jobs data", ref="eic", sectors="The whole market; consumer and capital-goods companies most",
         why="Economy-level numbers come first in the top-down (economy, industry, company) approach.",
         q=["India inflation CPI GDP data", "US inflation jobs report economy", "India IIP PMI economy"], kw=r"\b(inflation|cpi|wpi|gdp|jobs report|payrolls|unemployment|pmi|iip|recession|economic growth)\b"),
    dict(id="geo", name="Wars, conflicts and security", ref="geo", sectors="Oil marketing and aviation (crude), defence, shipping and logistics, exporters",
         why="Conflicts in oil regions lift crude and the risk premium; disruption of shipping routes hits supply chains.",
         q=["war conflict oil markets", "Middle East Iran Israel tensions markets", "Russia Ukraine war economy", "India China Pakistan border tensions"], kw=r"\b(war|conflict|missile|strikes?|attack|military|ceasefire|troops|tensions|invasion|drone)\b"),
    dict(id="trade", name="Trade, tariffs and sanctions", ref="geo", sectors="Exporters (IT services, pharma, textiles, auto parts, metals), importers",
         why="Tariffs, quotas and sanctions change what can be sold where and at what price.",
         q=["tariffs trade war", "sanctions oil exports", "India US trade deal tariffs", "export ban import duty"], kw=r"\b(tariffs?|trade (war|deal|talks|pact)|sanctions?|export ban|import duty|duties|wto|embargo)\b"),
    dict(id="politics", name="Government, elections and policy", ref="cad", sectors="Depends on the policy: PSU stocks, infrastructure, consumer, sectors named in the decision",
         why="Taxes, spending and regulation change company earnings; fiscal deficits push up interest rates.",
         q=["India government policy budget GST", "US White House policy economy", "election results markets", "H-1B visa policy"], kw=r"\b(government|election|budget|gst|policy|parliament|white house|congress|minister|cabinet|visa|pli|subsidy|tax)\b", need=MARKET),
    dict(id="people", name="Posts and remarks by market-moving people", ref="emh", sectors="Companies and sectors they talk about; overall sentiment",
         why="Remarks by heads of government, central bankers and big-company leaders spread in minutes; public information is reflected in prices quickly.",
         q=["\"Elon Musk\" post OR tweet OR \"on X\"", "Trump \"Truth Social\" post", "Trump says tariffs OR markets OR India", "\"Jerome Powell\" says", "\"Nirmala Sitharaman\" says", "\"RBI Governor\" says", "\"Warren Buffett\" OR \"Jensen Huang\" OR \"Sam Altman\" says"],
         kw=r"(musk|trump|powell|sitharaman|rbi governor|buffett|jensen huang|altman|xi jinping|modi|putin|lagarde|zuckerberg|bezos|ambani|adani|tata)", people=True, need=MARKET),
    dict(id="energy", name="Crude oil, gas and commodities", ref="commod_eq", sectors="Oil producers and refiners, OMCs, airlines, paints, tyres, chemicals, metals",
         why="Commodity prices change input costs and margins; India imports most of its crude.",
         q=["crude oil prices OPEC", "gold silver prices", "copper aluminium steel prices"], kw=r"\b(crude|oil|opec|brent|gas|lng|gold|silver|copper|aluminium|steel|coal|commodit)"),
    dict(id="fx", name="Rupee, dollar and foreign money flows", ref="fpi", sectors="IT services and pharma (exporters), importers, the whole market via FPI flows",
         why="Foreign portfolio money is 'hot money' that can leave at any time; a weaker rupee raises import costs and helps exporters.",
         q=["rupee dollar forex", "FPI FII outflows inflows India equities"], kw=r"\b(rupee|dollar|forex|currency|fpi|fii|foreign investors?|outflows?|inflows?)\b"),
    dict(id="regulator", name="Regulators, courts and investigations", ref="corp", sectors="The companies named; sometimes a whole segment (derivatives, brokers, platforms)",
         why="Orders, penalties and rule changes alter what companies may do and can trigger exchange surveillance.",
         q=["SEBI order rules", "SEC investigation company", "antitrust probe fine company", "court ruling company shares"], kw=r"\b(sebi|sec\b|regulator|probe|investigation|penalty|fine[sd]?|ban|court|ruling|antitrust|nclt|ed\b|cbi|raid)\b"),
    dict(id="corporate", name="Company results, deals and boardrooms", ref="corp", sectors="The companies named and their peers",
         why="Results, mergers, buybacks, management changes and governance issues change a company's value directly.",
         q=["quarterly results India company profit", "merger acquisition deal billion", "CEO resigns OR appointed company", "boardroom battle shareholders activist", "IPO listing India"],
         kw=r"\b(results?|profit|revenue|earnings|merger|acqui|buyback|stake|ceo|chairman|board|resign|ipo|listing|dividend|bonus|demerger)"),
    dict(id="tech", name="Big tech, AI and chips", ref="global", sectors="IT services, semiconductors and electronics makers, data centres, telecom",
         why="Spending plans of the world's largest tech companies drive demand for Indian IT services and global sentiment.",
         q=["Nvidia Apple Microsoft AI spending", "artificial intelligence chips semiconductor", "Tesla SpaceX xAI Musk business"], kw=r"\b(ai|artificial intelligence|nvidia|apple|microsoft|google|alphabet|amazon|meta|openai|tesla|chip|semiconductor|xai|spacex)\b"),
    dict(id="world", name="China and world markets", ref="global", sectors="Metals, chemicals, exporters; overall risk appetite",
         why="Integrated economies mean a problem in one region spreads; China drives global metal and commodity demand.",
         q=["China economy stimulus stocks", "global stock markets selloff OR rally", "Wall Street stocks close"], kw=r"\b(china|chinese|beijing|wall street|s&p|nasdaq|dow|nikkei|hang seng|global markets|stocks)\b"),
    dict(id="ratings", name="Credit ratings and sovereign outlook", ref="corp", sectors="Banks and the whole market (foreign funding costs)",
         why="Rating changes for India or large companies change borrowing costs and foreign investors' appetite.",
         q=["Moody's OR Fitch OR S&P rating India", "credit rating downgrade upgrade company"], kw=r"\b(moody|fitch|s&p global ratings|rating|downgrade|upgrade|outlook)\b"),
]
PEOPLE = [("Elon Musk", r"\bmusk\b"), ("Donald Trump", r"\btrump\b"), ("Jerome Powell", r"\bpowell\b"), ("Nirmala Sitharaman", r"sitharaman"), ("RBI Governor", r"rbi governor|sanjay malhotra"),
          ("Narendra Modi", r"\bmodi\b"), ("Xi Jinping", r"\bxi\b|xi jinping"), ("Vladimir Putin", r"\bputin\b"), ("Warren Buffett", r"buffett"), ("Jensen Huang", r"jensen huang"),
          ("Sam Altman", r"\baltman\b"), ("Mukesh Ambani", r"\bambani\b"), ("Gautam Adani", r"\badani\b")]


SHORT = {'rates': 'Rates', 'macro': 'Economy data', 'geo': 'Conflicts', 'trade': 'Trade & sanctions', 'politics': 'Policy & elections', 'people': 'People & posts', 'energy': 'Oil & commodities', 'fx': 'Rupee & flows', 'regulator': 'Regulators', 'corporate': 'Companies', 'tech': 'Tech & AI', 'world': 'China & world', 'ratings': 'Ratings'}


def _dom(u):
    m = re.match(r"https?://([^/]+)", u or ""); d = (m.group(1) if m else "").lower()
    return d[4:] if d.startswith("www.") else d


def parse(xml):
    out = []
    for it in re.findall(r"<item\b.*?</item>", xml, re.S | re.I):
        g = lambda k: (re.search(rf"<{k}\b[^>]*>(.*?)</{k}>", it, re.S | re.I) or [None, ""])[1]
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", g("title"))).strip()
        link = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", g("link"))).strip()
        sm = re.search(r'<source\b[^>]*url="([^"]+)"[^>]*>(.*?)</source>', it, re.S | re.I)
        dom, src = (_dom(sm.group(1)), html.unescape(sm.group(2)).strip()) if sm else ("", "")
        ts = None
        try: ts = email.utils.parsedate_to_datetime(g("pubDate").strip()).astimezone(dt.timezone.utc)
        except Exception: pass
        if src and title.endswith(" - " + src): title = title[: -len(src) - 3]
        if title and link.startswith("http"): out.append(dict(t=title[:220], u=link[:600], dom=dom, src=src, d=ts))
    return out


def gnews(q, days):
    r = requests.get("https://news.google.com/rss/search", params=dict(q=f"{q} when:{days}d", hl="en-IN", gl="IN", ceid="IN:en"), headers=UA, timeout=25)
    r.raise_for_status(); return parse(r.text)


def _toks(t):
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 2 and w not in {"the", "and", "for", "with", "from", "after", "over", "amid", "says", "said", "will", "its", "this", "that", "into", "than", "what", "how", "why"}}


def cluster(items):
    """same story from several outlets -> one story with the outlets listed (word overlap >= 50%)"""
    stories = []
    for x in sorted(items, key=lambda x: x["d"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True):
        tk = _toks(x["t"])
        if not tk: continue
        for s in stories:
            inter = len(tk & s["tk"]); union = len(tk | s["tk"])
            if union and inter / union >= 0.5 or (inter >= 5 and inter / min(len(tk), len(s["tk"])) >= 0.7):
                if x["src"] not in {o["s"] for o in s["out"]}: s["out"].append(dict(s=x["src"], u=x["u"]))
                break
        else:
            stories.append(dict(t=x["t"], u=x["u"], s=x["src"], d=x["d"], tk=tk, out=[dict(s=x["src"], u=x["u"])]))
    return stories


def company_matcher(names):
    """names: {SYMBOL: 'Company Name Limited'} -> function(title) -> [symbols]"""
    stop = {"india", "indian", "bank", "power", "energy", "capital", "finance", "industries", "global", "international", "national", "general", "united", "steel", "motors", "life", "money", "gold", "silver", "oil", "gas", "trade", "home", "first", "star", "sun"}
    pats, firsts = [], set()
    for sym, nm in names.items():
        if not nm: continue
        base = re.sub(r"\b(limited|ltd\.?|company|corporation|corp\.?|co\.|inc\.?|\(india\)|india)\b", "", nm, flags=re.I).strip(" .,&-")
        words = base.split()
        cand = " ".join(words[:3]) if len(words) >= 3 and len(" ".join(words[:2])) < 9 else " ".join(words[:2]) if len(words) >= 2 else base
        if cand.endswith((" of", " &", " and")): cand = " ".join(words[:3])
        if len(cand) >= 5 and cand.lower() not in stop and not cand.endswith((" of", " &", " and")): pats.append((sym, re.compile(r"\b" + re.escape(cand) + r"\b")))
        if len(sym) >= 3 and sym.isalpha() and sym.lower() not in stop: pats.append((sym, re.compile(r"\b" + re.escape(sym) + r"\b")))
        w0 = words[0] if words else ""          # first word alone ("Reliance") goes to the most traded company that starts with it
        generic = len(words) >= 2 and words[1].lower() in {"industries", "enterprises", "group", "holdings", "ltd", "limited", "corporation", "ventures"}
        if generic and len(w0) >= 5 and w0.lower() not in stop and w0[0].isupper() and w0 not in firsts:
            firsts.add(w0); pats.append((sym, re.compile(r"\b" + re.escape(w0) + r"\b(?! (Power|Capital|Infra|Home|Retail|Securities|Finance))")))
    def f(title):
        hit = []
        for sym, rx in pats:
            if sym not in hit and rx.search(title): hit.append(sym)
        return hit[:4]
    return f


def collect(names=None, days=3, log=None):
    now = dt.datetime.now(dt.timezone.utc); cutoff = now - dt.timedelta(days=days)
    match = company_matcher(names or {})
    themes_out, allst = [], []
    for th in THEMES:
        items = []
        for q in th["q"]:
            try: items += gnews(q, days)
            except Exception as e:
                if log: log.warning("news %s: %s", q, str(e)[:80])
            time.sleep(0.8)
        keep = []
        for x in items:
            if x["d"] and x["d"] > now + dt.timedelta(minutes=10): x["d"] -= dt.timedelta(minutes=330)   # IST labelled as UTC
            if x["d"] and x["d"] < cutoff: continue
            name = SOURCES.get(x["dom"]) or next((v for k, v in SOURCES.items() if x["dom"].endswith("." + k)), None)
            if not name or JUNK.search(x["t"]): continue
            if not re.search(th["kw"], x["t"], re.I): continue        # the headline itself must be about the theme
            if th.get("need") and not re.search(th["need"], x["t"], re.I): continue   # and, for people and politics, about money or markets
            x["src"] = name; keep.append(x)
        st = cluster(keep)
        for s in st:
            s["n"] = len(s["out"]); s["co"] = match(s["t"])
            if th.get("people"): s["who"] = [nm for nm, rx in PEOPLE if re.search(rx, s["t"], re.I)][:2]
            for nm, sym in (("Mukesh Ambani", "RELIANCE"), ("Gautam Adani", "ADANIENT")):     # people whose name stands for a listed group
                if re.search(dict(PEOPLE)[nm], s["t"], re.I) and sym in (names or {}) and sym not in s["co"]: s["co"].append(sym)
        st.sort(key=lambda s: (-min(s["n"], 6), -(s["d"].timestamp() if s["d"] else 0)))
        if th.get("people"): st = [s for s in st if s.get("who")]
        out = []
        for s in st[:12]:
            o = dict(t=s["t"], u=s["u"], s=s["s"], d=s["d"].isoformat() if s["d"] else None, n=s["n"], also=[a for a in s["out"] if a["s"] != s["s"]][:4], co=s["co"])
            if s.get("who"): o["who"] = s["who"]
            out.append(o); allst.append(dict(o, th=th["id"], tk=s["tk"]))
        themes_out.append(dict(id=th["id"], name=th["name"], short=SHORT.get(th["id"], th["name"]), why=th["why"], ref=th["ref"], sectors=th["sectors"], stories=out))
    # top stories: the most widely covered across all themes (a story found under two themes counts once)
    top, seen = [], []
    for s in sorted(allst, key=lambda s: (-min(s["n"], 8), -(dt.datetime.fromisoformat(s["d"]).timestamp() if s["d"] else 0))):
        if any(len(s["tk"] & t2) / max(1, len(s["tk"] | t2)) >= 0.5 for t2 in seen): continue
        seen.append(s["tk"]); top.append({k: v for k, v in s.items() if k != "tk"})
        if len(top) >= 10: break
    people = {}
    for th in themes_out:
        if th["id"] != "people": continue
        for s in th["stories"]:
            for w in s.get("who", []): people.setdefault(w, []).append(s)
    return dict(updated=now.isoformat(), days=days, top=top, themes=themes_out, people=[dict(name=k, stories=v[:5]) for k, v in people.items()],
                note="Collected from Google News searches, limited to a fixed list of established outlets, grouped when several outlets carry the same story, and ranked by how many outlets carry it and how recent it is. Posts on X or Truth Social appear when these outlets report them. Headlines are not summarised or checked.")
