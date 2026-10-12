#!/usr/bin/env python3
"""Uso do Claude (5h / semanal / semanal por modelo) para a tab bar do herdr.

Lê de um cache e retorna na hora; se o cache tiver mais de MAX_AGE segundos,
dispara em segundo plano uma consulta ao `claude -p` (get_usage, não gasta cota).

  claude-usage.py          linha compacta para a tab bar
  claude-usage.py --full   detalhes (popup do herdr, prefix+u); fecha com qualquer tecla
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone

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


DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def load_cache():
    """(idade em segundos, doc) do cache; (None, None) se não existir/estiver corrompido."""
    try:
        age = time.time() - os.path.getmtime(CACHE)
        with open(CACHE) as f:
            return age, json.load(f)
    except (OSError, ValueError):
        return None, None


def spawn_refresh_if_stale(age):
    if age is None or age > MAX_AGE:
        subprocess.Popen([sys.executable, __file__, "--refresh"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reset_info(g):
    """('sáb 07:00', '5d 16h') a partir de resets_at; ('?', '?') se não houver."""
    iso = (g or {}).get("resets_at")
    if not iso:
        return "?", "?"
    try:
        when = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return "?", "?"
    now = datetime.now(timezone.utc).astimezone()
    label = when.strftime("%H:%M") if when.date() == now.date() else f"{DIAS[when.weekday()]} {when:%H:%M}"
    secs = max(0, int((when - now).total_seconds()))
    d, h, m = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    left = f"{d}d {h}h" if d else (f"{h}h {m:02d}m" if h else f"{m}m")
    return label, left


def full(age, doc):
    if not doc:
        print("sem dados de cota ainda (cache vazio); tente de novo em alguns segundos")
    else:
        rl = doc.get("rate_limits") or {}
        rows = [("5h", rl.get("five_hour")), ("semana", rl.get("seven_day"))]
        rows += [(f"semana {g.get('display_name', 'modelo')}", g) for g in rl.get("model_scoped") or []]
        print(f"Cotas do Claude ({doc.get('subscription_type', '?')})")
        print()
        for name, g in rows:
            label, left = reset_info(g)
            lock = f"  ⛔ {g.get('locked_reason')}" if (g or {}).get("locked_reason") else ""
            print(f"  {name:<14} {pct(g):>4}   renova {label:<10} (faltam {left}){lock}")
        print()
        print(f"  atualizado há {int(age // 60)} min" if age is not None else "")
    print("\n[qualquer tecla fecha]", end="", flush=True)
    try:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        try:
            input()
        except EOFError:
            pass


def pct(g):
    if not isinstance(g, dict) or g.get("utilization") is None:
        return "?"
    return f"{round(g['utilization'])}%" + ("⛔" if g.get("locked_reason") else "")


def main():
    if sys.argv[1:] == ["--refresh"]:
        refresh()
        return
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    age, doc = load_cache()
    spawn_refresh_if_stale(age)
    if sys.argv[1:] == ["--full"]:
        full(age, doc)
        return
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
