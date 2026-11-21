---
name: stark-transcript
description: Revisa transcrição do Whisper (nomes, gírias, termos técnicos, pontuação) de um corte no estúdio. Use antes de publicar ou quando legendas tiverem erros.
---

# stark-transcript

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`; contexto: `curl -s -H "$AUTH" "$API/clips/<CLIP>/context"` → `words` = [início, fim, texto, prob].
2. Corrija só o TEXTO de cada palavra (nunca tempos). Atenção a prob < 0.6 e a palavras que mudam sentido (ex.: palavrão por erro de reconhecimento).
3. Envie: `PATCH $API/clips/<CLIP>` `{"words_override": [[s,e,"texto"],…]}` e depois re-renderize.
