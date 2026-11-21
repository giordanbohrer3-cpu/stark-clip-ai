---
name: stark-cuts
description: Seleciona os 3 melhores cortes de um vídeo do STARK CLIP AI usando a assinatura do Claude Code (Modo Operador). Use quando o usuário pedir cortes/planejar cortes de um vídeo já transcrito.
---

# stark-cuts

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`
2. Baixe o pedido: `curl -s -H "$AUTH" "$API/videos/<ID>/analysis-request?mode=short"` (ou `mode=long` p/ >60s).
3. Leia as frases indexadas. Escolha até 3 trechos NÃO sobrepostos e NÃO redundantes: gancho nos 3s iniciais, contexto suficiente, conclusão. Prefira os candidatos da heurística se forem bons; nunca force 3.
4. Responda só JSON `{"cuts":[{"start_idx":i,"end_idx":j,"title":"…","summary":"…","justification":"…","hook_score":0-100}]}` — títulos sem clickbait enganoso.
5. Importe: `curl -s -H "$AUTH" -H 'content-type: application/json' -X POST "$API/videos/<ID>/cuts/import" -d @cuts.json`.
6. Reporte score final e justificativa. Score é estimativa explicável, não promessa de viralização.
