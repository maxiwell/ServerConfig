#!/bin/sh
# Tab bar do herdr: "dono/repo [branch] │" (sem remote: "[branch] │")
# Também dispara o plugin git-dirty em segundo plano (token $dirty da sidebar),
# no máximo a cada DIRTY_EVERY segundos: o plugin faz git status em todos os
# worktrees (~0,3 s) e rodar a cada tick da tab bar custava ~15% de um core.
DIRTY_EVERY=30
stamp="${XDG_RUNTIME_DIR:-/tmp}/herdr-git-dirty.stamp"
now=$(date +%s)
last=$(cat "$stamp" 2>/dev/null || echo 0)
if [ $((now - last)) -ge "$DIRTY_EVERY" ]; then
  echo "$now" > "$stamp"
  setsid python3 ~/.config/herdr/local-plugins/git-dirty/main.py >/dev/null 2>&1 </dev/null &
fi
b=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
url=$(git remote get-url origin 2>/dev/null || git remote get-url "$(git remote | head -n1)" 2>/dev/null)
repo=$(printf '%s' "$url" | sed -E 's#\.git/?$##; s#/+$##; s#^.*[:/]([^/:]+/[^/:]+)$#\1#')
[ -n "$repo" ] && printf '%s [%s] │\n' "$repo" "$b" || printf '[%s] │\n' "$b"
