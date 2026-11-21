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
git clone https://github.com/giordanbohrer3-cpu/stark-clip-ai.git && cd stark-clip-ai && bash scripts/install.sh
```

O repositório é privado: o `git clone` pede login do GitHub uma vez.

## 2. Usar e instalar no PC

- Windows: duplo clique em `scripts\start.cmd` · outros: `pnpm start`
- Abra http://127.0.0.1:3000/install no Chrome ou Edge → **Instalar app**

## 3. Celular (Tailscale, grátis e privado)

1. Instale o Tailscale no PC e no celular, mesma conta (plano pessoal grátis).
2. Painel do Tailscale → **DNS** → ative **MagicDNS** e **HTTPS Certificates**.
3. No PC, com o app rodando: `pnpm run phone` (= `tailscale serve --bg 3000`) → mostra `https://seu-pc.<tailnet>.ts.net`.
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
