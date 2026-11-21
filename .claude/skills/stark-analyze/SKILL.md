---
name: stark-analyze
description: Classifica vídeos-fonte por nicho, potencial e prontidão (direitos, áudio, duração). Use ao organizar a biblioteca ou priorizar o que processar.
---

# stark-analyze

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`; liste: `curl -s -H "$AUTH" "$API/videos"`.
2. Para cada vídeo: tem arquivo? `rights_ok`? áudio? duração (>3 min rende 3 cortes melhores)?
3. Sugira nicho e prioridade (alta/média/baixa) com motivo. Atualize nicho: `PATCH $API/videos/<ID>` `{"niche":"…"}`.
4. Enfileire os prioritários: `POST $API/videos/<ID>/process` (bloqueia sem autorização — não contorne).
