"""Runs the screener on an exact 15-minute rhythm for part of the day inside ONE GitHub job.
GitHub's own cron may start a job 5-20 minutes late, but once this job is running it keeps time itself.
Usage: python session.py --until 12:30      (slots: 08:45 morning brief, 09:15 ... 16:15 scans, 16:00 = summary + evening review)"""
import argparse, datetime as dt, json, subprocess, sys, time
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30)); ROOT = Path(__file__).resolve().parent
def now(): return dt.datetime.now(IST)
def hm(s): h, m = s.split(":"); return dt.time(int(h), int(m))

def slots_for(day):
    out, t = [], dt.datetime.combine(day, dt.time(8, 45), IST)
    while t.time() <= dt.time(16, 15):
        if t.time() == dt.time(8, 45) or t.time() >= dt.time(9, 15): out.append(t)
        t += dt.timedelta(minutes=15 if t.time() != dt.time(8, 45) else 30)
    return out

def py(*args, timeout=540):
    try: return subprocess.run([sys.executable, *args], cwd=ROOT, timeout=timeout).returncode
    except subprocess.TimeoutExpired: print("timed out:", args, flush=True); return 124

def write_status(slot, rc, st):
    fails = 0 if rc == 0 else st.get("fails", 0) + 1
    st = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "slot": slot.strftime("%H:%M"), "rc": rc, "fails": fails}
    (ROOT / "status.json").write_text(json.dumps(st)); return st

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--until", default="16:30"); a = ap.parse_args()
    until, done, st = hm(a.until), None, {}
    while True:
        n = now()
        if n.weekday() >= 5 or n.time() >= until: break
        todo = [s for s in slots_for(n.date()) if s <= n and s.time() < until and (done is None or s > done)]
        if not todo:
            nxt = [s for s in slots_for(n.date()) if s > n and s.time() < until]
            if not nxt: break
            time.sleep(max(1, min((nxt[0] - n).total_seconds() + 1, 240))); continue
        slot = todo[-1]; done = slot; t = slot.time()
        print(f"=== slot {t:%H:%M} (now {now():%H:%M:%S}) ===", flush=True)
        if t == dt.time(8, 45):
            rc = py("brief.py", "morning", timeout=240)
        else:
            rc = py("screen.py", *(["--summary"] if t == dt.time(16, 0) else []))
            if t == dt.time(16, 0) and rc == 0: py("brief.py", "evening", timeout=240)
        st = write_status(slot, rc, st)
        subprocess.run(["bash", "save.sh"], cwd=ROOT)

if __name__ == "__main__":
    main()
