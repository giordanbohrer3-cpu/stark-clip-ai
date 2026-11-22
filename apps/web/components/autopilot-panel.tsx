"use client";
/* Piloto automático: o app escolhe os cortes em alta, legenda, põe as # e agenda sozinho (Metricool). */
import { ExternalLink, Rocket } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Note, Panel, Toggle } from "@/components/ui";
import { api, usePoll } from "@/lib/api";
import { ago } from "@/lib/format";

type Item = { key: string; clip_id: number; network: string; title: string; caption: string; score: number };
type Status = {
  at?: string; error?: string; enabled?: boolean; items?: Item[]; used_this_month?: number; monthly_limit?: number;
  posted_recent?: { clip_id: number; network: string; scheduled_for?: string }[];
  settings: { enabled: boolean; networks: string[]; monthly_limit: number };
  metricool_url: string;
};

const NET: Record<string, string> = { tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook" };

export function AutopilotPanel() {
  const st = usePoll<Status>("/system/autopilot", 15000);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const s = st.data;
  const cfg = s?.settings;

  const save = async (key: string, patch: Record<string, unknown>, ok: string) => {
    setBusy(key);
    setMsg(null);
    try {
      await api("/settings", { method: "PATCH", json: { data: { autopilot: patch } } });
      setMsg({ tone: "ok", text: ok });
      st.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };
  const toggleNet = (n: string) => {
    const nets = new Set(cfg?.networks ?? []);
    if (nets.has(n)) nets.delete(n);
    else nets.add(n);
    void save(`n-${n}`, { networks: [...nets] }, "Redes atualizadas.");
  };

  return (
    <Panel eyebrow="automático" title="Piloto automático" id="autopilot" actions={
      cfg && <Toggle checked={cfg.enabled} onChange={(v) => save("on", { enabled: v }, v ? "Piloto ligado." : "Piloto desligado.")}
        label={cfg.enabled ? "ligado" : "desligado"} />
    }>
      {msg && <div className="mb-3"><Note tone={msg.tone}>{msg.text}</Note></div>}
      <p className="text-sm text-muted">
        Escolhe os cortes mais em alta, escreve a legenda com as # e agenda no melhor horário: um post por dia, em rodízio
        entre as redes. Plano grátis do Metricool: até {cfg?.monthly_limit ?? 18} por mês.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {Object.entries(NET).map(([n, label]) => (
          <button key={n} type="button" onClick={() => toggleNet(n)} disabled={busy === `n-${n}`} aria-pressed={cfg?.networks.includes(n)}
            className={`h-8 rounded-full border px-3 text-xs ${cfg?.networks.includes(n) ? "border-violet/60 bg-violet/15 text-ink" : "border-line text-muted"}`}>
            {label}
          </button>
        ))}
        <Badge className="border-cyan/40 text-cyan">este mês: {s?.used_this_month ?? 0} de {s?.monthly_limit ?? cfg?.monthly_limit ?? 18}</Badge>
        {s?.at && <span className="text-xs text-muted">atualizado {ago(s.at)}</span>}
      </div>
      {s?.error && <div className="mt-3"><Note tone="bad">{s.error}</Note></div>}
      <div className="mt-4">
        <p className="hud-label mb-2">próximos posts</p>
        {!s?.items?.length ? (
          <p className="text-sm text-muted">Nenhum corte pronto com autorização comercial ainda. Jogue vídeos na pasta de entrada.</p>
        ) : (
          <ul className="space-y-2">
            {s.items.map((i) => (
              <li key={i.key} className="rounded-lg border border-line p-2.5">
                <p className="flex items-center justify-between gap-2 text-sm font-semibold">
                  <span className="truncate">{i.title}</span>
                  <Badge className="shrink-0 border-violet/50 text-violet">{NET[i.network] ?? i.network}</Badge>
                </p>
                <p className="mt-1 line-clamp-2 text-xs text-muted">{i.caption}</p>
                <p className="mt-1 font-mono text-[0.65rem] text-cyan">nota {i.score}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <a href={s?.metricool_url ?? "https://app.metricool.com"} target="_blank" rel="noreferrer" className="mt-4 inline-flex">
        <Button variant="primary" icon={<Rocket className="size-4" />}>Conectar TikTok, Instagram e Facebook <ExternalLink className="size-3.5" /></Button>
      </a>
      <p className="mt-2 text-xs text-muted">Só uma vez: entre nas suas contas dentro do Metricool. Depois disso posta sozinho.</p>
    </Panel>
  );
}
