---
name: stark-captions
description: Define estilo de legenda e motion (fonte, cor de destaque, posição segura, palavras por linha) por nicho/marca. Use ao criar template visual ou ajustar legibilidade.
---

# stark-captions

1. Padrões: Config → Marca (`PATCH /settings {"data":{"captions":{...}}}`); por corte: `PATCH /clips/<id> {"caption_style":{...}}`.
2. Regras: posição 0.60–0.72 (fora da UI das redes), 2–3 palavras/linha, contraste alto (contorno 6–8px), CAIXA ALTA opcional.
3. Tela dividida (2 pessoas) centraliza legenda automaticamente.
4. Animações extras (títulos, zoom, transições) → Fase 3 com Remotion: ver skill remotion:remotion-captions se instalada.
