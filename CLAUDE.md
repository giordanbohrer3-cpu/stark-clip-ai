# Clipzou — instruções para o Claude Code

Clipzou (ex-STARK CLIP AI): máquina de clipes pessoal. Radar ao vivo (Twitch/YouTube, picos de chat) + cortes prontos.
Funciona sem chave: famosos da Twitch pelo chat público, YouTubers famosos pelo feed RSS público, pasta de entrada
(`~/Clipzou/Entrada`) que vira cortes sozinha. Roda em segundo plano (serviço): liga com o PC e se atualiza sozinho. Motor Python (`services/engine`, FastAPI + worker, FFmpeg, faster-whisper) + painel Next.js 16 (`apps/web`, PWA). Roda 100% local e grátis. Dono: uso pessoal, fala PT-BR, prefere respostas curtas.

## Regra principal: faça, não pergunte

- Pedido de instalar, ligar, rodar, abrir, atualizar ou “não funciona”: **execute a skill `/stark-setup` direto**, sem pedir confirmação nem listar opções.
- Mensagem vaga ou só “oi” logo ao abrir: rode o diagnóstico rápido (abaixo) e diga em 2 linhas o estado e o próximo passo que você já vai fazer.
- Erro: leia a saída, corrija e tente de novo. Só pare para pedir algo que só o usuário pode fazer (senha do sudo, login do GitHub/Tailscale).

## Comandos

| Ação | Comando |
|---|---|
| Atualizar código | `git pull --ff-only` |
| Instalar (idempotente) | `STARK_NO_START=1 bash scripts/install.sh` |
| Ligar / abrir (usa o serviço) | `STARK_NO_BROWSER=1 bash scripts/start.sh` |
| Serviço (liga com o PC, atualiza a cada 15 min) | `bash scripts/service.sh install --now` · `status` · `uninstall` |
| Atualizar e reiniciar agora | `bash scripts/update.sh` (ou botão Config → Atualizar agora) |
| Parar | `bash scripts/stop.sh` |
| Saúde | `curl -s http://127.0.0.1:3000/api/engine/health` |
| Abrir painel | `xdg-open http://127.0.0.1:3000` (macOS: `open`) |
| Instalar como app | abrir `http://127.0.0.1:3000/install` no Chrome/Edge |
| Celular (app online) | Config → Nuvem (chave secreta do Supabase) + Vercel (Root `apps/web`; variáveis `SUPABASE_SECRET_KEY`, `CLIPZOU_PASSWORD`) — `docs/INSTALL.md` §3 |
| Celular (alternativa) | `pnpm run phone` (Tailscale) |
| Testes | `cd services/engine && uv run pytest -q` · `cd apps/web && pnpm exec tsc --noEmit && pnpm lint` |

Diagnóstico rápido: `git status -sb`, `command -v pnpm uv node ffmpeg`, curl na saúde.

## Chaves do radar (opcionais, grátis)

Sem chaves o radar já funciona (chat público + RSS). Chaves liberam espectadores, top geral e corte automático de live. Pedido "configura as chaves/radar": abra `services/engine/.env` para o usuário (`xdg-open services/engine/.env`),
explique em 3 linhas onde criar (Twitch: dev.twitch.tv → Aplicativos → Registrar, redirect `http://localhost:3000/api/engine/live/twitch/callback`,
Confidencial; YouTube: Google Cloud → YouTube Data API v3 → chave). NÃO peça as chaves no chat. Quando ele salvar: `bash scripts/update.sh`
em segundo plano e confira `curl -s http://127.0.0.1:3000/api/engine/live/status`. Depois: Radar → Conectar Twitch.

## Limites

- `sudo` não funciona sem terminal: se faltar pacote do sistema, mostre ao usuário a linha exata (`sudo apt install -y git ffmpeg curl`) para ele rodar no terminal dele, e continue depois.
- Servidores longos (`start.sh`, `pnpm start`) sempre em segundo plano; nunca bloqueie a sessão.
- Modo grátis (`STARK_FREE_ONLY=true`): não ative APIs pagas.
- Direitos: só processar vídeo com autorização registrada; não baixar vídeos do YouTube.
- Nuvem: Supabase do usuário, projeto `pyxbnpplflraaztljgos`, área `clipzou` (só a chave secreta acessa). Nunca mexa em
  outras tabelas desse projeto (são de outros apps dele). A chave secreta o usuário cola em Config → Nuvem e na Vercel;
  NÃO peça no chat.
- Piloto automático: o PC (`stark_engine/autopilot.py`, roda no processo `cloud`) escolhe os cortes em alta, monta
  legenda + # e manda a fila para `clipzou.snapshot` ('autopilot_queue'), com vídeos na pasta secreta do PC (chave
  pública + segredo em `data/.autopilot_secret`). Uma tarefa agendada (2x/dia) agenda 1 post/dia no Metricool (marca
  blogId 8262686, plano grátis = 20 posts/mês) e registra em 'autopilot_posted'. Ligar/desligar: Config → Piloto automático.
- Docs: `docs/ARCHITECTURE.md`, `docs/INSTALL.md`, `docs/INTEGRATIONS.md`.
