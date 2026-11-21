# ARCHITECTURE — STARK CLIP AI

Local-first. Um operador (você) roda tudo na própria máquina; escala para multi-workspace sem trocar contratos.

```
Navegador (HUD Next.js 16)
   │  /api/engine/*  (sem token no browser)
   ▼
Next.js route handler (proxy) ── injeta Bearer, repassa Range/stream
   │  http://127.0.0.1:8787/api/v1/*
   ▼
FastAPI (motor) ──► SQLite WAL / PostgreSQL (SQLModel)
   ▲                     ▲
   │ jobs (tabela Job)   │
Worker(s) python -m stark_engine.worker
   ├─ FFmpeg (probe, áudio, cenas, render, loudnorm, NVENC opcional)
   ├─ faster-whisper (transcrição local, timestamps por palavra)
   ├─ OpenCV Haar (rosto → reframe 9:16 / split)
   └─ IA opcional: Ollama local | Gemini | Claude | OpenAI (APIs oficiais, orçamento)
data/ (media, clips, exports, branding, cache)
```

## Módulos (`services/engine/stark_engine/`)

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Settings `STARK_*`; gera `data/.api_token` e `.secret_key` (chmod 600) se ausentes |
| `models.py` | Entidades (abaixo). Datetimes UTC aware |
| `security.py` | Auth Bearer→User→Workspace, papéis, Fernet p/ tokens OAuth, `safe_path`, defaults do workspace |
| `media.py` | ffprobe, extração 16 kHz, energia RMS, cenas (filtro `scene`), frames, encoder, `run_ffmpeg` com progresso/cancelamento |
| `transcribe.py` | faster-whisper (VAD, palavras) — áudio passado como numpy (evita PyAV) |
| `clipper.py` | Motor heurístico: frases → janelas → 8 features → score 0-100 → seleção sem sobreposição/redundância |
| `ai/providers.py` | Adaptadores HTTP oficiais, orçamento rígido pré-chamada, retry 429/5xx, `AIUsage` |
| `ai/planner.py` | Planejamento por IA via índices de frase + pedido do Modo Operador |
| `captions.py` | Jump cuts (remap de tempo), blocos, SRT, ASS karaokê (palavra ativa destacada) |
| `reframe.py` | Amostragem de rostos, layouts face/center/split/fit, câmera com zona morta, `sendcmd` por frame |
| `render.py` | Filtergraph único: trim/concat → crop/split/fit → cor → legendas → logo → loudnorm −14 LUFS |
| `jobqueue.py` | Fila no banco: claim otimista, lease, backoff, cancelamento, recuperação de órfãos, pausa |
| `pipeline.py` | Handlers `analyze` / `render` (revalidam direitos — defesa em profundidade) |
| `publishing.py` | Cadência (limite diário, intervalo, silêncio, fuso), anti-duplicado, auto-throttle, adaptadores |
| `copywriter.py` | Título, legenda por rede, hashtags (heurística; IA opcional) |
| `youtube.py` | oEmbed (sem chave) + Data API v3; hosts fixos (anti-SSRF); **não baixa vídeo** |
| `routers/*` | API v1 tipada (OpenAPI em `/docs`) |

## Dados (entidades mínimas)

`User, Workspace, SocialAccount, SourceVideo, RightsGrant, Transcript, ClipCandidate, EditedClip, Job, ScheduledPost, Trend, AnalyticsSnapshot, AIUsage, AuditLog`
- `RenderJob` = `Job(kind="render")`, `PublishingJob` = `Job(kind="publish")` (fila única = um worker loop simples).
- Escopo: toda query filtra `workspace_id` (`Ctx.get_owned`).

## Pipeline

1. Upload (extensão, tamanho, ffprobe, duração, hash) **+ RightsGrant obrigatório** → miniatura.
2. `analyze`: áudio → transcrição (cache por hash+modelo) → energia → cenas → `ClipAnalyzer` → (IA opcional) → até N cortes (`min_score`; nunca artificiais).
3. Estúdio: trecho, layout, pausas, ruído, logo, estilo, revisão de palavras → `render` (prévia 540p ou final 1080×1920) → MP4/SRT/ASS/capa → textos.
4. Agenda: slots por cadência → aprovação → `publish` (assistido/exportar; API oficial = Fase 4).

### Score (explicável)
`hook .24 · closure .14 · energy .14 · density .08 · emotion .10 · cohesion .12 · dur_fit .12 · scenes .06`, × (1 − 0.5·silêncio) − 15·CTA. Faixa de duração adaptativa ao vídeo (`duration_bounds`); modo longo 61–180 s. Breakdown salvo e exibido na UI.

## Decisões e desvios do stack sugerido

| Sugerido | Adotado | Motivo |
|---|---|---|
| Redis/BullMQ | Fila no banco (`jobqueue.py`) | Motor é Python; zero infra extra; persistente; N workers seguros. Trocar por Arq/Redis se >1 máquina |
| PySceneDetect | Filtro `scene` do FFmpeg | Mesma função, sem dependência |
| MediaPipe | OpenCV Haar (<5.0) | Sem download de modelos; OpenCV 5 removeu `CascadeClassifier`. YuNet/MediaPipe = melhoria Fase 3 |
| PostgreSQL | SQLite WAL (local) / Postgres (compose) | Zero config para 1 operador; mesmo ORM |
| Alembic | `create_all` | **Pendente**: adicionar migrações antes de dados de produção |
| shadcn/ui, GSAP | Primitivos próprios + Motion + Three | Menos dependências; tokens compatíveis com shadcn |
| Sessões async | SQLModel sync em `def` (threadpool) | Workload CPU-bound; sem bloquear event loop |

## Segurança

Token só no servidor (proxy); portas em `127.0.0.1`; papéis owner/editor/viewer; Fernet p/ tokens OAuth; uploads validados (ext, tamanho, ffprobe, duração); `safe_path` anti-traversal; anti-SSRF (YouTube por hosts fixos, IA por URLs fixas); FFmpeg via lista de args (sem shell); direitos revalidados no worker; logs sem credenciais; auditoria de ações; APIs pagas desligadas + `confirm_paid` + limite rígido.

**Limites atuais:** login multiusuário na UI pendente (API já é multiusuário por token); sem rate limit HTTP próprio; retenção/backup de `data/` manual.
