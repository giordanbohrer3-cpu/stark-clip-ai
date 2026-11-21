# Instalação (PC + celular) — 100% grátis

O STARK roda no **seu PC** (motor de vídeo). O app instalado (PWA) é a tela de controle no PC e no celular.

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

- Windows: duplo clique em `scripts\start.cmd` · Linux: menu → **STARK CLIP AI** (ou `bash scripts/start.sh`) · macOS: `bash scripts/start.sh`
- Abra http://127.0.0.1:3000/install no Chrome ou Edge → **Instalar app**

**Atualização automática:** toda vez que o STARK liga, ele baixa a versão nova do GitHub e recompila. Os apps do PC e do celular mostram a versão nova ao abrir. Com ele já ligado: menu → STARK CLIP AI → **Atualizar e reiniciar** (ou `bash scripts/update.sh`).

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
