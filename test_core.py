"""Quick self-checks for the parts that must not break. Run: python test_core.py"""
import numpy as np, pandas as pd
import datetime as dt, json, sys
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

def t_auto_levels():
    """Automatic stop/target: chosen rule applied from the buy date, stop never moves down, your own number overrides, alerts follow."""
    import exitrules as X
    store = {}
    def fake(cmd):
        if cmd[0] == "GET": return store.get(cmd[1])
        if cmd[0] == "SET": store[cmd[1]] = cmd[2]; return "OK"
    old = screen.redis; screen.redis = fake
    try:
        screen.EXITS.clear(); screen.EXITS.update({"_default": "screener", "_date": "2026-10-09", "_rules": {},
            "screener": dict(rule=dict(fam="trail", t=10, hold=40, id="trail-t10-h40"), name="Screener Buy", score=0.01, label="Trailing stop 10%",
                             rule_all=dict(fam="fix", sp=8, tp=20, hold=40, id="fix-sp8-tp20-h40"), score_all=0.02, label_all="Stop -8%, target +20%")})
        idx = pd.bdate_range("2026-06-01", periods=40)
        c = np.r_[np.linspace(100, 130, 30), np.linspace(129, 120, 10)]
        df = pd.DataFrame(dict(Open=c, High=c * 1.005, Low=c * 0.995, Close=c, Volume=1e6), index=idx)
        p = dict(id="p1", symbol="AAA", exchange="NSE", qty=10, avg=100.0, alertSl=True, alertTg=True, alertMa=False,
                 txns=[dict(type="buy", date="2026-06-20", qty=10, price=100.0)])
        screen.PXD["NSE:AAA"] = df
        u = dict(uid="u1", chat="1", positions=[p], watchlist=[])
        auto, ch = screen.update_auto([u], True)
        a = auto["u1"]["NSE:AAA"]
        assert a["entry_date"] == "2026-06-22" or a["entry_date"] == "2026-06-20", a
        assert abs(a["sl"] - 130 * 0.9) < 0.6 and a["target"] is None and a["exit"] is None and a["basis"] == "recent", a
        ua = dict(u, uid="u2", settings={"exitAll": 1}); aa = screen.update_auto([ua], True)[0]["u2"]["NSE:AAA"]
        assert aa["rule"] == "fix-sp8-tp20-h40" and aa["basis"] == "all" and aa["target"] == 120.0, aa
        # price falls: the trailing stop does not come down; at 116 the stop (117) is hit
        df2 = pd.concat([df, pd.DataFrame(dict(Open=[118.0], High=[118.5], Low=[116.0], Close=[116.5], Volume=[1e6]), index=[idx[-1] + pd.tseries.offsets.BDay()])])
        screen.PXD["NSE:AAA"] = df2
        auto2, _ = screen.update_auto([u], True)
        b = auto2["u1"]["NSE:AAA"]
        assert b["exit"] and b["exit"]["why"] == "stop", b
        ev = screen.position_events([p], {"NSE:AAA": {"price": 116.5, "pct": 1}}, {"ma_period": 44, "near_pct": 2}, auto2["u1"])
        assert any(k.endswith(":ax") and "STOP LOSS hit (automatic)" in m for k, m in ev), ev
        # your own stop wins over the automatic one
        pm = dict(p, sl=110.0, slMode="manual")
        e = screen.effective(pm, b)
        assert e["sl"] == 110.0 and not e["sl_auto"]
        ev = screen.position_events([pm], {"NSE:AAA": {"price": 109, "pct": 1}}, {"ma_period": 44, "near_pct": 2}, auto2["u1"])
        assert any(k.endswith(":sl") and "stop ₹110" in m for k, m in ev), ev
        # a stop that moved by 0.5% or more is announced once
        screen.PXD["NSE:AAA"] = df.iloc[:25]
        store.clear(); screen.update_auto([u], True)
        screen.PXD["NSE:AAA"] = df
        _, ch = screen.update_auto([u], True)
        assert ch["u1"][0][2][0][0] == "stop" and ch["u1"][0][2][0][2] > ch["u1"][0][2][0][1], ch
        lv = screen.level_events(ch["u1"]); assert "automatic stop" in lv[0][1], lv
        _, ch = screen.update_auto([u], True); assert not ch, ch   # announced once
    finally:
        screen.redis = old; screen.EXITS.clear(); screen.PXD.clear()

def t_listings():
    """Shares on both exchanges get their BSE code; BSE positions use it for prices; names come from the exchange lists."""
    import tempfile, shutil, pathlib
    d = pathlib.Path(tempfile.mkdtemp()); old_root = screen.ROOT
    for f in ("universe_nse.csv", "universe_bse.csv"): shutil.copy(old_root / f, d / f)
    try:
        screen.ROOT = d; screen.LST.clear(); screen.BHAV.setdefault("NSE", ("2026-10-12", {})); screen.BHAV["BSE"] = ("2026-10-12", {})
        screen.BSE_ISIN.clear(); screen.BSE_ISIN.update({"INE742F01042": "532921", "INE900L01028": "541967"})
        screen.write_listings()
        L = json.loads((d / "listings.json").read_text())
        assert L["n"]["ADANIPORTS"] == ["Adani Ports and Special Economic Zone Limited", "532921"], L["n"]["ADANIPORTS"]
        assert L["n"]["MBAPL"][1] == "541967" and L["dual"] == 2
        assert screen.pos_tickers({"symbol": "ADANIPORTS", "exchange": "BSE"}) == ["ADANIPORTS.BO", "532921.BO"]
        assert screen.pos_yahoo({"symbol": "ADANIPORTS", "exchange": "NSE"}) == "ADANIPORTS.NS"
        bs = next(iter(L["b"])); assert screen.pos_tickers({"symbol": bs, "exchange": "BSE"})[0] == L["b"][bs][1] + ".BO"
        assert screen.share_name("ADANIPORTS", "BSE") == "Adani Ports and Special Economic Zone Limited"
        m = (d / "listings.json").stat().st_mtime_ns; screen.write_listings(); assert (d / "listings.json").stat().st_mtime_ns == m   # unchanged: not rewritten
    finally:
        screen.ROOT = old_root; screen.LST.clear(); screen.BSE_ISIN.clear(); screen.BHAV.pop("BSE", None); screen.BHAV.pop("NSE", None)

def t_position_quotes_bse():
    """A BSE holding gets a price from whichever Yahoo ticker has it, and the quote carries its name and exchange."""
    old_f, old_r, old_L = screen.fetch, screen.reconcile, dict(screen.LST)
    idx = pd.bdate_range("2026-07-01", periods=60); df = pd.DataFrame(dict(Open=1750.0, High=1760.0, Low=1740.0, Close=np.linspace(1700, 1754, 60), Volume=1e5), index=idx)
    try:
        screen.LST.clear(); screen.LST.update({"n": {"ADANIPORTS": ["Adani Ports and Special Economic Zone Limited", "532921"]}, "b": {"XYZ": ["Xyz Ltd", "500001"]}})
        for got in ({"532921.BO": df}, {"ADANIPORTS.BO": df}):
            screen.fetch = lambda tickers, **k: {t: got[t] for t in tickers if t in got}; screen.reconcile = lambda *a, **k: None
            q = screen.position_quotes([{"symbol": "ADANIPORTS", "exchange": "BSE"}], {"ma_type": "SMA", "ma_period": 44})
            v = q["BSE:ADANIPORTS"]; assert v["price"] == 1754.0 and v["exchange"] == "BSE" and v["name"].startswith("Adani Ports"), v
        calls = []
        def flaky(tickers, **k):   # first batch drops the ticker, the retry returns it
            calls.append(list(tickers)); return {} if len(calls) == 1 else {t: df for t in tickers if t == "ADANIPORTS.BO"}
        screen.fetch = flaky
        assert screen.position_quotes([{"symbol": "ADANIPORTS", "exchange": "BSE"}], {"ma_type": "SMA", "ma_period": 44})["BSE:ADANIPORTS"]["price"] == 1754.0 and len(calls) == 2
        screen.fetch = lambda tickers, **k: {}
        assert screen.position_quotes([{"symbol": "ADANIPORTS", "exchange": "BSE"}], {"ma_type": "SMA", "ma_period": 44}) == {}
    finally:
        screen.fetch, screen.reconcile = old_f, old_r; screen.LST.clear(); screen.LST.update(old_L); screen.PXD.clear()

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("t_"): f(); print("PASS", k)
    print("ALL PASS")
