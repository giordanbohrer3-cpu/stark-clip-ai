"use client";
/* Nuvem: no PC, colar a chave do Supabase e o link do app online; online, config enxuta (o resto só no PC). */
import { Cloud, LogOut, RefreshCw, Save, Unplug } from "lucide-react";
import { useState } from "react";
import { Button, Field, Input, Note, Panel, Textarea } from "@/components/ui";
import { api, usePoll } from "@/lib/api";
import { ago } from "@/lib/format";
import type { CloudStatus, SettingsResp } from "@/lib/types";

type Msg = { tone: "ok" | "bad" | "warn"; text: string } | null;

export function CloudPanel() {
  const st = usePoll<CloudStatus>("/cloud/status", 10000);
  const [key, setKey] = useState("");
  const [app, setApp] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState("");
  const s = st.data;
  const appUrl = app ?? s?.app_url ?? "";

  const run = async (k: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(k);
    setMsg(null);
    try {
      await fn();
      setMsg({ tone: "ok", text: ok });
      setKey("");
      st.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const state = !s?.configured ? "desligada"
    : s.error ? `erro: ${s.error}`
    : s.running ? `sincronizando${s.last_sync_at ? ` · último envio ${ago(s.last_sync_at)}` : ""}` : "ligando…";

  return (
    <Panel eyebrow="celular sem Tailscale" title="Nuvem (app online)" id="cloud">
      {msg && <div className="mb-3"><Note tone={msg.tone}>{msg.text}</Note></div>}
      <p className="mb-3 flex items-center gap-2 text-sm">
        <Cloud className={`size-4 ${s?.configured && !s.error ? "text-ok" : "text-muted"}`} />
        <span className={s?.error ? "text-bad" : ""}>{state}</span>
      </p>
      {s?.configured && (
        <p className="mb-3 text-xs text-muted">
          {s.uploaded_mb ?? 0} MB de cortes na nuvem (limite {s.storage_limit_mb ?? 500} MB, apaga os mais velhos) ·
          download do mês {s.egress_mb ?? 0} MB. A cota grátis do Supabase é dividida com seus outros apps.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Chave secreta do Supabase" hint="Supabase → giordanbohrer3-cpu's Project → Project Settings → API Keys → Secret keys → copiar. Fica criptografada só neste PC.">
          <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
            placeholder={s?.configured ? "•••••• salva (cole outra para trocar)" : "sb_secret_…"} />
        </Field>
        <Field label="Link do app online (Vercel)" hint="Aparece no QR de instalar no celular.">
          <Input value={appUrl} onChange={(e) => setApp(e.target.value)} placeholder="https://clipzou-xxxx.vercel.app" inputMode="url" />
        </Field>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" loading={busy === "save"} disabled={!key && app === null} icon={<Save className="size-4" />}
          onClick={() => run("save", () => api("/cloud/config", { method: "POST", json: { key: key || undefined, app_url: app ?? undefined } }),
            "Salvo. O PC começa a mandar o radar e os cortes para o app online.")}>Salvar</Button>
        {s?.configured && (
          <Button variant="subtle" loading={busy === "off"} icon={<Unplug className="size-4" />}
            onClick={() => confirm("Desligar a nuvem neste PC? O app online para de receber cortes novos.") &&
              run("off", () => api("/cloud/config", { method: "DELETE" }), "Nuvem desligada neste PC.")}>Desconectar</Button>
        )}
      </div>
    </Panel>
  );
}

export function CloudSettings() {
  const cfg = usePoll<SettingsResp>("/settings", 0);
  const ver = usePoll<{ commit: string | null; date: string | null }>("/system/version", 0);
  const cs = usePoll<CloudStatus>("/cloud/status", 30000);
  const [watch, setWatch] = useState<string | null>(null);
  const [yt, setYt] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState("");
  const radar = cfg.data?.settings?.radar;

  const run = async (k: string, fn: () => Promise<{ message?: string; detail?: string } | unknown>, ok: string) => {
    setBusy(k);
    setMsg(null);
    try {
      const r = (await fn()) as { message?: string; detail?: string; queued?: boolean } | undefined;
      setMsg({ tone: r?.queued ? "warn" : "ok", text: r?.message ?? (r?.queued ? r.detail ?? ok : ok) });
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Configurações</h1>
          <p className="text-xs text-muted">
            app online · versão do PC {ver.data?.commit ?? "—"}{ver.data?.date ? ` · ${ago(ver.data.date)}` : ""} ·
            PC {cs.data?.pc_online ? "ligado" : `desligado${cs.data?.pc_seen_at ? ` (visto ${ago(cs.data.pc_seen_at)})` : ""}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button loading={busy === "upd"} icon={<RefreshCw className="size-4" />}
            onClick={() => run("upd", () => api("/system/update", { method: "POST" }), "Pedido enviado ao PC.")}>Atualizar o PC</Button>
          <Button variant="subtle" icon={<LogOut className="size-4" />}
            onClick={() => fetch("/api/login", { method: "DELETE" }).then(() => window.location.replace("/login"))}>Sair</Button>
        </div>
      </div>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      <Note tone="info">
        Este é o app online: o app em si se atualiza sozinho. Configuração completa (chaves, legendas, publicação) fica no PC.
        Download do mês: {cs.data?.egress_mb ?? 0} MB de {cs.data?.egress_cap_mb ?? 2048} MB (limite que protege seus outros apps no Supabase).
      </Note>
      <Panel eyebrow="radar" title="Quem o radar vigia" id="lists">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Streamers famosos (Twitch)" hint="um por linha">
            <Textarea rows={8} value={watch ?? (radar?.watch_twitch ?? []).join("\n")} onChange={(e) => setWatch(e.target.value)} />
          </Field>
          <Field label="YouTubers famosos (ID do canal UC…)" hint="um por linha">
            <Textarea rows={8} value={yt ?? (radar?.youtube_channels ?? []).join("\n")} onChange={(e) => setYt(e.target.value)} />
          </Field>
        </div>
        <Button className="mt-3" variant="primary" loading={busy === "lists"} disabled={watch === null && yt === null} icon={<Save className="size-4" />}
          onClick={() => run("lists", () => api("/settings", { method: "PATCH", json: { data: { radar: {
            ...(watch !== null ? { watch_twitch: watch.split("\n") } : {}),
            ...(yt !== null ? { youtube_channels: yt.split("\n") } : {}),
          } } } }), "Salvo no PC. O radar aplica em até 1 min.")}>Salvar listas</Button>
      </Panel>
    </div>
  );
}
