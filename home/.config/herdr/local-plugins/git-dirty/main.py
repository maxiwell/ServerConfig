#!/usr/bin/env python3
"""Informa ao herdr a branch do checkout de cada workspace (token $branch da
sidebar) e um "✎" quando há alterações não commitadas (token $branch_dirty, ao
lado da branch). Se a branch tem o nome do workspace, não a repete: o "✎" vai
para o token $dirty, na linha do nome.

Roda nos eventos de agente do herdr e também a cada tick do git-info.sh
(tab bar, no máximo a cada 30 s), para pegar edições feitas fora dos agentes.
"""
import fcntl, json, os, pathlib, shutil, subprocess

HERDR = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or str(pathlib.Path.home() / ".local/bin/herdr")
LOCK = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "herdr-git-dirty.lock"


def herdr(*args):
    return subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=5)


def branch(path):
    try:
        r = subprocess.run(["git", "-C", path, "status", "--porcelain=v2", "--branch"],
                           capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    lines = r.stdout.splitlines()
    head = next((l.split(" ", 2)[2] for l in lines if l.startswith("# branch.head ")), None)
    if not head:
        return None
    return head, any(not l.startswith("#") for l in lines)


def main():
    # evita execuções sobrepostas (tick de 2s + eventos)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    try:
        workspaces = json.loads(herdr("workspace", "list").stdout)["result"]["workspaces"]
        panes = json.loads(herdr("pane", "list").stdout)["result"]["panes"]
    except (ValueError, KeyError):
        return
    first_cwd = {}
    for pane in panes:
        first_cwd.setdefault(pane.get("workspace_id"), pane.get("cwd"))
    for ws in workspaces:
        wid = ws["workspace_id"]
        path = (ws.get("worktree") or {}).get("checkout_path") or first_cwd.get(wid)
        head, dirty = (branch(path) if path else None) or (None, False)
        mark = "✎" if dirty else None
        if head == ws.get("label"):
            want = {"branch": None, "branch_dirty": None, "dirty": mark}
        else:
            want = {"branch": head, "branch_dirty": mark, "dirty": None}
        tokens = ws.get("tokens") or {}
        args = []
        for name, value in want.items():
            if tokens.get(name) == value:
                continue
            args += ["--token", f"{name}={value}"] if value else ["--clear-token", name]
        if not args:
            continue
        herdr("workspace", "report-metadata", wid, "--source", "git-dirty", *args)


if __name__ == "__main__":
    main()
