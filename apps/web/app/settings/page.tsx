"use client";
import { ImageUp, Save } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Field, Input, Note, Panel, Select, Toggle } from "@/components/ui";
import { api, ApiError, usePoll } from "@/lib/api";
import { ago, usd } from "@/lib/format";
import type { Settings, SettingsResp } from "@/lib/types";

const AUTONOMY = [
  ["assisted", "Assistido", "Você aprova cada etapa: análise, render e publicação."],
  ["semi", "Semiautomático", "Analisa e renderiza sozinho; publicação só com sua aprovação."],
  ["autonomous", "Autônomo autorizado", "Agenda aprovado nas contas autorizadas, dentro de limites e pausa global."],
] as const;

type Usage = { id: number; provider: string; model: string; task: string; input_tokens: number; output_tokens: number; cost_usd: number; ok: boolean; error: string | null; created_at: string };
type Audit = { id: number; actor: string; action: string; target: string; created_at: string };

export default function SettingsPage() {
  const cfg = usePoll<SettingsResp>("/settings", 0);
  const usage = usePoll<Usage[]>("/ai/usage?limit=20", 0);
  const audit = usePoll<Audit[]>("/audit?limit=30", 10000);
  const [draft, setS] = useState<Settings | null>(null);
  const s = draft ?? cfg.data?.settings ?? null;
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!s) return;
    const data: Partial<Settings> = { ...s };
    delete data.paused;
    setBusy(true);
    setMsg(null);
    try {
      await api("/settings", { method: "PATCH", json: { data } });
      setMsg({ tone: "ok", text: "Configurações salvas." });
      cfg.reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 428 && confirm(`${e.message}\n\nConfirmar ativação de API paga? Cobranças seguem o limite de orçamento.`)) {
        await api("/settings?confirm_paid=true", { method: "PATCH", json: { data } });
        setMsg({ tone: "warn", text: "API paga ativada com limite rígido de orçamento." });
        cfg.reload();
      } else setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const logo = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api<{ logo_path: string }>("/branding/logo", { method: "POST", body: fd });
      if (s) setS({ ...s, branding: { ...s.branding, logo_path: r.logo_path } });
      setMsg({ tone: "ok", text: "Logo enviada." });
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    }
  };

  if (!s || !cfg.data) return <p className="text-muted">carregando…</p>;
  const set = <K extends keyof Settings>(k: K, v: Partial<Settings[K]>) => setS({ ...s, [k]: { ...(s[k] as object), ...v } });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Configurações</h1>
        <Button variant="primary" onClick={save} loading={busy} icon={<Save className="size-4" />}>Salvar</Button>
      </div>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel eyebrow="agente" title="Nível de autonomia" id="auto">
          <div className="space-y-2" role="radiogroup" aria-label="autonomia">
            {AUTONOMY.map(([v, l, d]) => (
              <label key={v} className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${s.autonomy === v ? "border-cyan/60 bg-cyan/5" : "border-line"}`}>
                <input type="radio" name="autonomy" checked={s.autonomy === v} onChange={() => setS({ ...s, autonomy: v })} className="mt-1" />
                <span><span className="text-sm font-medium">{l}</span><span className="block text-xs text-muted">{d}</span></span>
              </label>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">Sempre manuais: criação de contas, segurança, permissões e novas cobranças.</p>
        </Panel>

        <Panel eyebrow="cortes" title="Motor de cortes" id="clips">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Cortes por vídeo"><Input type="number" min={1} max={5} value={s.clips.target} onChange={(e) => set("clips", { target: +e.target.value })} /></Field>
            <Field label="Duração"><Select value={s.clips.mode} onChange={(e) => set("clips", { mode: e.target.value as "short" | "long" })}>
              <option value="short">curto adaptativo</option><option value="long">longo &gt;60s</option></Select></Field>
            <Field label="Score mínimo" hint="abaixo disso não cria corte"><Input type="number" min={0} max={90} value={s.clips.min_score} onChange={(e) => set("clips", { min_score: +e.target.value })} /></Field>
          </div>
        </Panel>

        <Panel eyebrow="orquestrador de IA" title="Provedores e orçamento" id="ai">
          {cfg.data.env.free_only && (
            <div className="mb-4"><Note tone="ok">
              Modo 100% grátis: heurística local, Ollama, Gemini free tier (chave de projeto sem faturamento) e Modo
              Operador no Claude Code. APIs pagas bloqueadas no servidor (STARK_FREE_ONLY).
            </Note></div>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Orçamento mensal (US$)" hint="0 = nenhuma cobrança"><Input type="number" min={0} step={0.5} value={s.ai.monthly_budget_usd} onChange={(e) => set("ai", { monthly_budget_usd: +e.target.value })} /></Field>
            <Field label="Alerta em (%)"><Input type="number" min={10} max={100} value={s.ai.alert_pct} onChange={(e) => set("ai", { alert_pct: +e.target.value })} /></Field>
            <div className="flex items-end"><Toggle checked={s.ai.hard_limit} onChange={(v) => set("ai", { hard_limit: v })} label="Limite rígido" /></div>
            {(["cut_planning", "copywriting"] as const).map((task) => (
              <Field key={task} label={task === "cut_planning" ? "Planejar cortes" : "Títulos/legendas"} className="sm:col-span-3 lg:col-span-1">
                <Select value={s.ai.routing[task]} onChange={(e) => set("ai", { routing: { ...s.ai.routing, [task]: e.target.value } })}>
                  <option value="heuristic">heurística local (grátis)</option><option value="auto">auto (local → barato)</option>
                  {(cfg.data?.providers ?? []).filter((p) => !p.blocked).map((p) => <option key={p.provider} value={p.provider}>{p.provider}</option>)}
                </Select>
              </Field>
            ))}
          </div>
          <ul className="mt-4 space-y-2">
            {cfg.data.providers.map((p) => {
              const pc = s.ai.providers[p.provider];
              return (
                <li key={p.provider} className="grid items-center gap-2 rounded-lg border border-line p-3 sm:grid-cols-[1fr_1.4fr_auto]">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.provider}</span>
                    {p.blocked ? <Badge className="border-muted/40 text-muted">bloqueado (grátis)</Badge>
                      : p.paid ? <Badge className="border-warn/40 text-warn">pago</Badge>
                      : <Badge className="border-ok/40 text-ok">{p.provider === "ollama" ? "local" : "free tier"}</Badge>}
                    <Badge className={p.has_key ? "border-ok/40 text-ok" : "border-bad/40 text-bad"}>{p.has_key ? "chave ok" : "sem chave"}</Badge>
                  </div>
                  <Input value={pc.model} aria-label={`modelo ${p.provider}`} className="h-8 text-xs"
                    onChange={(e) => set("ai", { providers: { ...s.ai.providers, [p.provider]: { ...pc, model: e.target.value } } })} />
                  <Toggle checked={pc.enabled && !p.blocked} disabled={p.blocked} label="ativo" onChange={(v) => set("ai", { providers: { ...s.ai.providers, [p.provider]: { ...pc, enabled: v } } })} />
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-xs text-muted">Chaves via variáveis STARK_*_API_KEY no servidor. Assinaturas (Claude/ChatGPT/Gemini) não viram API: use o Modo Operador no Claude Code.</p>
        </Panel>

        <Panel eyebrow="marca" title="Logo e legendas padrão" id="brand">
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-[10px] border border-line px-4 text-sm hover:text-cyan">
              <ImageUp className="size-4" aria-hidden />Enviar logo PNG
              <input type="file" accept="image/png" className="sr-only" onChange={(e) => e.target.files?.[0] && logo(e.target.files[0])} />
            </label>
            <span className="text-xs text-muted">{s.branding.logo_path ?? "sem logo"}</span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Field label={`Opacidade ${s.branding.logo_opacity}`}><input type="range" min={0.2} max={1} step={0.05} value={s.branding.logo_opacity} className="w-full" onChange={(e) => set("branding", { logo_opacity: +e.target.value })} /></Field>
            <Field label={`Tamanho logo ${Math.round(s.branding.logo_scale * 100)}%`}><input type="range" min={0.06} max={0.3} step={0.01} value={s.branding.logo_scale} className="w-full" onChange={(e) => set("branding", { logo_scale: +e.target.value })} /></Field>
            <Field label="Fonte"><Input value={s.captions.font} onChange={(e) => set("captions", { font: e.target.value })} /></Field>
            <Field label={`Tamanho legenda ${s.captions.size}`}><input type="range" min={48} max={130} value={s.captions.size} className="w-full" onChange={(e) => set("captions", { size: +e.target.value })} /></Field>
            <Field label="Destaque"><Input type="color" value={s.captions.highlight} className="p-1" onChange={(e) => set("captions", { highlight: e.target.value })} /></Field>
            <Field label="Palavras/linha"><Input type="number" min={1} max={5} value={s.captions.words_per_line} onChange={(e) => set("captions", { words_per_line: +e.target.value })} /></Field>
          </div>
        </Panel>

        <Panel eyebrow="máquina de clipes" title="Radar ao vivo" id="radar">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Jogo/categoria (Twitch)" hint="nome exato, ex.: Grand Theft Auto VI"><Input value={s.radar.game} onChange={(e) => set("radar", { game: e.target.value })} /></Field>
            <Field label="Busca de lives no YouTube"><Input value={s.radar.youtube_query} onChange={(e) => set("radar", { youtube_query: e.target.value })} /></Field>
            <Field label="Idiomas (vazio = todos)" hint="ex.: pt, en"><Input value={s.radar.languages.join(", ")} onChange={(e) => set("radar", { languages: e.target.value.split(/[\s,]+/).filter(Boolean) })} /></Field>
            <Field label="Máx. de lives no radar"><Input type="number" min={10} max={100} value={s.radar.max_channels} onChange={(e) => set("radar", { max_channels: +e.target.value })} /></Field>
            <Field label={`Sensibilidade do pico ${s.radar.sensitivity}`} hint="menor = mais momentos"><input type="range" min={2} max={5} step={0.5} value={s.radar.sensitivity} className="w-full" onChange={(e) => set("radar", { sensitivity: +e.target.value })} /></Field>
            <Field label="Mínimo de msgs por 10 s"><Input type="number" min={5} max={200} value={s.radar.min_rate} onChange={(e) => set("radar", { min_rate: +e.target.value })} /></Field>
          </div>
          <p className="mt-2 text-xs text-muted">Mudanças valem após reiniciar (menu → Clipzou → Atualizar e reiniciar).</p>
        </Panel>

        <Panel eyebrow="cadência" title="Ritmo de publicação" id="cad">
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Intervalo mín. (min)"><Input type="number" min={15} value={s.cadence.min_gap_minutes} onChange={(e) => set("cadence", { min_gap_minutes: +e.target.value })} /></Field>
            <Field label="Silêncio início (h)"><Input type="number" min={0} max={23} value={s.cadence.quiet_start} onChange={(e) => set("cadence", { quiet_start: +e.target.value })} /></Field>
            <Field label="Silêncio fim (h)"><Input type="number" min={0} max={23} value={s.cadence.quiet_end} onChange={(e) => set("cadence", { quiet_end: +e.target.value })} /></Field>
            <Field label="Fuso (UTC±h)"><Input type="number" min={-12} max={14} value={s.cadence.tz_offset_h} onChange={(e) => set("cadence", { tz_offset_h: +e.target.value })} /></Field>
          </div>
          <p className="mt-2 text-xs text-muted">Limite diário é por conta (Publicar). Falhas seguidas cortam o limite pela metade automaticamente.</p>
        </Panel>

        <Panel eyebrow="consumo" title="Chamadas de IA recentes" id="use">
          {!usage.data?.length ? <p className="text-sm text-muted">Nenhuma chamada paga/local registrada.</p> : (
            <ul className="space-y-1 text-xs">
              {usage.data.map((u) => (
                <li key={u.id} className="flex justify-between gap-2 border-b border-line py-1">
                  <span>{u.provider}/{u.task} {u.ok ? "" : `· erro: ${u.error}`}</span>
                  <span className="font-mono text-muted">{u.input_tokens}+{u.output_tokens} tok · {usd(u.cost_usd)} · {ago(u.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel eyebrow="auditoria" title="Últimas ações" id="audit" className="xl:col-span-2">
          <ul className="grid gap-1 text-xs sm:grid-cols-2">
            {audit.data?.map((a) => (
              <li key={a.id} className="flex justify-between gap-2 border-b border-line py-1">
                <span><span className="text-cyan">{a.action}</span> {a.target}</span><span className="text-muted">{a.actor} · {ago(a.created_at)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
