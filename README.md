# STARK CLIP AI

Central de comando para transformar **vídeos autorizados** em cortes verticais prontos: transcrição local, 3 cortes por vídeo com score explicável, legendas animadas, reframe 9:16, render, agenda e publicação assistida.

> Link do YouTube não é autorização. O app não baixa vídeos do YouTube. Envie o original (seu canal: YouTube Studio → Download) ou material licenciado/permitido pelo criador.

## 100% grátis (uso pessoal)

| Peça | Como fica grátis |
|---|---|
| Transcrição | Whisper local (sem API) |
| Cortes / textos | Heurística local · Ollama local · Gemini free tier · Modo Operador no Claude Code (sua assinatura) |
| APIs pagas | **Bloqueadas** no servidor (`STARK_FREE_ONLY=true`, padrão) |
| Banco / fila | SQLite local, sem Redis |
| Render | FFmpeg na sua máquina (GPU NVIDIA opcional) |
| Publicação | Kit assistido / exportação (você posta no app/navegador) |
| CI | GitHub Actions (cota grátis do plano Free) |

Software 100% open source (FastAPI, Next.js, FFmpeg, faster-whisper, OpenCV). Fontes OFL.

## Instalar (PC + celular como app)

Guia completo: [docs/INSTALL.md](docs/INSTALL.md) — instalador de 1 comando (Windows/macOS/Linux), PWA no PC e no celular via Tailscale (grátis). Com o app rodando, abra `/install`.

## Rodar (Windows, macOS, Linux)

Pré-requisitos: Python 3.11+ com [uv](https://docs.astral.sh/uv/), Node 20.9+ com pnpm, FFmpeg no PATH.

```bash
pnpm install
```

```bash
pnpm run setup
```

```bash
pnpm dev
```

Abra http://127.0.0.1:3000. O token do motor é gerado em `services/engine/data/.api_token` e lido pelo proxy do Next (nunca vai ao navegador).

### Docker (com PostgreSQL)

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

## Fluxo

1. **Vídeos** → upload + declaração de direitos → análise automática.
2. **Detalhe** → 3 candidatos com score, justificativa e prévia → versão longa (>60 s) opcional.
3. **Estúdio** → trecho, layout (rosto/split/centro/encaixar), remover pausas, ruído, logo, estilo e revisão das legendas → prévia 540p / final 1080×1920 → MP4, SRT, ASS, capa, textos por rede.
4. **Publicar** → perfis, agenda em lote por cadência, aprovação, kit assistido ou exportação.
5. **Config** → autonomia, pausa global, orçamento de IA, provedores, marca, cadência, auditoria.

## Usar suas assinaturas (Modo Operador)

No Claude Code, dentro deste repo: `/stark-cuts` (ou “planeje os cortes do vídeo 3”). O Claude lê o pedido do motor, escolhe os cortes e importa o JSON validado. Mesmo fluxo funciona com Gemini CLI/Codex logados. No modo grátis (padrão) APIs pagas nem podem ser ativadas.

## Testes

```bash
pnpm test
```

```bash
pnpm run check
```

```bash
pnpm run test:ui
```

## Estrutura

```
services/engine/   motor FastAPI + worker (Python)
apps/web/          HUD Next.js 16 + proxy /api/engine
.claude/skills/    10 skills do Modo Operador
docs/              ARCHITECTURE · IMPLEMENTATION_PLAN · INTEGRATIONS
```

Leia `docs/IMPLEMENTATION_PLAN.md` → “Riscos e objeções” antes de escalar volume: originalidade e direitos decidem a monetização.
