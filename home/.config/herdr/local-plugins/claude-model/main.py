#!/usr/bin/env python3
"""Informa ao herdr o modelo e o contexto usado de cada painel do Claude
(tokens $model e $ctx da sidebar).

Roda nos eventos de agente do herdr; lê o modelo e o uso de tokens da última
resposta na transcrição da sessão (~/.claude/projects/*/<session>.jsonl).
Tamanho da janela: CLAUDE_CTX_WINDOW (env) ou 1M (Haiku: 200k).
"""
import json, os, pathlib, re, subprocess

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
PROJECTS = pathlib.Path.home() / ".claude" / "projects"


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


def herdr(*args):
    return subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=5)


def main():
    out = herdr("pane", "list").stdout
    try:
        panes = json.loads(out)["result"]["panes"]
    except (ValueError, KeyError):
        return
    for pane in panes:
        if pane.get("agent") != "claude":
            # painel que deixou de ser Claude: remove o modelo antigo
            stale = [t for t in ("model", "ctx") if t in (pane.get("tokens") or {})]
            if stale:
                herdr("pane", "report-metadata", pane["pane_id"], "--source", "claude-model",
                      *[a for t in stale for a in ("--clear-token", t)])
            continue
        sid = (pane.get("agent_session") or {}).get("value")
        hits = list(PROJECTS.glob(f"*/{sid}.jsonl")) if sid else []
        model, usage = from_transcript(hits[0]) if hits else (None, {})
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

if __name__ == "__main__":
    main()
