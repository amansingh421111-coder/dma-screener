"""Warns on Telegram when the screener has stopped (no completed run for 25 minutes in market hours, or two failed runs).
Runs from its own small workflow, so it still fires when the main one is not running."""
import datetime as dt, json, sys
from pathlib import Path
from screen import IST, ROOT, redis, send_telegram, cloud_users, notify

def check(now=None, status=None):
    now = now or dt.datetime.now(IST)
    if now.weekday() >= 5 or not (dt.time(9, 30) <= now.time() <= dt.time(16, 20)): return None
    if status is None:
        f = ROOT / "status.json"
        if not f.exists(): return "status.json is missing: the screener has never reported in."
        status = json.loads(f.read_text())
    age = (now - dt.datetime.fromisoformat(status["ts"]).astimezone(IST)).total_seconds() / 60
    if age > 25: return f"No screener run has completed for {age:.0f} minutes (last: {status.get('slot', '?')} IST)."
    if status.get("fails", 0) >= 2: return f"The last {status['fails']} screener runs failed (slot {status.get('slot', '?')} IST)."
    return None

def main():
    msg = check()
    if not msg: print("healthy"); return
    try: first = redis(["SET", "wd:last", dt.datetime.now(IST).isoformat(), "NX", "EX", 1800])
    except Exception as e: print("redis unavailable:", e); first = "OK"
    if not first: print("already warned recently"); return
    text = "⚠️ Screener health\n" + msg + "\nOpen GitHub → Actions to check. Alerts may be delayed until it recovers."
    sent = False
    for u in cloud_users(): sent = send_telegram(u["chat"], text) or sent
    if not sent: notify(text)
    print("warned:", msg)

if __name__ == "__main__":
    main()
