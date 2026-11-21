#!/usr/bin/env bash
# Atualiza do GitHub e reinicia o Clipzou (normalmente nem precisa: ele se atualiza sozinho a cada 15 min).
cd "$(dirname "$0")/.." || exit 1
if systemctl --user is-enabled clipzou.service >/dev/null 2>&1; then
  systemctl --user restart clipzou.service  # o serviço baixa a versão nova ao ligar
  exec bash scripts/start.sh                # espera ficar pronto e abre o app
fi
if [ "$(uname)" = "Darwin" ] && [ -f "$HOME/Library/LaunchAgents/ai.clipzou.plist" ]; then
  launchctl kickstart -k "gui/$(id -u)/ai.clipzou" 2>/dev/null
  exec bash scripts/start.sh
fi
bash scripts/stop.sh
exec bash scripts/start.sh
