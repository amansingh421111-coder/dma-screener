"""Quick self-checks for the parts that must not break. Run: python test_core.py"""
import datetime as dt, sys
import screen, session, watchdog, brief

def t_slots():
    s = [x.strftime("%H:%M") for x in session.slots_for(dt.date(2026, 10, 9))]
    assert s[0] == "08:45" and s[1] == "09:15" and s[-1] == "16:15" and len(s) == 30, s

def t_watchdog():
    IST = screen.IST; n = dt.datetime(2026, 10, 9, 11, 0, tzinfo=IST)
    mk = lambda m, f=0: {"ts": (n - dt.timedelta(minutes=m)).astimezone(dt.timezone.utc).isoformat(), "slot": "10:45", "fails": f}
    assert watchdog.check(n, mk(10)) is None
    assert "40 minutes" in watchdog.check(n, mk(40))
    assert "failed" in watchdog.check(n, mk(5, 2))
    assert watchdog.check(n.replace(hour=8), mk(400)) is None            # before market
    assert watchdog.check(n.replace(day=10), mk(400)) is None            # Saturday

def t_xcheck():
    screen.BHAV["NSE"] = ("d", {"AAA": (1, 1, 1, 100.0, 100000, 0, 0, 0, 0), "BBB": (1, 1, 1, 200.0, 100000, 0, 0, 0, 0)})
    screen.BHAV["BSE"] = ("d", {"111": (1, 1, 1, 100.1, 9000, 0, 0, 0, 0), "222": (1, 1, 1, 190.0, 9000, 0, 0, 0, 0)})
    screen.BSE_ISIN.update({"INA": "111", "INB": "222"})
    r = screen.xcheck([{"symbol": "AAA", "isin": "INA"}, {"symbol": "BBB", "isin": "INB"}])
    assert r["pairs"] == 2 and r["mismatch"] == 1 and r["worst"][0]["symbol"] == "BBB", r

def t_watch():
    q = {"NSE:AAA": {"price": 100, "pct": 1.2}}; c = {"ma_period": 44, "buy_max_pct": 5}
    ev = screen.watch_events([{"id": "1", "symbol": "AAA", "exchange": "NSE", "alertBuy": True, "above": 99}], q, c)
    assert [e[0] for e in ev] == ["W:NSE:AAA#1:w1", "W:NSE:AAA#1:w3"], ev

def t_brief():
    sj = {"ma_period": 44, "signals": [], "quotes": {"NSE:X": {"price": 90, "pct": -1, "chg": -1}}}
    m = brief.build("morning", [{"symbol": "X", "exchange": "NSE", "qty": 10, "avg": 100, "sl": 95}], sj, dt.datetime(2026, 10, 12, 8, 45))
    assert "BREACHED" in m and "Morning brief" in m and "not financial advice" in m

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("t_"): f(); print("PASS", k)
    print("ALL PASS")
