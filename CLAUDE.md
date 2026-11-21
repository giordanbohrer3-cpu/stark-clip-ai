# STARK CLIP AI — instruções para o Claude Code

App pessoal de cortes verticais. Motor Python (`services/engine`, FastAPI + worker, FFmpeg, faster-whisper) + painel Next.js 16 (`apps/web`, PWA). Roda 100% local e grátis. Dono: uso pessoal, fala PT-BR, prefere respostas curtas.

## Regra principal: faça, não pergunte

- Pedido de instalar, ligar, rodar, abrir, atualizar ou “não funciona”: **execute a skill `/stark-setup` direto**, sem pedir confirmação nem listar opções.
- Mensagem vaga ou só “oi” logo ao abrir: rode o diagnóstico rápido (abaixo) e diga em 2 linhas o estado e o próximo passo que você já vai fazer.
- Erro: leia a saída, corrija e tente de novo. Só pare para pedir algo que só o usuário pode fazer (senha do sudo, login do GitHub/Tailscale).

## Comandos

| Ação | Comando |
|---|---|
| Atualizar código | `git pull --ff-only` |
| Instalar (idempotente) | `STARK_NO_START=1 bash scripts/install.sh` |
| Ligar (atualiza sozinho; deixe em segundo plano) | `STARK_NO_BROWSER=1 bash scripts/start.sh` |
| Atualizar e reiniciar | `bash scripts/update.sh` (em segundo plano) |
| Parar | `bash scripts/stop.sh` |
| Saúde | `curl -s http://127.0.0.1:3000/api/engine/health` |
| Abrir painel | `xdg-open http://127.0.0.1:3000` (macOS: `open`) |
| Instalar como app | abrir `http://127.0.0.1:3000/install` no Chrome/Edge |
| Celular | `pnpm run phone` (Tailscale) |
| Testes | `cd services/engine && uv run pytest -q` · `cd apps/web && pnpm exec tsc --noEmit && pnpm lint` |

Diagnóstico rápido: `git status -sb`, `command -v pnpm uv node ffmpeg`, curl na saúde.

## Limites

- `sudo` não funciona sem terminal: se faltar pacote do sistema, mostre ao usuário a linha exata (`sudo apt install -y git ffmpeg curl`) para ele rodar no terminal dele, e continue depois.
- Servidores longos (`start.sh`, `pnpm start`) sempre em segundo plano; nunca bloqueie a sessão.
- Modo grátis (`STARK_FREE_ONLY=true`): não ative APIs pagas.
- Direitos: só processar vídeo com autorização registrada; não baixar vídeos do YouTube.
- Docs: `docs/ARCHITECTURE.md`, `docs/INSTALL.md`, `docs/INTEGRATIONS.md`.
