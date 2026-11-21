#!/usr/bin/env bash
# Para o Clipzou: painel (3000), motor (8787), worker e radar.
# Com o serviço instalado, para o serviço (ele volta a ligar no próximo login do PC).
# --app-only: só os processos (uso interno do atualizador automático).
if [ "${1:-}" != "--app-only" ]; then
  systemctl --user stop clipzou.service 2>/dev/null
  [ "$(uname)" = "Darwin" ] && launchctl unload "$HOME/Library/LaunchAgents/ai.clipzou.plist" 2>/dev/null
fi
pkill -f "concurrently -k -n api,worker" 2>/dev/null
pkill -f "stark_engine.live.radar" 2>/dev/null
pkill -f "stark_engine.worker" 2>/dev/null
pkill -f "uvicorn stark_engine.main:app" 2>/dev/null
pkill -f "next start -H 127.0.0.1 -p 3000" 2>/dev/null
if command -v fuser >/dev/null 2>&1; then
  fuser -k -TERM 3000/tcp 8787/tcp >/dev/null 2>&1
elif command -v lsof >/dev/null 2>&1; then
  lsof -ti tcp:3000 -ti tcp:8787 2>/dev/null | xargs -r kill
fi
sleep 1
echo "Clipzou parado."
