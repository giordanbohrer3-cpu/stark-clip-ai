#!/usr/bin/env bash
# Liga motor + worker + painel e abre o navegador quando estiver pronto. Ctrl+C para parar.
# Antes de ligar, atualiza sozinho do GitHub (STARK_NO_UPDATE=1 desliga).
cd "$(dirname "$0")/.." || exit 1
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
export PATH="$HOME/.local/bin:$PNPM_HOME:$HOME/Library/pnpm:$PATH"
URL="http://127.0.0.1:3000"
open_url() { (xdg-open "$1" || open "$1") >/dev/null 2>&1 & }

if curl -fs "$URL/api/engine/health" >/dev/null 2>&1; then
  echo "STARK já está rodando: $URL  (para atualizar: bash scripts/update.sh)"
  open_url "$URL"
  exit 0
fi
command -v pnpm >/dev/null 2>&1 || { echo "pnpm não encontrado: rode antes  bash scripts/install.sh" >&2; exit 1; }

if [ "${STARK_NO_UPDATE:-}" != "1" ] && [ -d .git ]; then
  OLD=$(git rev-parse HEAD)
  if GIT_TERMINAL_PROMPT=0 git pull --ff-only -q 2>/dev/null; then
    if [ "$OLD" != "$(git rev-parse HEAD)" ]; then
      echo "▶ Versão nova baixada. Atualizando (1–3 min)…"
      STARK_NO_START=1 bash scripts/install.sh || echo "aviso: atualização falhou; tentando ligar mesmo assim" >&2
    fi
  else
    echo "aviso: sem atualizar agora (sem internet, login do GitHub ou alterações locais). Usando a versão atual."
  fi
fi
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
