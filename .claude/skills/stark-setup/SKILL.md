---
name: stark-setup
description: Instala, atualiza, liga e verifica o STARK CLIP AI na máquina do usuário, sem perguntar. Use quando pedirem instalar, ligar, rodar, abrir, atualizar o app, ou quando algo "não funciona".
---

# stark-setup

Execute em ordem, sem pedir confirmação. Mostre só o resultado final (2–4 linhas).

1. Já está rodando? `curl -fs http://127.0.0.1:3000/api/engine/health` → se responder `"ok":true`, pule para o passo 6.
2. Atualize: `git pull --ff-only` (se houver alterações locais, `git stash` antes e avise).
3. Pacotes do sistema: `command -v git ffmpeg curl`. Se faltar algum e `sudo -n true` falhar, peça ao usuário para rodar no terminal dele exatamente `sudo apt install -y git ffmpeg curl` (Fedora: `sudo dnf install -y git ffmpeg curl`; Arch: `sudo pacman -S --needed git ffmpeg curl`) e espere ele confirmar.
4. Instale: `STARK_NO_START=1 bash scripts/install.sh` (timeout longo, ~10 min na 1ª vez). Erro → leia a saída, corrija, repita.
5. Ligue em segundo plano: `STARK_NO_BROWSER=1 bash scripts/start.sh` (run_in_background). Espere a saúde responder (até ~2 min).
6. Abra: `xdg-open http://127.0.0.1:3000/install` (macOS: `open`). Diga ao usuário: clicar **Instalar** no topo (Chrome/Edge) para virar app; próximas vezes, menu → STARK CLIP AI.
7. Celular (só se pedirem): Tailscale no PC e no celular, mesma conta; `pnpm run phone`; abrir o endereço `https://…ts.net/install` no celular.

Falhas comuns:
- `pnpm`/`uv` não encontrado: `export PATH="$HOME/.local/bin:$HOME/.local/share/pnpm:$PATH"` e repita.
- Porta 3000/8787 ocupada: `fuser -k 3000/tcp 8787/tcp` (ou `pkill -f "next start"; pkill -f uvicorn`) e ligue de novo.
- Transcrição com erro de CUDA: o motor já cai para CPU; se persistir, `STARK_WHISPER_DEVICE=cpu`.
