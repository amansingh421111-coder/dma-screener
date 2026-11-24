"""Runs the screener on an exact 15-minute rhythm for part of the day inside ONE GitHub job.
GitHub's own cron may start a job late during peak queue loads; once this job is running it keeps time itself and catches up if started late.
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
    slot_str = slot.strftime("%H:%M") if hasattr(slot, "strftime") else str(slot)
    st = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "slot": slot_str, "rc": rc, "fails": fails}
    (ROOT / "status.json").write_text(json.dumps(st)); return st

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--until", default="16:30"); a = ap.parse_args()
    until, done, st = hm(a.until), None, {}
    n = now()

    # Weekend check
    if n.weekday() >= 5:
        print("Weekend: skipping session.", flush=True)
        return

    # Guard: strictly reject execution in late evening, night, or pre-dawn (e.g. runner queue delay)
    if n.time() > dt.time(16, 45) or n.time() < dt.time(8, 0):
        print(f"Session started outside operating window ({n:%H:%M:%S} IST). Skipping to prevent late night alerts.", flush=True)
        return

    # If triggered in the post-market EOD window (16:00 to 16:45 IST):
    if n.time() >= dt.time(16, 0):
        print(f"Session started in EOD window ({n:%H:%M:%S} IST). Running EOD summary scan...", flush=True)
        rc = py("screen.py", "--summary", "--force")
        if rc == 0: py("brief.py", "evening", timeout=240)
        write_status(dt.datetime.combine(n.date(), dt.time(16, 0), IST), rc, st)
        subprocess.run(["bash", "save.sh"], cwd=ROOT)
        return

    # If morning brief has not yet been sent today and we are starting in the morning:
    state_file = ROOT / "state.json"
    st_data = {}
    try: st_data = json.loads(state_file.read_text())
    except Exception: pass
    if n.time() < dt.time(10, 30) and st_data.get("brief_morning") != str(n.date()):
        print(f"Morning brief not yet sent today. Running morning brief ({n:%H:%M:%S} IST)...", flush=True)
        py("brief.py", "morning", timeout=240)

    # If a morning session was delayed past 12:30 but is still within trading hours, extend it to 16:30
    if until <= dt.time(12, 30) and n.time() >= until and n.time() < dt.time(16, 30):
        print(f"Morning session started late at {n:%H:%M:%S} IST. Extending until 16:30 IST.", flush=True)
        until = dt.time(16, 30)

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

    # Fallback catch-up: if the session ran and ended without executing even one slot:
    if done is None and n.weekday() < 5:
        if n.time() > dt.time(16, 45) or n.time() < dt.time(8, 0):
            print(f"Session ended outside operating window ({n:%H:%M:%S} IST). Skipping fallback catch-up.", flush=True)
            return
        print(f"No slots executed in session window (time {n:%H:%M:%S} IST). Running catch-up scan...", flush=True)
        is_eod = n.time() >= dt.time(16, 0)
        rc = py("screen.py", "--summary" if is_eod else "--force")
        if is_eod and rc == 0:
            py("brief.py", "evening", timeout=240)
        write_status(n, rc, st)
        subprocess.run(["bash", "save.sh"], cwd=ROOT)

if __name__ == "__main__":
    main()
