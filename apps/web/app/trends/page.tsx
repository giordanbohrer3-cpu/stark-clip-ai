"use client";
import { ExternalLink, Lightbulb, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Empty, Field, Input, Note, Panel, Select } from "@/components/ui";
import { api, usePoll } from "@/lib/api";
import { ago, num } from "@/lib/format";
import type { SettingsResp, Trend } from "@/lib/types";

type Idea = { angle: string; hook: string; audience: string; format: string; duration_s: number; title: string; cta: string; hashtags: string[]; originality: string; source: string };

const SOURCES = [
  ["TikTok Creative Center", "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/pt"],
  ["Google Trends (BR)", "https://trends.google.com/trending?geo=BR"],
  ["YouTube Em alta", "https://www.youtube.com/feed/trending"],
];

export default function Trends() {
  const trends = usePoll<Trend[]>("/trends", 0);
  const cfg = usePoll<SettingsResp>("/settings", 0);
  const [form, setForm] = useState({ kind: "hashtag", label: "", url: "", confidence: 0.5, license_note: "" });
  const [niche, setNiche] = useState("");
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const run = async (k: string, fn: () => Promise<unknown>) => {
    setBusy(k);
    setMsg(null);
    try {
      await fn();
      trends.reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Radar de tendências</h1>
      {msg && <Note tone="bad">{msg}</Note>}
      <Note tone="info">
        Só fontes oficiais/autorizadas: YouTube Data API (automático) e registro manual com fonte e data. Sem scraping.
        Áudios em alta: use apenas pela biblioteca da própria plataforma no momento de postar (licença).
      </Note>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <Panel eyebrow="sinais" title="Tendências salvas" id="tr" actions={
          <Button size="sm" onClick={() => run("yt", () => api("/trends/youtube?region=BR", { method: "POST" }))} loading={busy === "yt"}
            disabled={!cfg.data?.env.youtube_api} icon={<RefreshCw className="size-3.5" />}>YouTube BR em alta</Button>
        }>
          {!cfg.data?.env.youtube_api && <p className="mb-3 text-xs text-warn">Defina STARK_YOUTUBE_API_KEY para importar automaticamente.</p>}
          {!trends.data?.length ? <Empty title="Sem sinais ainda">Importe do YouTube ou registre o que viu nas fontes oficiais.</Empty> : (
            <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
              {trends.data.map((t) => (
                <li key={t.id} className="flex items-start gap-3 rounded-lg border border-line p-3">
                  <input type="checkbox" aria-label="usar nas ideias" checked={sel.includes(t.label)} className="mt-1"
                    onChange={(e) => setSel((s) => e.target.checked ? [...s, t.label] : s.filter((x) => x !== t.label))} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{t.label}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      <Badge>{t.kind}</Badge><Badge>{t.source}</Badge><span>{t.region}</span><span>· {ago(t.fetched_at)}</span>
                      <span>· confiança {Math.round(t.confidence * 100)}%</span>
                      {typeof t.metric.views === "number" && <span>· {num(t.metric.views)} views</span>}
                    </div>
                    {t.license_note && <p className="mt-1 text-xs text-warn">{t.license_note}</p>}
                  </div>
                  {t.url && <a href={t.url} target="_blank" rel="noreferrer" aria-label="abrir fonte" className="text-muted hover:text-cyan"><ExternalLink className="size-4" /></a>}
                  <button aria-label="remover" className="text-muted hover:text-bad" onClick={() => run(`d${t.id}`, () => api(`/trends/${t.id}`, { method: "DELETE" }))}><Trash2 className="size-4" /></button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel eyebrow="registro manual" title="Adicionar sinal" id="add">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Tipo"><Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {["hashtag", "audio", "topic", "format", "video"].map((k) => <option key={k}>{k}</option>)}</Select></Field>
              <Field label={`Confiança ${Math.round(form.confidence * 100)}%`}>
                <input type="range" min={0} max={1} step={0.05} value={form.confidence} className="w-full" onChange={(e) => setForm({ ...form, confidence: +e.target.value })} /></Field>
              <Field label="Rótulo" className="sm:col-span-2"><Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="#educacaofinanceira" /></Field>
              <Field label="Link da fonte" className="sm:col-span-2"><Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://…" /></Field>
              <Field label="Nota de licença" className="sm:col-span-2"><Input value={form.license_note} onChange={(e) => setForm({ ...form, license_note: e.target.value })} placeholder="ex.: áudio só via biblioteca do TikTok" /></Field>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-2 text-xs">
                {SOURCES.map(([l, u]) => <a key={u} href={u} target="_blank" rel="noreferrer" className="text-cyan underline-offset-2 hover:underline">{l}</a>)}
              </div>
              <Button onClick={() => run("add", () => api("/trends", { method: "POST", json: { ...form, url: form.url || null, source: "manual" } }).then(() => setForm({ ...form, label: "", url: "" })))}
                disabled={!form.label} loading={busy === "add"} icon={<Plus className="size-4" />}>Salvar</Button>
            </div>
          </Panel>

          <Panel eyebrow="estratégia" title="Gerar ideias" id="ideas">
            <div className="flex gap-2">
              <Input value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="nicho do perfil" aria-label="nicho" />
              <Button variant="primary" loading={busy === "ideas"} icon={<Lightbulb className="size-4" />}
                onClick={() => run("ideas", async () => setIdeas(await api<Idea[]>("/trends/ideas", { method: "POST", json: { niche, topics: sel } })))}>Gerar</Button>
            </div>
            <p className="mt-1 text-xs text-muted">{sel.length ? `${sel.length} sinal(is) selecionado(s)` : "usa os sinais mais recentes"} · IA só se habilitada em Config.</p>
            {ideas && (
              <ul className="mt-4 space-y-3">
                {ideas.map((i, k) => (
                  <li key={k} className="rounded-lg border border-line p-3 text-sm">
                    <p className="font-medium">{i.title}</p>
                    <p className="mt-1 text-muted"><b className="text-ink">Gancho:</b> {i.hook}</p>
                    <p className="text-muted"><b className="text-ink">Ângulo:</b> {i.angle}</p>
                    <p className="text-xs text-muted">{i.audience} · {i.format} · ~{i.duration_s}s · {i.cta}</p>
                    <p className="mt-1 text-xs text-cyan">{(i.hashtags ?? []).join(" ")}</p>
                    <p className="text-xs text-warn">originalidade: {i.originality} · {i.source}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
