#!/usr/bin/env bash
# Para o STARK: painel (3000), motor (8787) e worker.
pkill -f "concurrently -k -n api,worker,web" 2>/dev/null
pkill -f "stark_engine.worker" 2>/dev/null
pkill -f "uvicorn stark_engine.main:app" 2>/dev/null
pkill -f "next start -H 127.0.0.1 -p 3000" 2>/dev/null
if command -v fuser >/dev/null 2>&1; then
  fuser -k -TERM 3000/tcp 8787/tcp >/dev/null 2>&1
elif command -v lsof >/dev/null 2>&1; then
  lsof -ti tcp:3000 -ti tcp:8787 2>/dev/null | xargs -r kill
fi
sleep 1
echo "STARK parado."
