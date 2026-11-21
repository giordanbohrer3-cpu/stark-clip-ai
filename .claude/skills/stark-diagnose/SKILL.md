---
name: stark-diagnose
description: Roda testes e diagnostica o STARK CLIP AI (motor, fila, web). Use quando algo falhar ou antes de commitar.
---

# stark-diagnose

1. Saúde: `curl -s http://127.0.0.1:8787/api/v1/health`.
2. Testes motor (inclui E2E real ffmpeg+whisper): `cd services/engine && uv run pytest -q`.
3. Web: `cd apps/web && pnpm exec tsc --noEmit && pnpm lint && pnpm build`; UI: `node apps/web/scripts/ui-smoke.mjs`.
4. Fila travada: `GET $API/jobs?state=running` (lease expira e volta p/ fila sozinho); pausa global: `POST $API/agent/resume`.
5. Logs sem segredos; nunca imprima `.api_token`/chaves.
