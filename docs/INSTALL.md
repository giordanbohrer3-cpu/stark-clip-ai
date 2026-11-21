# Instalação do Clipzou (PC + celular) — 100% grátis

## 0. Funciona sem chave

- **Radar:** vigia streamers famosos da Twitch pelo chat público e lê os vídeos dos YouTubers famosos pelo feed público.
  Mude as listas em **Config → Radar**.
- **Pasta de entrada:** `~/Clipzou/Entrada`. No **Feed**, ative a pasta (declaração única de que os vídeos são seus ou
  autorizados) e jogue vídeos nela: os cortes 9:16 legendados aparecem no Feed sozinhos.
- **Segundo plano:** o Clipzou liga com o PC, reinicia se cair e se atualiza sozinho do GitHub (a cada 15 min ou em
  **Config → Atualizar agora**). Sem terminal.

Chaves grátis **opcionais** (`services/engine/.env`, depois Config → Atualizar agora):

- **Twitch:** dev.twitch.tv → Console → Aplicativos → Registrar. Redirecionamento: `http://localhost:3000/api/engine/live/twitch/callback`,
  tipo **Confidencial** → `STARK_TWITCH_CLIENT_ID` e `STARK_TWITCH_CLIENT_SECRET`. Libera espectadores, top geral e
  **Conectar Twitch** (corte automático dos canais que te deram editor).
- **YouTube:** console.cloud.google.com → ativar **YouTube Data API v3** → Credenciais → Chave de API → `STARK_YOUTUBE_API_KEY`.

## 1. PC (uma vez)

**Windows** (PowerShell):

```powershell
winget install --id Git.Git -e
git clone https://github.com/giordanbohrer3-cpu/stark-clip-ai.git
cd stark-clip-ai
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Tailscale
```

**macOS / Linux**:

```bash
cd ~ && { [ -d stark-clip-ai/.git ] || { [ -e stark-clip-ai ] && mv stark-clip-ai stark-clip-ai.antigo; git clone https://github.com/giordanbohrer3-cpu/stark-clip-ai.git; }; } && cd stark-clip-ai && git pull --ff-only && bash scripts/install.sh
```

O repositório é privado: o `git clone` pede login do GitHub uma vez.

## 2. Usar e instalar no PC

- Linux/macOS: o instalador registra o serviço (liga com o PC). Abra pelo ícone **Clipzou** no menu.
- Windows: duplo clique em `scripts\start.cmd`.
- Abra http://127.0.0.1:3000/install no Chrome ou Edge → **Instalar app**

**Atualização automática:** o serviço confere o GitHub a cada 15 min, baixa a versão nova, recompila e reinicia sozinho.
Os apps do PC e do celular mostram a versão nova ao abrir. Para forçar: **Config → Atualizar agora**.

## 3. Celular (Tailscale, grátis e privado)

1. Instale o Tailscale no PC e no celular, mesma conta (plano pessoal grátis). Linux: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up` (abre o login; use a mesma conta do celular).
2. Painel do Tailscale → **DNS** → ative **MagicDNS** e **HTTPS Certificates**.
3. No PC, com o app rodando: `pnpm run phone` (= `sudo tailscale serve --bg 3000` no Linux; se aparecer link para ativar HTTPS, abra e confirme) → mostra `https://seu-pc.<tailnet>.ts.net`.
4. No celular abra `https://seu-pc.<tailnet>.ts.net/install`:
   - Android (Chrome): **Instalar app**
   - iPhone (Safari): Compartilhar → **Adicionar à Tela de Início**

A página `/install` do PC mostra um QR code com esse endereço.

## Problemas comuns

| Sintoma | Solução |
|---|---|
| Não aparece “Instalar” | precisa HTTPS (Tailscale) ou `localhost`; recarregue a página uma vez |
| “Motor offline” | rode `pnpm start` no PC; o PC precisa estar ligado |
| iPhone não instala | use o Safari (outros navegadores no iOS não instalam) |
| Mesma rede Wi-Fi sem Tailscale | abre via `http://IP-do-PC:3000`, mas sem HTTPS não instala como app |

Nada fica público: o Tailscale só libera aparelhos da sua conta.
