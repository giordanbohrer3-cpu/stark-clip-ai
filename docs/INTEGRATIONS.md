# INTEGRATIONS — STARK CLIP AI

Legenda: ✅ validado nesta sessão · 🟡 implementado, não validado (falta credencial) · 🔵 disponível na sessão Claude (não é runtime do app) · ⬜ planejado · ⛔ não permitido / fora de escopo

Verificado em 2026-11-21. Regras de plataformas mudam: confira a documentação oficial antes de depender delas.

## Modo 100% grátis (padrão)

`STARK_FREE_ONLY=true`: o servidor recusa ativar ou rotear Anthropic/OpenAI (HTTP 403) e registra custo 0.
Permitidos: heurística, Ollama (local) e Gemini **free tier** — crie a chave no Google AI Studio em projeto
**sem faturamento** (assim não há cobrança; no free tier o Google pode usar os dados para melhorar produtos).

## Runtime do app

| Integração | Status | Notas |
|---|---|---|
| FFmpeg 6.1 (libass, x264) | ✅ | render, cenas, loudnorm; NVENC auto-detectado (sem GPU aqui). x264 é GPL: atenção ao redistribuir binários |
| faster-whisper (MIT) | ✅ | modelos `base`/`small` baixados do Hugging Face no 1º uso (cache local) |
| OpenCV 4.14 headless | ✅ | Haar embutido; **não use OpenCV 5** (removeu CascadeClassifier) |
| YouTube oEmbed | ✅ | metadados por URL, sem chave |
| YouTube Data API v3 | 🟡 | busca/“em alta”; requer `STARK_YOUTUBE_API_KEY` (cota diária grátis) |
| Gemini API | 🟡 | free tier via AI Studio (dados podem ser usados p/ melhorar produtos no free tier) |
| Anthropic API | 🟡 | default `claude-haiku-5-5`; pago, desligado por padrão |
| OpenAI API | 🟡 | default `gpt-5-mini` (confirme nome/preço atual); pago, desligado |
| Ollama (local) | 🟡 | grátis; ex.: `qwen2.5:7b`; requer Ollama instalado |
| Preços de IA | 🟡 | tabela editável em Config (estimativa; confira preço oficial) |
| PostgreSQL 16 | 🟡 | via docker compose (Docker indisponível nesta sessão) |

## Publicação

| Destino | Status | Requisito oficial |
|---|---|---|
| Modo assistido (kit + link de upload) | ✅ | você publica no navegador logado; sem captura de senha/cookie |
| Exportar pasta (vídeo, legenda, capa, meta.json) | ✅ | serve p/ qualquer agendador |
| Instagram (Graph API, Reels) | ⬜ | conta Business/Creator; app Meta; em modo dev funciona nas contas com papel no app; limite diário via `content_publishing_limit` |
| Facebook Pages (Reels) | ⬜ | `pages_manage_posts`; mesma lógica de app Meta |
| TikTok Content Posting API | ⬜ | sem auditoria do app, posts só privados; Direct Post público exige audit |
| YouTube Shorts (`videos.insert`) | ⬜ | projeto não verificado → vídeos privados até auditoria |
| Extensões de navegador que postam sozinhas | ⛔ | automação não oficial = risco de banimento; preferir agendadores oficiais |
| Criação automática de contas / CAPTCHA | ⛔ | viola termos das plataformas |
| Download de vídeos do YouTube (yt-dlp etc.) | ⛔ | viola Termos do YouTube; use YouTube Studio para seus vídeos |

## MCPs / skills na sua sessão Claude (Modo Operador)

Funcionam quando **você** usa o Claude Code; o app não os chama sozinho.

| Ferramenta | Status | Uso no fluxo |
|---|---|---|
| Metricool MCP | ✅ conectado · ⚠️ nenhuma rede ligada | conecte TikTok/IG/FB em app.metricool.com → Claude agenda (`createScheduledPost`), melhor horário, analytics |
| vidIQ MCP | ✅ plano free: 150 créditos/mês (renova 21/12/2026) | sons em alta TikTok, outliers, keywords, títulos; publicar Reels/social (gasta créditos) |
| Descript MCP | 🔵 não validado | `create_social_clips`, transcrição (usa créditos do plano) |
| Adobe for creativity MCP | 🔵 não validado | quick cut, resize de vídeo |
| Canva MCP | 🔵 não validado | logo, foto de perfil, capas |
| ElevenLabs MCP | 🔵 não validado | narração/TTS, transcrição (créditos) |
| Skill `postiz:postiz` | 🔵 não carregada | Postiz = agendador open-source (AGPL-3.0, self-host) com OAuth oficial |
| Skills `remotion:*` | 🔵 | animações/títulos (Fase 3). Licença Remotion: grátis p/ indivíduos e times pequenos; empresas maiores pagam |
| GitHub MCP | ⚠️ falhou ao conectar | push via `gh` CLI funciona no container |
| Skills do projeto `.claude/skills/stark-*` | ✅ criadas | 10 skills: cortes, análise, transcrição, legendas, render, tendências, publicação, direitos, custos, diagnóstico |

## Assinaturas: o que é permitido

| Assinatura | Pode | Não pode |
|---|---|---|
| Claude Pro/Max | Claude Code (este) + skill `stark-cuts` lendo o pedido e importando JSON | virar API do app via cookies/token web |
| ChatGPT Plus/Pro | Codex CLI logado na conta, mesmo fluxo do pedido/JSON | idem |
| Google AI Pro | Gemini CLI logado; Gemini API free tier (chave AI Studio) | idem |

Automatizar o CLI em lote (headless) com assinatura é zona cinzenta nos termos — **não implementado** de propósito. Decisão sua após ler os termos de cada provedor.

## Fontes de tendência

YouTube Data API (oficial) · registro manual com fonte/data/confiança (TikTok Creative Center, Google Trends) · vidIQ MCP (operador). Sem scraping. Áudios populares: apenas pela biblioteca da plataforma no momento de postar.
