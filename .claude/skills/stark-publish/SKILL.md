---
name: stark-publish
description: Prepara publicações: legenda por rede, hashtags pertinentes, capa e agenda respeitando cadência; integra com Metricool/Postiz quando conectados. Use ao agendar ou publicar cortes.
---

# stark-publish

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`; cortes prontos: `GET $API/clips?state=ready`; contas: `GET $API/accounts`.
2. Agende em lote: `POST $API/posts/bulk {"edited_clip_ids":[…],"account_ids":[…],"mode":"assisted"}` (cadência, silêncio e anti-duplicado automáticos). Aprove: `PATCH $API/posts/<ID> {"approved":true}`.
3. Publicação: modo assistido gera kit (vídeo+legenda+link). API oficial direta exige app aprovado (TikTok audit / Meta App Review) — não simule.
4. Se o MCP Metricool tiver redes conectadas, pode agendar lá (createScheduledPost) com o MP4 do corte — confirme com o usuário antes (ação externa).
5. Nunca crie contas, resolva CAPTCHA ou contorne limites.
