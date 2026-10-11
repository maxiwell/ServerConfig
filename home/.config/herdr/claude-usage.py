#!/usr/bin/env python3
"""Uso do Claude (5h / semanal / semanal por modelo) para a tab bar do herdr.

Lê de um cache e retorna na hora; se o cache tiver mais de MAX_AGE segundos,
dispara em segundo plano uma consulta ao `claude -p` (get_usage, não gasta cota).
"""
import json, os, subprocess, sys, time

CACHE = os.path.expanduser("~/.cache/herdr-claude-usage.json")
LOCK = CACHE + ".lock"
MAX_AGE = 300


def fetch():
    req = {"type": "control_request", "request_id": "r1",
           "request": {"subtype": "get_usage", "skip_behaviors": True}}
    out = subprocess.run(
        ["claude", "-p", "--verbose", "--safe-mode", "--input-format", "stream-json",
         "--output-format", "stream-json", "--no-session-persistence"],
        input=json.dumps(req) + "\n", capture_output=True, text=True, timeout=60,
    ).stdout
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "control_response":
            resp = d.get("response") or {}
            if resp.get("subtype") == "success":
                return resp.get("response") or {}
    return None


def refresh():
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        if time.time() - os.path.getmtime(LOCK) < 120:
            return
        os.remove(LOCK)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL)
    os.close(fd)
    try:
        doc = fetch()
        if doc:
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(doc, f)
            os.replace(tmp, CACHE)
    finally:
        os.remove(LOCK)


def pct(g):
    if not isinstance(g, dict) or g.get("utilization") is None:
        return "?"
    return f"{round(g['utilization'])}%" + ("⛔" if g.get("locked_reason") else "")


def main():
    if sys.argv[1:] == ["--refresh"]:
        refresh()
        return
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    try:
        age = time.time() - os.path.getmtime(CACHE)
        with open(CACHE) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        age, doc = None, None
    if age is None or age > MAX_AGE:
        subprocess.Popen([sys.executable, __file__, "--refresh"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not doc:
        print("… │")
        return
    rl = doc.get("rate_limits") or {}
    # 5h / semanal / semanal por modelo (ex.: Fable)
    gauges = [rl.get("five_hour"), rl.get("seven_day"), *(rl.get("model_scoped") or [])]
    stale = "~" if age is not None and age > MAX_AGE * 3 else ""
    print(" / ".join(pct(g) for g in gauges) + stale + " │")


if __name__ == "__main__":
    main()
