#!/usr/bin/env bash
# Liga motor + worker + painel e abre o navegador quando estiver pronto. Ctrl+C para parar.
cd "$(dirname "$0")/.." || exit 1
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
export PATH="$HOME/.local/bin:$PNPM_HOME:$HOME/Library/pnpm:$PATH"
URL="http://127.0.0.1:3000"
open_url() { (xdg-open "$1" || open "$1") >/dev/null 2>&1 & }

if curl -fs "$URL/api/engine/health" >/dev/null 2>&1; then
  echo "STARK já está rodando: $URL"
  open_url "$URL"
  exit 0
fi
command -v pnpm >/dev/null 2>&1 || { echo "pnpm não encontrado: rode antes  bash scripts/install.sh" >&2; exit 1; }
[ -f apps/web/.next/BUILD_ID ] || pnpm run build

( for _ in $(seq 1 90); do
    sleep 2
    if curl -fs "$URL/api/engine/health" >/dev/null 2>&1; then
      echo; echo "✔ STARK pronto: $URL  (celular: pnpm run phone)"
      [ "${STARK_NO_BROWSER:-}" = "1" ] || open_url "$URL"
      break
    fi
  done ) &
exec pnpm start
