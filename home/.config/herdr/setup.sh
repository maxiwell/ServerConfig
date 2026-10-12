#!/usr/bin/env bash
# Resolve as pendências do ~/.config/herdr neste servidor:
#   - confere herdr e python3 no PATH e servidor no ar
#   - deixa os scripts da tab bar executáveis
#   - linka (e habilita) todos os plugins em local-plugins/
#   - roda a ação "refresh" de cada plugin linkado e mostra os tokens
# Idempotente: pode rodar quantas vezes quiser.
set -euo pipefail

CFG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$CFG/local-plugins"

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }

echo "== Pré-requisitos"
command -v herdr  >/dev/null || fail "herdr não está no PATH (esperado em ~/.local/bin/herdr)"
command -v python3 >/dev/null || fail "python3 não encontrado (os plugins usam python3)"
ok "herdr $(herdr --version 2>/dev/null | awk '{print $2}') / $(python3 --version)"

if ! herdr pane list >/dev/null 2>&1; then
  fail "servidor herdr não responde. Abra o herdr (ou 'herdr server') e rode de novo."
fi
ok "servidor herdr respondendo"

echo "== Scripts da tab bar"
for f in "$CFG"/*.sh "$CFG"/*.py; do
  [ -e "$f" ] || continue
  [ "$f" = "$CFG/setup.sh" ] && continue
  if [ ! -x "$f" ]; then chmod +x "$f"; ok "chmod +x $(basename "$f")"; else ok "$(basename "$f") executável"; fi
done

echo "== Plugins locais"
[ -d "$PLUGINS_DIR" ] || { warn "sem diretório local-plugins/"; exit 0; }

installed="$(herdr plugin list 2>/dev/null || true)"
linked=()
for dir in "$PLUGINS_DIR"/*/; do
  dir="${dir%/}"
  manifest="$dir/herdr-plugin.toml"
  [ -f "$manifest" ] || { warn "$(basename "$dir"): sem herdr-plugin.toml, ignorado"; continue; }
  id="$(sed -n 's/^id *= *"\(.*\)"/\1/p' "$manifest" | head -1)"
  [ -n "$id" ] || { warn "$(basename "$dir"): manifesto sem id, ignorado"; continue; }

  if grep -q "^- $id " <<<"$installed"; then
    if grep -q "^- $id .* disabled" <<<"$installed"; then
      herdr plugin enable "$id" >/dev/null && ok "$id: habilitado"
    else
      ok "$id: já linkado"
    fi
  else
    herdr plugin link "$dir" --enabled >/dev/null && ok "$id: linkado de $dir"
  fi
  linked+=("$id")
done

echo "== Ações de refresh"
for id in "${linked[@]}"; do
  if herdr plugin action list --plugin "$id" 2>/dev/null | grep -q '"action_id":"refresh"'; then
    herdr plugin action invoke refresh --plugin "$id" >/dev/null && ok "$id: refresh invocado"
  else
    warn "$id: sem ação refresh (vai atualizar nos eventos)"
  fi
done
sleep 2

echo "== Tokens dos painéis"
herdr pane list | python3 -c '
import json, sys
for p in json.load(sys.stdin)["result"]["panes"]:
    print("  %-8s agent=%-8s tokens=%s" % (p["pane_id"], p.get("agent", "-"), p.get("tokens") or {}))'

echo "== Log dos plugins (último)"
herdr plugin log 2>/dev/null | python3 -c '
import json, sys
logs = json.load(sys.stdin)["result"]["logs"]
for l in logs[-3:]:
    print("  %s/%s: %s exit=%s %s" % (l["plugin_id"], l.get("action_id"), l["status"], l.get("exit_code"), (l.get("stderr") or "").strip()[:200]))
' || true

echo
ok "pronto. Se a sidebar não refletir, rode: herdr server reload-config"
