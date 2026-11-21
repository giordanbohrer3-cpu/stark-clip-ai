#!/usr/bin/env bash
# Atualiza do GitHub e reinicia o STARK (o start.sh baixa a versão nova e recompila).
cd "$(dirname "$0")/.." || exit 1
bash scripts/stop.sh
exec bash scripts/start.sh
