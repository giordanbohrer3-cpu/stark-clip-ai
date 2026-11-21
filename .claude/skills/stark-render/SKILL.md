---
name: stark-render
description: Renderiza e diagnostica cortes (FFmpeg, reframe 9:16, jump cuts, loudnorm, NVENC). Use quando render falhar, ficar lento ou o enquadramento sair errado.
---

# stark-render

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`; jobs do corte: `curl -s -H "$AUTH" "$API/clips/<CLIP>/jobs"`.
2. Args exatos do FFmpeg ficam em `services/engine/data/clips/<CLIP>/ffmpeg_args.json` (rode manualmente p/ reproduzir).
3. Enquadramento: layout auto/face/split/center/fit (`PATCH /clips/<CLIP>`). Rosto não detectado → `center` ou `fit`.
4. Prévia rápida: `POST /clips/<CLIP>/render {"preview":true}`. GPU: `STARK_HWACCEL=nvenc`.
5. Cancelar/repetir: `POST /jobs/<JOB>/cancel|retry`.
