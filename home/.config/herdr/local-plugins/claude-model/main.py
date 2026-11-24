#!/usr/bin/env python3
"""Informa ao herdr o modelo e o contexto usado de cada painel do Claude
(tokens $model e $ctx da sidebar).

Roda nos eventos de agente do herdr; lê o modelo e o uso de tokens da última
resposta na transcrição da sessão (~/.claude/projects/*/<session>.jsonl).
Tamanho da janela: CLAUDE_CTX_WINDOW (env) ou 1M (Haiku: 200k).
"""
import fcntl, json, os, pathlib, re, subprocess, time

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
PROJECTS = pathlib.Path.home() / ".claude" / "projects"
JOBS = pathlib.Path.home() / ".claude" / "jobs"


def pretty(model_id):
    # claude-opus-5-5 -> Opus 5.5 ; claude-haiku-4-5-20251001 -> Haiku 4.5
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$", model_id)
    if not m:
        return model_id
    name, major, minor = m.groups()
    return f"{name.capitalize()} {major}" + (f".{minor}" if minor else "")


def window(model_id, used):
    if os.environ.get("CLAUDE_CTX_WINDOW"):
        return int(os.environ["CLAUDE_CTX_WINDOW"])
    if "haiku" in model_id and used <= 200_000:
        return 200_000
    return 1_000_000


def ctx_bar(model_id, usage):
    used = sum(usage.get(k) or 0 for k in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    if not used:
        return None
    pct = min(1.0, used / window(model_id, used))
    k = f"{used / 1000:.0f}k" if used < 1_000_000 else f"{used / 1e6:.1f}M"
    return f"{pct * 100:.0f}% {k}"


def from_transcript(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 512_000))
            lines = f.read().decode(errors="ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"assistant"' not in line:
            continue
        try:
            msg = json.loads(line).get("message") or {}
        except ValueError:
            continue
        model = msg.get("model")
        if isinstance(model, str) and model.startswith("claude-"):
            return model, msg.get("usage") or {}
    return None, {}


def transcript_for(pane):
    """Transcrição da sessão do painel. Normalmente é <session>.jsonl; mas um
    `claude` conectado a uma sessão em background (fleet/daemon) reporta ao
    herdr o id do próprio cliente, que não tem transcrição. Nesse caso acha o
    job em ~/.claude/jobs cujo nome é o título do painel e usa a transcrição
    dele (linkScanPath)."""
    sid = (pane.get("agent_session") or {}).get("value")
    hits = list(PROJECTS.glob(f"*/{sid}.jsonl")) if sid else []
    if hits:
        return hits[0]
    title = (pane.get("terminal_title_stripped") or "").strip()
    if not title:
        return None
    found = []
    for state in JOBS.glob("*/state.json"):
        try:
            job = json.loads(state.read_text())
        except (OSError, ValueError):
            continue
        path = job.get("linkScanPath")
        if job.get("name") == title and path and os.path.exists(path):
            found.append(path)
    return found[0] if len(found) == 1 else None  # ambíguo: melhor não chutar


def herdr(*args):
    return subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=5)


def update():
    """Atualiza $model/$ctx de todos os painéis; devolve True se algum Claude
    está trabalhando (aí vale continuar atualizando)."""
    out = herdr("pane", "list").stdout
    try:
        panes = json.loads(out)["result"]["panes"]
    except (ValueError, KeyError):
        return False
    working = False
    for pane in panes:
        if pane.get("agent") == "claude" and pane.get("agent_status") == "working":
            working = True
        if pane.get("agent") != "claude":
            # painel que deixou de ser Claude: remove o modelo antigo
            stale = [t for t in ("model", "ctx") if t in (pane.get("tokens") or {})]
            if stale:
                herdr("pane", "report-metadata", pane["pane_id"], "--source", "claude-model",
                      *[a for t in stale for a in ("--clear-token", t)])
            continue
        path = transcript_for(pane)
        model, usage = from_transcript(path) if path else (None, {})
        want = {"model": f"✳ {pretty(model)}" if model else None,
                "ctx": ctx_bar(model, usage) if model else None}
        have = pane.get("tokens") or {}
        args = []
        for name, value in want.items():
            if have.get(name) == value:
                continue
            args += ["--token", f"{name}={value}"] if value else ["--clear-token", name]
        if args:
            herdr("pane", "report-metadata", pane["pane_id"], "--source", "claude-model", *args)
    return working


def watch():
    """Os eventos só chegam quando o status muda: no 1º turno de uma sessão a
    transcrição ainda não tem resposta (modelo não aparece) e, em turnos
    longos, o $ctx fica parado. Enquanto algum Claude estiver trabalhando,
    um único processo em segundo plano (flock) reatualiza a cada INTERVAL s."""
    lock_path = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "herdr-claude-model.lock"
    if os.fork():
        return
    os.setsid()
    if os.fork():
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    try:
        lock = open(lock_path, "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os._exit(0)  # já tem um watcher rodando
    deadline = time.monotonic() + MAX_WATCH
    try:
        while time.monotonic() < deadline:
            time.sleep(INTERVAL)
            if not update():
                break
    finally:
        os._exit(0)


INTERVAL = 5          # segundos entre atualizações enquanto trabalha
MAX_WATCH = 2 * 3600  # trava de segurança


def main():
    if update():
        watch()


if __name__ == "__main__":
    main()
