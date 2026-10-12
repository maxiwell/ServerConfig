#!/usr/bin/env python3
"""Informa ao herdr o modelo de cada painel do Claude (token $model da sidebar).

Roda nos eventos de agente do herdr; lê o modelo da última resposta na
transcrição da sessão (~/.claude/projects/*/<session>.jsonl).
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
            return model
    return None


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
            if "model" in (pane.get("tokens") or {}):
                herdr("pane", "report-metadata", pane["pane_id"], "--source", "claude-model", "--clear-token", "model")
            continue
        sid = (pane.get("agent_session") or {}).get("value")
        hits = list(PROJECTS.glob(f"*/{sid}.jsonl")) if sid else []
        model = from_transcript(hits[0]) if hits else None
        want = {"model": f"✳ {pretty(model)}" if model else None}
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
