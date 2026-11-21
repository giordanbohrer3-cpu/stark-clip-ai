"use client";
import { ClipboardCopy, Download, Film, RefreshCw, Save, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Field, Input, Note, Panel, Progress, Select, Textarea, Toggle } from "@/components/ui";
import { activeJob, api, BASE, fileUrl, usePoll } from "@/lib/api";
import { clockMs } from "@/lib/format";
import type { CaptionStyle, Clip, ClipContext, JobRow, Word } from "@/lib/types";

const PLATFORMS = ["tiktok", "instagram", "facebook", "youtube"] as const;

function chunks(words: Word[], perLine: number) {
  const out: Word[][] = [];
  let cur: Word[] = [];
  for (const w of words) {
    const text = [...cur, w].map((x) => x[2]).join(" ");
    if (cur.length && (cur.length >= perLine || w[0] - cur[cur.length - 1][1] > 0.6 || text.length > 22 || /[.!?…]$/.test(cur[cur.length - 1][2]))) {
      out.push(cur);
      cur = [];
    }
    cur.push(w);
  }
  if (cur.length) out.push(cur);
  return out;
}

export default function Studio() {
  const { id } = useParams<{ id: string }>();
  const clip = usePoll<Clip>(`/clips/${id}`, 3000);
  const ctx = usePoll<ClipContext>(`/clips/${id}/context`, 0);
  const jobs = usePoll<JobRow[]>(`/clips/${id}/jobs`, 2000);
  const vid = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(0);
  const [editDraft, setEdit] = useState<Partial<Clip> | null>(null);
  const [styleDraft, setStyle] = useState<CaptionStyle | null>(null);
  const [wordsDraft, setWords] = useState<Word[] | null>(null);
  const [view, setView] = useState<"live" | "preview" | "output">("live");
  const [tab, setTab] = useState<(typeof PLATFORMS)[number]>("tiktok");
  const [copyDraft, setCopy] = useState<Clip["copy_text"] | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [busy, setBusy] = useState("");

  const c = clip.data;
  const edit = editDraft ?? (c ? { start_s: c.start_s, end_s: c.end_s, layout: c.layout, remove_pauses: c.remove_pauses, denoise: c.denoise, logo: c.logo } : null);
  const copy = copyDraft ?? (c?.copy_text?.captions ? c.copy_text : null);
  const style = styleDraft ?? (ctx.data ? { ...ctx.data.caption_defaults, ...(c?.caption_style as Partial<CaptionStyle>) } : null);
  const words = wordsDraft ?? ctx.data?.words ?? null;

  const start = edit?.start_s ?? 0;
  const end = edit?.end_s ?? 0;
  const inRange = useMemo(() => (words ?? []).filter((w) => w[1] > start && w[0] < end), [words, start, end]);
  const cks = useMemo(() => chunks(inRange, style?.words_per_line ?? 3), [inRange, style?.words_per_line]);
  const active = cks.find((ch, i) => t >= ch[0][0] && t <= Math.min(cks[i + 1]?.[0][0] ?? Infinity, ch[ch.length - 1][1] + 0.35));
  const job = activeJob(jobs.data);
  const dirty = !!c && !!edit && (edit.start_s !== c.start_s || edit.end_s !== c.end_s || edit.layout !== c.layout ||
    edit.remove_pauses !== c.remove_pauses || edit.denoise !== c.denoise || edit.logo !== c.logo);

  const onTime = () => {
    const v = vid.current;
    if (!v) return;
    setT(v.currentTime);
    if (view === "live" && (v.currentTime > end || v.currentTime < start - 0.5)) v.currentTime = start;
  };
  useEffect(() => {
    if (view === "live" && vid.current && start) vid.current.currentTime = start;
  }, [view, start]);

  const save = async () => {
    if (!c || !edit || !style) return;
    setBusy("save");
    try {
      const base = ctx.data?.words ?? [];
      const changed = words && words.some((w, i) => w[2] !== base[i]?.[2]);
      await api(`/clips/${id}`, { method: "PATCH", json: { ...edit, caption_style: style, ...(changed ? { words_override: words!.map((w) => [w[0], w[1], w[2]]) } : {}), ...(copy ? { copy_text: copy } : {}) } });
      setMsg({ tone: "ok", text: "Salvo. Renderize para aplicar." });
      clip.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const render = async (preview: boolean) => {
    await save();
    setBusy(preview ? "rp" : "rf");
    try {
      await api(`/clips/${id}/render`, { method: "POST", json: { preview } });
      jobs.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const regen = async () => {
    setBusy("copy");
    try {
      const r = await api<Clip>(`/clips/${id}/copy`, { method: "POST" });
      setCopy(r.copy_text);
    } finally {
      setBusy("");
    }
  };

  if (clip.error) return <Note tone="bad">{clip.error}</Note>;
  if (!c || !edit || !style || !ctx.data) return <p className="text-muted">carregando estúdio…</p>;
  const v = ctx.data.video;
  const src = view === "live" ? `${BASE}/videos/${v.id}/media` : fileUrl(c.id, view);
  const span = Math.max(1, end - start);
  const capColor = style.primary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="hud-label"><Link href={`/videos/${v.id}`} className="hover:text-cyan">{v.title}</Link> / corte #{c.id}</p>
          <h1 className="mt-1 text-xl font-semibold">{ctx.data.candidate?.title ?? "Corte"}</h1>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge status={c.status} />
            {c.layout_used && <Badge>layout: {c.layout_used}</Badge>}
            {c.duration_s > 0 && <Badge>{c.duration_s.toFixed(1)}s renderizado</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={save} loading={busy === "save"} icon={<Save className="size-4" />}>Salvar</Button>
          <Button onClick={() => render(true)} loading={busy === "rp"} disabled={!!job} icon={<Film className="size-4" />}>Prévia 540p</Button>
          <Button variant="primary" onClick={() => render(false)} loading={busy === "rf"} disabled={!!job} icon={<Sparkles className="size-4" />}>Render final</Button>
        </div>
      </div>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      {c.error && <Note tone="bad">{c.error}</Note>}
      {job && (
        <div className="hud-panel p-4">
          <Progress value={job.progress} active label="render" />
          <p className="mt-1 text-xs text-muted">{job.payload?.preview ? "prévia" : "final"} · {job.stage} · {Math.round(job.progress * 100)}%</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(260px,380px)_1fr]">
        <div className="space-y-3">
          <div className="flex gap-1 rounded-[10px] border border-line p-1" role="tablist" aria-label="fonte da prévia">
            {([["live", "Ao vivo"], ["preview", "Prévia"], ["output", "Final"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={view === k} disabled={k !== "live" && !c.files.includes(k)}
                onClick={() => setView(k)} className={`flex-1 rounded-lg py-1.5 text-xs disabled:opacity-40 ${view === k ? "bg-cyan/15 text-cyan" : "text-muted"}`}>{l}</button>
            ))}
          </div>
          <div className="relative mx-auto aspect-[9/16] max-h-[72vh] overflow-hidden rounded-2xl border border-cyan/30 bg-black shadow-[0_0_40px_-12px_var(--cyan)]"
            style={{ containerType: "size" }}>
            <video key={src} ref={vid} src={src} controls playsInline preload="metadata" onTimeUpdate={onTime}
              onLoadedMetadata={(e) => { if (view === "live") e.currentTarget.currentTime = start; }}
              className={`size-full ${view === "live" ? "object-cover" : "object-contain"}`} />
            {view === "live" && active && (
              <div className="pointer-events-none absolute inset-x-[12%] text-center font-black leading-tight"
                style={{ top: `${style.position * 100}%`, transform: "translateY(-50%)", fontSize: `${style.size / 19.2}cqh` }}>
                <span style={{ WebkitTextStroke: `1px ${style.outline}`, textShadow: `0 2px 0 ${style.outline}, 0 0 10px #000` }}>
                  {active.map((w, i) => {
                    const on = t >= w[0] && t < (active[i + 1]?.[0] ?? w[1] + 0.35);
                    const txt = style.uppercase ? w[2].toUpperCase() : w[2];
                    return <span key={i} style={{ color: on ? style.highlight : capColor, display: "inline-block", transform: on ? "scale(1.1)" : undefined, margin: "0 .15em" }}>{txt}</span>;
                  })}
                </span>
              </div>
            )}
          </div>
          {view === "live" && <p className="text-center text-xs text-muted">Ao vivo = aproximação (centro, sem cortes de pausa). O render aplica rastreio de rosto.</p>}
        </div>

        <div className="space-y-6">
          <Panel eyebrow="timeline" title="Trecho e legendas" id="tl">
            <div className="space-y-3">
              <div className="relative h-16 rounded-lg border border-line bg-black/30" onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                if (vid.current && view === "live") vid.current.currentTime = start + ((e.clientX - r.left) / r.width) * span;
              }}>
                <div className="absolute inset-x-0 top-1 h-6 rounded bg-gradient-to-r from-blue/40 to-violet/40" aria-hidden />
                {cks.map((ch, i) => (
                  <div key={i} className="absolute top-8 h-6 rounded border border-cyan/40 bg-cyan/15" aria-hidden
                    style={{ left: `${((ch[0][0] - start) / span) * 100}%`, width: `${Math.max(0.5, ((ch[ch.length - 1][1] - ch[0][0]) / span) * 100)}%` }} />
                ))}
                {view === "live" && <div className="absolute inset-y-0 w-0.5 bg-warn" style={{ left: `${Math.min(100, Math.max(0, ((t - start) / span) * 100))}%` }} aria-hidden />}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={`Início ${clockMs(start)}`}>
                  <input type="range" className="w-full" min={Math.max(0, (ctx.data.candidate?.start_s ?? start) - 30)} max={end - 3} step={0.1} value={start}
                    onChange={(e) => setEdit({ ...edit, start_s: +e.target.value })} aria-label="início do corte" />
                </Field>
                <Field label={`Fim ${clockMs(end)} · ${span.toFixed(1)}s`}>
                  <input type="range" className="w-full" min={start + 3} max={Math.min(v.duration_s, (ctx.data.candidate?.end_s ?? end) + 30)} step={0.1} value={end}
                    onChange={(e) => setEdit({ ...edit, end_s: +e.target.value })} aria-label="fim do corte" />
                </Field>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Enquadramento">
                  <Select value={edit.layout} onChange={(e) => setEdit({ ...edit, layout: e.target.value })}>
                    <option value="auto">auto (rosto/split)</option><option value="face">seguir rosto</option>
                    <option value="split">tela dividida (2 pessoas)</option><option value="center">centro</option><option value="fit">encaixar + fundo desfocado</option>
                  </Select>
                </Field>
                <div className="space-y-2 sm:col-span-2">
                  <Toggle checked={!!edit.remove_pauses} onChange={(x) => setEdit({ ...edit, remove_pauses: x })} label="Remover pausas (jump cuts)" />
                  <Toggle checked={!!edit.denoise} onChange={(x) => setEdit({ ...edit, denoise: x })} label="Reduzir ruído" />
                  <Toggle checked={!!edit.logo} onChange={(x) => setEdit({ ...edit, logo: x })} label="Logo da marca" hint="envie em Config → Marca" />
                </div>
              </div>
            </div>
          </Panel>

          <Panel eyebrow="legendas" title="Estilo e revisão" id="cap">
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label={`Tamanho ${style.size}`}><input type="range" min={48} max={130} value={style.size} className="w-full" onChange={(e) => setStyle({ ...style, size: +e.target.value })} /></Field>
              <Field label={`Posição ${Math.round(style.position * 100)}%`}><input type="range" min={0.2} max={0.85} step={0.01} value={style.position} className="w-full" onChange={(e) => setStyle({ ...style, position: +e.target.value })} /></Field>
              <Field label="Destaque"><Input type="color" value={style.highlight} onChange={(e) => setStyle({ ...style, highlight: e.target.value })} className="p-1" /></Field>
              <Field label="Texto"><Input type="color" value={style.primary} onChange={(e) => setStyle({ ...style, primary: e.target.value })} className="p-1" /></Field>
              <Field label="Palavras/linha"><Select value={style.words_per_line} onChange={(e) => setStyle({ ...style, words_per_line: +e.target.value })}>{[1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</Select></Field>
              <div className="flex items-end sm:col-span-3"><Toggle checked={style.uppercase} onChange={(x) => setStyle({ ...style, uppercase: x })} label="CAIXA ALTA" /></div>
            </div>
            <p className="hud-label mt-5">revisão manual (obrigatória antes de publicar)</p>
            <div className="mt-2 flex max-h-56 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-line p-2">
              {inRange.map((w) => {
                const idx = words!.indexOf(w);
                return (
                  <input key={idx} value={w[2]} aria-label={`palavra em ${w[0].toFixed(1)}s`}
                    onChange={(e) => setWords(words!.map((x, i) => (i === idx ? [x[0], x[1], e.target.value] : x)))}
                    className={`rounded border bg-black/30 px-1.5 py-0.5 text-xs ${t >= w[0] && t < w[1] ? "border-cyan text-cyan" : "border-line"} ${(w[3] ?? 1) < 0.6 ? "text-warn" : ""}`}
                    style={{ width: `${Math.max(4, w[2].length + 2.5)}ch` }} />
                );
              })}
            </div>
            <p className="mt-1 text-xs text-muted">Amarelo = baixa confiança do Whisper. Corrija nomes, gírias e termos técnicos.</p>
          </Panel>

          <Panel eyebrow="entrega" title="Arquivos e textos" id="out" actions={
            <Button size="sm" onClick={regen} loading={busy === "copy"} icon={<RefreshCw className="size-3.5" />}>Gerar textos</Button>
          }>
            <div className="flex flex-wrap gap-2">
              {(["output", "srt", "ass", "cover"] as const).map((k) => (
                <a key={k} href={c.files.includes(k) ? fileUrl(c.id, k, true) : undefined} aria-disabled={!c.files.includes(k)}
                  className={`inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-line px-3 text-xs ${c.files.includes(k) ? "hover:border-cyan/50 hover:text-cyan" : "pointer-events-none opacity-40"}`}>
                  <Download className="size-3.5" aria-hidden />{{ output: "MP4", srt: "SRT", ass: "ASS", cover: "Capa" }[k]}
                </a>
              ))}
              <Link href={`/publish?clip=${c.id}`} className={c.status === "ready" ? "" : "pointer-events-none opacity-40"}>
                <Button size="sm" variant="primary" icon={<Send className="size-3.5" />}>Agendar</Button>
              </Link>
            </div>
            {copy?.captions ? (
              <div className="mt-4 space-y-3">
                <Field label="Título"><Input value={copy.title ?? ""} onChange={(e) => setCopy({ ...copy, title: e.target.value })} /></Field>
                <div className="flex gap-1" role="tablist" aria-label="rede">
                  {PLATFORMS.map((p) => (
                    <button key={p} role="tab" aria-selected={tab === p} onClick={() => setTab(p)}
                      className={`rounded-lg px-3 py-1 text-xs ${tab === p ? "bg-cyan/15 text-cyan" : "text-muted"}`}>{p}</button>
                  ))}
                </div>
                <Textarea value={copy.captions[tab] ?? ""} onChange={(e) => setCopy({ ...copy, captions: { ...copy.captions, [tab]: e.target.value } })} className="min-h-32" aria-label={`legenda ${tab}`} />
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-muted">{(copy.hashtags?.[tab] ?? []).join(" ")} · fonte: {copy.source}</p>
                  <Button size="sm" onClick={() => navigator.clipboard.writeText(copy.captions?.[tab] ?? "")} icon={<ClipboardCopy className="size-3.5" />}>Copiar</Button>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm text-muted">Textos são gerados após o render final (ou clique em Gerar textos).</p>
            )}
          </Panel>
          {dirty && <Note tone="warn">Alterações não salvas no trecho/layout.</Note>}
        </div>
      </div>
    </div>
  );
}
