"use client";
import { CheckCircle2, ClipboardCopy, Download, MonitorSmartphone, Share, Smartphone, XCircle } from "lucide-react";
import qrcode from "qrcode-generator";
import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Field, Input, Note, Panel } from "@/components/ui";
import { usePoll } from "@/lib/api";
import { runInstall, useInstallPrompt, useJustInstalled, useOrigin, usePlatform, useStandalone } from "@/lib/pwa";
import type { Health } from "@/lib/types";

const TABS = [
  { id: "android", label: "Android" },
  { id: "ios", label: "iPhone" },
  { id: "desktop", label: "PC (Windows/Mac)" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const STEPS: Record<Tab, string[]> = {
  android: [
    "Abra o endereço HTTPS do Tailscale no Chrome do celular (ex.: https://meu-pc.tailnet.ts.net/install).",
    "Toque em “Instalar app” nesta página (ou menu ⋮ → Instalar aplicativo).",
    "O ícone STARK aparece na tela inicial e abre em tela cheia.",
  ],
  ios: [
    "Abra o endereço HTTPS do Tailscale no Safari (precisa ser o Safari).",
    "Toque em Compartilhar (quadrado com seta ↑).",
    "Escolha “Adicionar à Tela de Início” → Adicionar.",
  ],
  desktop: [
    "No PC, com o app rodando (pnpm start), abra http://127.0.0.1:3000/install no Chrome ou Edge.",
    "Clique em “Instalar app” aqui ou no ícone de instalar na barra de endereço.",
    "O STARK abre em janela própria e ganha atalho no menu Iniciar/Dock.",
  ],
};

const TS_CMD = "tailscale serve --bg 3000";
const HTTPS_URL = /^https:\/\/[a-z0-9.-]+(:\d+)?(\/.*)?$/i;

function qrSvg(text: string): string {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  return qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
}

function Check({ ok, label, hint }: { ok: boolean | null; label: string; hint?: string }) {
  return (
    <li className="flex items-start justify-between gap-3 py-1.5">
      <span>
        <span className="text-sm">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
      {ok === null ? <span className="text-xs text-muted">…</span> : ok
        ? <CheckCircle2 className="size-5 shrink-0 text-ok" aria-label="ok" />
        : <XCircle className="size-5 shrink-0 text-bad" aria-label="falta" />}
    </li>
  );
}

export default function InstallPage() {
  const evt = useInstallPrompt();
  const standalone = useStandalone();
  const justInstalled = useJustInstalled();
  const platform = usePlatform();
  const { origin, secure, local } = useOrigin();
  const health = usePoll<Health>("/health", 10000);
  const [tab, setTab] = useState<Tab | null>(null);
  const [phoneUrl, setPhoneUrl] = useState("");
  const [sw, setSw] = useState<boolean | null>(null);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.getRegistration("/").then((r) => setSw(!!r)).catch(() => setSw(false));
  }, []);

  const shown: Tab = tab ?? (platform === "ios" ? "ios" : platform === "android" ? "android" : "desktop");
  const target = local ? (HTTPS_URL.test(phoneUrl.trim()) ? phoneUrl.trim().replace(/\/$/, "") + "/install" : "") : `${origin}/install`;
  const svg = useMemo(() => (target ? qrSvg(target) : ""), [target]);
  const done = standalone || justInstalled;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-center gap-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/icon-192.png" alt="" className="size-16 rounded-2xl shadow-[0_0_30px_-8px_var(--cyan)]" />
        <div>
          <p className="hud-label">PWA · celular e PC · grátis</p>
          <h1 className="glow-text text-2xl font-semibold">Instalar STARK CLIP AI</h1>
        </div>
        {done && <Badge className="border-ok/40 text-ok">instalado</Badge>}
      </header>

      <Panel eyebrow="este dispositivo" title="Instalação" id="now">
        {done ? (
          <Note tone="ok">Pronto: o STARK está instalado neste dispositivo. Abra pelo ícone da tela inicial/menu.</Note>
        ) : evt ? (
          <Button variant="primary" className="h-12 w-full text-base sm:w-auto" onClick={() => runInstall(evt)} icon={<Download className="size-5" />}>
            Instalar app agora
          </Button>
        ) : !secure ? (
          <Note tone="warn">
            Endereço sem HTTPS: o navegador bloqueia a instalação. No celular, use o endereço HTTPS do Tailscale (passo a passo abaixo).
          </Note>
        ) : platform === "ios" ? (
          <Note tone="info"><Share className="mr-1 inline size-4" aria-hidden />No Safari: Compartilhar → “Adicionar à Tela de Início”.</Note>
        ) : (
          <Note tone="info">
            Use Chrome ou Edge: clique no ícone de instalar na barra de endereço ou menu ⋮ → “Instalar STARK CLIP AI”.
            Se não aparecer, recarregue a página uma vez.
          </Note>
        )}
        <div className="mt-4 flex gap-1 rounded-[10px] border border-line p-1" role="tablist" aria-label="plataforma">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={shown === t.id} onClick={() => setTab(t.id)}
              className={`flex-1 rounded-lg py-2 text-xs sm:text-sm ${shown === t.id ? "bg-cyan/15 text-cyan" : "text-muted"}`}>
              {t.label}
            </button>
          ))}
        </div>
        <ol className="mt-4 space-y-2">
          {STEPS[shown].map((s, i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className="grid size-6 shrink-0 place-items-center rounded-full border border-cyan/40 font-mono text-xs text-cyan">{i + 1}</span>
              <span className="text-muted">{s}</span>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel eyebrow="celular" title="Abrir no telefone" id="qr">
          {local && (
            <Field label="Endereço HTTPS do Tailscale" hint="aparece ao rodar o comando abaixo no PC">
              <Input value={phoneUrl} onChange={(e) => setPhoneUrl(e.target.value)} placeholder="https://meu-pc.tailnet.ts.net" inputMode="url" />
            </Field>
          )}
          {svg ? (
            <div className="mt-4 flex flex-col items-center gap-2">
              <div className="w-48 rounded-xl bg-white p-2 [&_svg]:h-auto [&_svg]:w-full" role="img" aria-label={`QR code para ${target}`}
                dangerouslySetInnerHTML={{ __html: svg }} />
              <p className="break-all text-center font-mono text-xs text-muted">{target}</p>
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted">Cole o endereço HTTPS para gerar o QR code e escanear com a câmera do celular.</p>
          )}
        </Panel>

        <Panel eyebrow="acesso grátis e privado" title="Tailscale no PC e no celular" id="ts">
          <ol className="space-y-2 text-sm text-muted">
            <li>1. Instale o Tailscale no PC e no celular e entre na mesma conta (plano pessoal grátis).</li>
            <li>2. No painel do Tailscale → DNS: ative MagicDNS e HTTPS Certificates.</li>
            <li>3. No PC, com o STARK rodando:</li>
          </ol>
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-line bg-black/40 px-3 py-2">
            <code className="flex-1 font-mono text-sm text-cyan">{TS_CMD}</code>
            <Button size="sm" variant="subtle" aria-label="copiar comando" onClick={() => navigator.clipboard.writeText(TS_CMD)}
              icon={<ClipboardCopy className="size-4" />} />
          </div>
          <p className="mt-2 text-xs text-muted">Só aparelhos da sua conta Tailscale acessam. Nada fica público na internet. O PC precisa estar ligado.</p>
        </Panel>
      </div>

      <Panel eyebrow="diagnóstico" title="Requisitos" id="checks">
        <ul className="divide-y divide-line">
          <Check ok={secure} label="Conexão segura (HTTPS ou localhost)" hint={origin} />
          <Check ok={sw} label="Service worker ativo" hint="registrado no modo produção (pnpm start)" />
          <Check ok={health.data ? health.data.ok : health.error ? false : null} label="Motor do PC online" hint="FFmpeg, banco e Whisper" />
          <Check ok={done} label="Instalado neste dispositivo" />
        </ul>
        <p className="mt-3 flex items-center gap-2 text-xs text-muted">
          <MonitorSmartphone className="size-4" aria-hidden /> O processamento roda no seu PC; o app instalado é a tela de controle.
          <Smartphone className="size-4" aria-hidden />
        </p>
      </Panel>
    </div>
  );
}
