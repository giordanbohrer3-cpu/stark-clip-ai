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

## 3. Celular sem Tailscale: app online (grátis, igual seus outros apps)

O app fica na **Vercel** (link fixo, atualiza sozinho a cada versão nova). O PC manda o radar e os cortes prontos para o
**Supabase**, numa área separada (`clipzou`) no projeto *giordanbohrer3-cpu's Project*, que já está criada. O PC continua
fazendo os cortes.

1. **Chave:** supabase.com → *giordanbohrer3-cpu's Project* → Project Settings → API Keys → **Secret keys** → criar
   (nome `clipzou`) → copiar. Não mande a chave em chat.
2. **PC:** Clipzou → **Config → Nuvem** → colar a chave → Salvar. Aparece "sincronizando".
3. **Vercel:** vercel.com/new → Import Git Repository → `stark-clip-ai` → **Root Directory: `apps/web`** →
   Environment Variables: `SUPABASE_SECRET_KEY` = a mesma chave · `CLIPZOU_PASSWORD` = uma senha sua → **Deploy**.
4. Copie o link `https://….vercel.app`. No PC: **Config → Nuvem → Link do app** → Salvar. A página `/install` mostra o QR.
5. **Celular:** escaneie o QR, entre com a senha e toque em **Instalar app** (iPhone: Safari → Compartilhar → Tela de Início).

O que funciona online: radar, feed (assistir e baixar), legenda, "Buscar agora", "Cortar agora", campanhas, listas do
radar e "Atualizar o PC". Edição fina, publicação e chaves ficam no PC. Com o PC desligado, o app mostra o último radar e
os cortes já enviados.

Limites grátis: o projeto do Supabase é dividido com seus outros apps, então o Clipzou se limita sozinho.
- Até 500 MB de cortes na nuvem. Os mais velhos saem da nuvem e continuam no PC.
- Até 2 GB de download por mês (a variável `CLIPZOU_EGRESS_CAP_MB` na Vercel muda esse limite).
- Corte acima de 48 MB fica só no PC.

### Opcional: Tailscale (sem nuvem)

1. Instale o Tailscale no PC e no celular, na mesma conta. Linux: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`.
2. Painel do Tailscale → **DNS** → ative **MagicDNS** e **HTTPS Certificates**.
3. No PC: `pnpm run phone` (no Linux, é o mesmo que `sudo tailscale serve --bg 3000`). No celular, abra `https://seu-pc.<tailnet>.ts.net/install`.

## Problemas comuns

| Sintoma | Solução |
|---|---|
| Não aparece “Instalar” | precisa HTTPS (app online na Vercel) ou `localhost`; recarregue a página uma vez |
| “PC desligado” no app online | ligue o PC: o Clipzou liga sozinho e volta a mandar o radar e os cortes |
| App online pede login sempre | defina `CLIPZOU_PASSWORD` na Vercel e faça Redeploy |
| “Motor offline” no PC | abra pelo ícone Clipzou (ele liga o serviço); se persistir: `bash scripts/service.sh status` |
| iPhone não instala | use o Safari (outros navegadores no iOS não instalam) |
| Mesma rede Wi-Fi sem Tailscale | abre via `http://IP-do-PC:3000`, mas sem HTTPS não instala como app |

Segurança: o app online exige senha (cookie assinado), a chave secreta fica só no servidor da Vercel e no PC
(criptografada), e os cortes ficam numa pasta privada com links temporários de 1 hora.
