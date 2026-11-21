#!/usr/bin/env bash
# STARK CLIP AI - instalador macOS/Linux (uso pessoal, 100% grátis). Pode rodar de novo sem problema.
# Uso: bash scripts/install.sh        (STARK_NO_START=1 = só instala, não liga)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
export PATH="$HOME/.local/bin:$PNPM_HOME:$HOME/Library/pnpm:$PATH"
have() { command -v "$1" >/dev/null 2>&1; }
say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

say "1/5 Sistema: git, ffmpeg, curl"
MISSING=""
for p in git ffmpeg ffprobe curl; do have "$p" || MISSING="$MISSING $p"; done
MISSING="${MISSING/ffprobe/}"
if [ -z "${MISSING// /}" ]; then
  echo "ok: git, ffmpeg, curl já instalados"
elif have brew; then
  brew install $MISSING
else
  if [ -n "$SUDO" ] && ! sudo -n true 2>/dev/null && [ ! -t 0 ]; then
    echo "Faltam:$MISSING. Rode no seu terminal e depois repita este instalador:" >&2
    if have apt-get; then echo "  sudo apt install -y git ffmpeg curl" >&2
    elif have dnf; then echo "  sudo dnf install -y git ffmpeg curl" >&2
    else echo "  sudo pacman -S --needed git ffmpeg curl" >&2; fi
    exit 2
  fi
  if have apt-get; then
    $SUDO apt-get update -q
    $SUDO apt-get install -y -q git ffmpeg curl ca-certificates
  elif have dnf; then
    $SUDO dnf install -y git curl ffmpeg || $SUDO dnf install -y git curl ffmpeg-free
  elif have pacman; then
    $SUDO pacman -Sy --needed --noconfirm git ffmpeg curl
  else
    echo "Não reconheci o gerenciador de pacotes. Instale git, ffmpeg e curl e rode de novo." >&2
    exit 1
  fi
fi

say "2/5 uv (gerencia o Python sozinho)"
have uv || curl -LsSf https://astral.sh/uv/install.sh | sh

say "3/5 pnpm + Node LTS"
have pnpm || curl -fsSL https://get.pnpm.io/install.sh | env PNPM_HOME="$PNPM_HOME" SHELL="${SHELL:-/bin/bash}" sh -
if ! have node || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
  pnpm env use --global lts
fi

ENV_FILE="$ROOT/services/engine/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'ENVEOF'
# Chaves GRÁTIS do radar Clipzou. Preencha, salve e reinicie (menu → Clipzou → Atualizar e reiniciar).
# Twitch: dev.twitch.tv → Aplicativos → Registrar (redirecionamento http://localhost:3000/api/engine/live/twitch/callback, Confidencial)
STARK_TWITCH_CLIENT_ID=
STARK_TWITCH_CLIENT_SECRET=
# YouTube: console.cloud.google.com → ativar "YouTube Data API v3" → Credenciais → Chave de API
STARK_YOUTUBE_API_KEY=
ENVEOF
  chmod 600 "$ENV_FILE"
fi

say "4/5 Instalando e compilando o Clipzou"
pnpm install
pnpm run setup
pnpm run build

if [ "$(uname)" = "Linux" ]; then
  say "5/5 Atalho no menu de aplicativos"
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/stark-clip-ai.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Clipzou
Comment=Máquina de clipes: radar ao vivo e cortes prontos
Exec=bash "$ROOT/scripts/start.sh"
Icon=$ROOT/apps/web/public/icons/icon-512.png
StartupWMClass=Clipzou
Terminal=true
Categories=AudioVideo;Video;
Actions=update;stop;

[Desktop Action update]
Name=Atualizar e reiniciar
Exec=bash "$ROOT/scripts/update.sh"

[Desktop Action stop]
Name=Parar Clipzou
Exec=bash "$ROOT/scripts/stop.sh"
EOF
fi

printf '\n\033[1;32m✔ Instalado.\033[0m Próximas vezes: abra "Clipzou" no menu ou rode: bash scripts/start.sh\n'
[ "${STARK_NO_START:-}" = "1" ] && exit 0
exec bash "$ROOT/scripts/start.sh"
