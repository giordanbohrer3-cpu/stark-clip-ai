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
if have brew; then
  for p in git ffmpeg; do have "$p" || brew install "$p"; done
elif have apt-get; then
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

say "2/5 uv (gerencia o Python sozinho)"
have uv || curl -LsSf https://astral.sh/uv/install.sh | sh

say "3/5 pnpm + Node LTS"
have pnpm || curl -fsSL https://get.pnpm.io/install.sh | env PNPM_HOME="$PNPM_HOME" SHELL="${SHELL:-/bin/bash}" sh -
if ! have node || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
  pnpm env use --global lts
fi

say "4/5 Instalando e compilando o STARK"
pnpm install
pnpm run setup
pnpm run build

if [ "$(uname)" = "Linux" ]; then
  say "5/5 Atalho no menu de aplicativos"
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/stark-clip-ai.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=STARK CLIP AI
Comment=Liga o motor de cortes e abre o painel
Exec=bash "$ROOT/scripts/start.sh"
Icon=$ROOT/apps/web/public/icons/icon-512.png
Terminal=true
Categories=AudioVideo;Video;
EOF
fi

printf '\n\033[1;32m✔ Instalado.\033[0m Próximas vezes: abra "STARK CLIP AI" no menu ou rode: bash scripts/start.sh\n'
[ "${STARK_NO_START:-}" = "1" ] && exit 0
exec bash "$ROOT/scripts/start.sh"
