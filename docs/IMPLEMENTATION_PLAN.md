# IMPLEMENTATION PLAN — STARK CLIP AI

Legenda: ✅ feito e testado · 🟡 parcial / sem validação externa · ⬜ pendente

## Critérios de aceitação v1

| # | Critério | Status | Evidência |
|---|---|---|---|
| 1 | HUD responsiva | ✅ | `ui-smoke.mjs`: 6 rotas × desktop/iPhone sem erro nem overflow |
| 2 | Upload de vídeo autorizado | ✅ | `test_e2e_pipeline` + upload via proxy |
| 3 | Transcrição real com timestamps | ✅ | faster-whisper local (base/small) |
| 4 | Até 3 cortes coerentes | ✅ | E2E; vídeo teste → 3 temas certos, intro/CTA excluídos |
| 5 | Editor com pré-visualização | ✅ | Estúdio: ao vivo + prévia + final |
| 6 | Legendas sincronizadas | ✅ | ASS karaokê + overlay ao vivo |
| 7 | Enquadramento vertical | ✅ | face/split/center/fit (rosto real não testado: vídeo sintético sem rosto) |
| 8 | Export MP4 | ✅ | 1080×1920, H.264, AAC −14 LUFS |
| 9 | Persistência | ✅ | SQLite/Postgres |
| 10 | Fila com progresso | ✅ | lease, retry, cancel, órfãos, pausa |
| 11 | Textos de publicação | ✅ | heurística; IA opcional 🟡 |
| 12 | Agendamento interno | ✅ | cadência + aprovação + anti-duplicado |
| 13 | Publicação oficial via API | ⬜ | Fase 4 (exige apps aprovados) |
| 14 | Modo demonstrativo identificado | ✅ | API oficial aparece desabilitada com motivo |
| 15 | Testes | ✅ | 26 pytest (unit, segurança, fila, E2E real) + smoke UI |

## Fases

**Fase 1 — Fundação ✅** arquitetura, banco, auth por token/workspace, dashboard real, upload com direitos.
⬜ login multiusuário na UI · ⬜ Alembic.

**Fase 2 — Núcleo de IA ✅** transcrição, score, 3 cortes, versão longa, Modo Operador, IA opcional com orçamento.
🟡 provedores pagos implementados mas **não validados** (sem chaves nesta sessão).

**Fase 3 — Estúdio 🟡** feito: trecho, layouts, jump cuts, ruído, cor, logo, estilo, revisão de palavras, prévia/final, SRT/ASS/capa.
⬜ multipista real (b-roll, música licenciada, SFX) · ⬜ templates por marca · ⬜ YuNet/MediaPipe + tracking multi-rosto · ⬜ títulos animados com Remotion · ⬜ correção ortográfica por IA.

**Fase 4 — Publicações 🟡** feito: perfis, cadência, agenda, kit assistido, exportação, marcar publicado.
⬜ OAuth + adaptadores oficiais (ordem sugerida):
1. Instagram + Facebook (Graph API) — app Meta em modo desenvolvimento publica nas **suas** contas (admin do app) sem App Review.
2. YouTube Shorts (`videos.insert`) — projeto não auditado publica só como privado.
3. TikTok Content Posting API — sem auditoria, só privado (SELF_ONLY).
Alternativa imediata: Metricool/Postiz (já fazem OAuth oficial) — ver INTEGRATIONS.md.

**Fase 5 — Crescimento 🟡** feito: radar (YouTube API + manual), ideias, métricas manuais (observado ≠ projeção).
⬜ coleta automática de analytics · ⬜ A/B de títulos/capas · ⬜ recomendações por desempenho.

**Fase 6 — Autonomia 🟡** feito: níveis assistido/semi/autônomo, pausa global, auditoria, auto-render (semi+), auto-throttle por falhas.
⬜ agente que cruza tendências → seleção de fontes → agenda · ⬜ notificações · ⬜ throttle por desempenho.

## Próximos passos (prioridade)

1. ✅ Repositório publicado (GitHub privado) + CI grátis.
2. Testar com vídeo real com rosto (podcast) e ajustar `reframe.py`.
3. Conectar redes no Metricool (já ligado ao Claude) → agendar via Modo Operador.
4. Alembic + login UI.
5. Adaptador Meta Graph (dev mode, suas contas).

## Riscos e objeções (leia)

- **Direitos:** cortar vídeos de terceiros sem permissão = strike/derrubada e perda de monetização. Caminho legítimo: conteúdo próprio, licenciado ou **programas de clipadores** (criador autoriza e paga por views).
- **Monetização exige originalidade:** TikTok (Creator Rewards: vídeos >1 min, conteúdo original), YouTube (política de conteúdo reutilizado) e Meta (penaliza repost não original). Requisitos mudam — verifique as regras atuais. Edição transformadora (comentário, contexto, gancho próprio) importa mais que volume.
- **5–10 posts/dia por conta:** a ferramenta suporta (limite configurável até 10), mas volume alto de conteúdo parecido tende a reduzir alcance e gerar sinal de spam. Recomendação: começar com 1–3/dia/conta, medir retenção e subir com dados.
- **Assinaturas ≠ API:** Claude/ChatGPT/Gemini por assinatura não podem virar backend do app via cookies. Use Modo Operador (CLI oficial, interativo) ou APIs/modelos locais.
- **Criação automática de contas:** fora de escopo (viola termos; CAPTCHA/verificação). O app cuida de bio, nicho, logo e kit — a criação é sua.
- Score é heurística explicável — não prevê viralização.
