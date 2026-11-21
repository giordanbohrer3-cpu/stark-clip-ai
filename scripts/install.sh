#!/usr/bin/env bash
# STARK CLIP AI - instalador macOS/Linux (uso pessoal, 100% grátis). Uso: bash scripts/install.sh
# macOS: Homebrew. Linux (Debian/Ubuntu): apt + instaladores oficiais do uv e do pnpm.
set -euo pipefail
cd "$(dirname "$0")/.."
have() { command -v "$1" >/dev/null 2>&1; }

if have brew; then
  for p in git uv node pnpm ffmpeg; do have "$p" || brew install "$p"; done
elif have apt-get; then
  sudo apt-get update -q
  sudo apt-get install -y -q git ffmpeg curl
  export PATH="$HOME/.local/bin:$HOME/.local/share/pnpm:$PATH"
  have uv || curl -LsSf https://astral.sh/uv/install.sh | sh          # instalador oficial do uv
  have pnpm || curl -fsSL https://get.pnpm.io/install.sh | sh -        # instalador oficial do pnpm
  export PATH="$HOME/.local/bin:$HOME/.local/share/pnpm:$PATH"
  if ! have node || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
    pnpm env use --global lts                                          # Node LTS gerenciado pelo pnpm
  fi
else
  echo "Instale manualmente: git, uv, Node 20+, pnpm e ffmpeg; depois rode este script de novo." >&2
  exit 1
fi

pnpm install
pnpm run setup
pnpm run build
echo
echo "Pronto! Rode 'pnpm start' e abra http://127.0.0.1:3000/install para instalar o app."
