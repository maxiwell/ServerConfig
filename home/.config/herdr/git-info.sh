#!/bin/sh
# Tab bar do herdr: "dono/repo [branch] │" (sem remote: "[branch] │")
b=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
url=$(git remote get-url origin 2>/dev/null || git remote get-url "$(git remote | head -n1)" 2>/dev/null)
repo=$(printf '%s' "$url" | sed -E 's#\.git/?$##; s#/+$##; s#^.*[:/]([^/:]+/[^/:]+)$#\1#')
[ -n "$repo" ] && printf '%s [%s] │\n' "$repo" "$b" || printf '[%s] │\n' "$b"
