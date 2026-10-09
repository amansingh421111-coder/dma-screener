"""Morning and evening briefs on Telegram, built from the last screener run and each user's holdings.
Usage: python brief.py morning|evening"""
import datetime as dt, json, sys
from screen import IST, ROOT, cloud_users, send_telegram, notify, read_json, pos_key

def inr(v): return f"₹{v:,.0f}"
def sg(v): return f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"

def quote_for(p, sj):
    k = pos_key(p); q = (sj.get("quotes") or {}).get(k)
    if q: return q
    for s in sj.get("signals", []):
        if f"{s.get('exchange', 'NSE')}:{s['symbol']}" == k: return dict(price=s["price"], pct=s["pct"], chg=s.get("chg"), ma=s["ma"])
    return None

def holdings_lines(pos, sj, c_ma):
    """Returns (lines, totals) for the open holdings."""
    lines, val, inv, day, risk, flagged = [], 0.0, 0.0, 0.0, 0.0, 0
    for p in pos:
        qty, avg, q = p.get("qty") or 0, p.get("avg") or p.get("buy") or 0, quote_for(p, sj)
        if qty <= 0 or not avg: continue
        if not q: lines.append(f"• {p['symbol']}: {qty} @ ₹{avg:g}, no price yet"); continue
        px, chg = q["price"], q.get("chg")
        v = qty * px; val += v; inv += qty * avg
        if chg is not None: day += qty * (px - px / (1 + chg / 100))
        sl = p.get("sl"); parts = [f"• {p['symbol']}: ₹{px:g}"]
        if chg is not None: parts.append(f"{sg(chg)} today")
        parts.append(f"P&L {sg((px / avg - 1) * 100)}")
        if sl:
            d = (px / sl - 1) * 100; parts.append(f"🛑 stop ₹{sl:g} BREACHED" if d <= 0 else f"stop ₹{sl:g} ({d:.1f}% away)")
            if sl < avg: risk += qty * (avg - sl)
            if 0 < d <= 3: parts.append("⚠️ close to stop")
            if d <= 3: flagged += 1
        if p.get("target"): parts.append(f"target ₹{p['target']:g} ({(p['target'] / px - 1) * 100:.1f}% to go)")
        if q.get("pct") is not None and q["pct"] < 0: parts.append(f"below {c_ma}-DMA ({q['pct']:+}%)"); flagged += 1
        lines.append(" · ".join(parts))
    return lines, dict(val=val, inv=inv, day=day, risk=risk, flagged=flagged)

def build(kind, pos, sj, now):
    ma = sj.get("ma_period", 44); lines, t = holdings_lines(pos, sj, ma)
    sig = sj.get("signals", []); n = lambda k: sum(1 for s in sig if s["type"] == k)
    h = sj.get("health") or {}
    head = f"☀️ Morning brief, {now:%a %d %b}" if kind == "morning" else f"🌆 Evening review, {now:%a %d %b}"
    out = [head]
    if h.get("price_date"):
        out.append(f"Last close: {h['price_date']}" if kind == "morning" else f"Prices: {h['price_date']} {'official close' if h.get('source') == 'official' else '(about 15 min delayed)'}")
    if lines:
        out.append(f"\nHoldings ({len(lines)})"); out += lines
        un = t["val"] - t["inv"]
        out.append(f"\nValue {inr(t['val'])} · unrealised {'+' if un >= 0 else '−'}{inr(abs(un))} ({sg(un / t['inv'] * 100 if t['inv'] else 0)})")
        if kind == "evening": out.append(f"Today {'+' if t['day'] >= 0 else '−'}{inr(abs(t['day']))}")
        if t["risk"]: out.append(f"Capital at risk if every stop hits: {inr(t['risk'])} ({t['risk'] / t['val'] * 100:.1f}% of value)")
        if t["flagged"]: out.append(f"{t['flagged']} item(s) need attention.")
    else: out.append("\nNo open holdings.")
    out.append(f"\nScreener: {n('buy')} in buy range, {n('near')} approaching, {n('sell')} just crossed below.")
    out.append("Log today's trades and why you took them in My Positions → Journal." if kind == "evening" else "Plan your trades before the open; act only on your rules.")
    out.append("\nResearch alert only, not financial advice.")
    return "\n".join(out)[:4000]

def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "morning"
    now = dt.datetime.now(IST)
    if now.weekday() >= 5: print("weekend"); return
    sj = read_json("signals.json", {})
    if not sj: print("no signals.json"); return
    sent = 0
    for u in cloud_users():
        if send_telegram(u["chat"], build(kind, u["positions"], sj, now)): sent += 1
    print("briefs sent:", sent)

if __name__ == "__main__":
    main()
