#!/usr/bin/env bash
# Liga o Clipzou (motor + worker + radar + painel).
# Com o serviço instalado (padrão), roda escondido: liga com o PC, reinicia se cair e se atualiza sozinho
# quando sai versão nova no GitHub. O ícone do menu só abre o app.
cd "$(dirname "$0")/.." || exit 1
ROOT="$PWD"
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
export PATH="$HOME/.local/bin:$PNPM_HOME:$HOME/Library/pnpm:$PATH"
URL="http://127.0.0.1:3000"
DATA="$ROOT/services/engine/data"
mkdir -p "$DATA"
open_url() { [ "${STARK_NO_BROWSER:-}" = "1" ] || [ "${STARK_SERVICE:-}" = "1" ] || { (xdg-open "$1" || open "$1") >/dev/null 2>&1 & }; }
healthy() { curl -fs "$URL/api/engine/health" >/dev/null 2>&1; }
service_on() {
  { [ "$(uname)" = "Linux" ] && systemctl --user is-enabled clipzou.service >/dev/null 2>&1; } ||
    { [ "$(uname)" = "Darwin" ] && [ -f "$HOME/Library/LaunchAgents/ai.clipzou.plist" ]; }
}

# Aberto pelo ícone/terminal com o serviço instalado: garante que está ligado e abre o app.
if [ "${STARK_SERVICE:-}" != "1" ] && service_on; then
  if ! healthy; then
    echo "Ligando o Clipzou em segundo plano…"
    command -v notify-send >/dev/null 2>&1 && notify-send -i "$ROOT/apps/web/public/icons/icon-192.png" \
      "Clipzou" "Ligando… o app abre sozinho em instantes." 2>/dev/null
    systemctl --user start clipzou.service 2>/dev/null ||
      launchctl kickstart "gui/$(id -u)/ai.clipzou" 2>/dev/null ||
      launchctl load -w "$HOME/Library/LaunchAgents/ai.clipzou.plist" 2>/dev/null
  fi
  for _ in $(seq 1 150); do healthy && break; sleep 2; done
  open_url "$URL"
  exit 0
fi

if healthy; then
  if [ "${STARK_SERVICE:-}" = "1" ]; then
    echo "outra cópia do Clipzou está ligada; tento de novo em 30 s"
    sleep 30
    exit 1
  fi
  echo "Clipzou já está rodando: $URL"
  open_url "$URL"
  exit 0
fi
command -v pnpm >/dev/null 2>&1 || { echo "pnpm não encontrado: rode antes  bash scripts/install.sh" >&2; exit 1; }

# 1) Versão nova no GitHub? Baixa (só avanço rápido, nunca apaga mudanças locais), reinstala e recarrega.
if [ "${STARK_NO_UPDATE:-}" != "1" ] && [ "${STARK_JUST_UPDATED:-}" != "1" ] && [ -d .git ]; then
  OLD=$(git rev-parse HEAD)
  if GIT_TERMINAL_PROMPT=0 git pull --ff-only -q 2>/dev/null; then
    if [ "$OLD" != "$(git rev-parse HEAD)" ]; then
      echo "▶ Versão nova baixada. Atualizando (1–3 min)…"
      STARK_NO_START=1 STARK_FROM_START=1 bash scripts/install.sh || echo "aviso: atualização falhou; ligando mesmo assim" >&2
      exec env STARK_JUST_UPDATED=1 bash "$ROOT/scripts/start.sh"
    fi
  else
    echo "aviso: sem atualizar agora (sem internet, login do GitHub ou alterações locais). Usando a versão atual."
  fi
fi
unset STARK_JUST_UPDATED
[ -f apps/web/.next/BUILD_ID ] || pnpm run build

( for _ in $(seq 1 90); do
    sleep 2
    if healthy; then
      echo "✔ Clipzou pronto: $URL"
      open_url "$URL"
      break
    fi
  done ) &

# 2) Atualizador: versão nova no GitHub (a cada 15 min) ou botão "Atualizar agora" → reinicia atualizado.
watch_updates() {
  local n=0 last="" up
  while sleep 20; do
    n=$((n + 1))
    [ -f "$DATA/update_now" ] || [ $((n % 45)) -eq 0 ] || continue
    rm -f "$DATA/update_now"
    GIT_TERMINAL_PROMPT=0 git fetch -q 2>/dev/null || continue
    up=$(git rev-parse '@{u}' 2>/dev/null) || continue
    { [ "$up" != "$(git rev-parse HEAD)" ] && [ "$up" != "$last" ]; } || continue
    last=$up
    { git merge-base --is-ancestor HEAD "$up" && [ -z "$(git status --porcelain --untracked-files=no)" ]; } || continue
    echo "▶ Versão nova no GitHub: reiniciando para atualizar…"
    touch "$DATA/.updating"
    bash scripts/stop.sh --app-only >/dev/null
    return
  done
}

pnpm start &
APP=$!
WATCH=""
if [ -d .git ] && [ "${STARK_NO_AUTOUPDATE:-}" != "1" ]; then
  watch_updates &
  WATCH=$!
fi
wait "$APP"
CODE=$?
[ -n "$WATCH" ] && kill "$WATCH" 2>/dev/null
if [ -f "$DATA/.updating" ]; then
  rm -f "$DATA/.updating"
  exec bash "$ROOT/scripts/start.sh"
fi
exit "$CODE"
