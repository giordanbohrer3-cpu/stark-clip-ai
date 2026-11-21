"use client";
import { ClipboardCopy, Clapperboard, Expand, Play, ThumbsDown, Upload } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { JobTimeline } from "@/components/job-timeline";
import { Badge, Button, Empty, Note, Panel, ScoreRing, Select, Textarea } from "@/components/ui";
import { api, BASE, usePoll } from "@/lib/api";
import { clock } from "@/lib/format";
import type { Candidate, Clip, VideoDetail } from "@/lib/types";

const FEAT: Record<string, string> = {
  hook: "Gancho", closure: "Conclusão", energy: "Energia", density: "Ritmo", emotion: "Emoção",
  cohesion: "Coesão", dur_fit: "Duração", scenes: "Dinâmica", ai_hook: "Nota IA",
};

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const d = usePoll<VideoDetail>(`/videos/${id}`, 3000);
  const player = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);
  const [mode, setMode] = useState("short");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "info"; text: string } | null>(null);
  const [opJson, setOpJson] = useState("");
  const [busy, setBusy] = useState("");

  const run = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ tone: "ok", text: ok });
      d.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const preview = (c: Candidate) => {
    const v = player.current;
    if (!v) return;
    v.currentTime = c.start_s;
    stopAt.current = c.end_s;
    v.play().catch(() => {});
  };

  const openStudio = (c: Candidate) =>
    run(`edit${c.id}`, async () => {
      const clip = await api<Clip>(`/candidates/${c.id}/edit`, { method: "POST" });
      router.push(`/studio/${clip.id}`);
    });

  const copyRequest = () =>
    run("op", async () => {
      const txt = await api<string>(`/videos/${id}/analysis-request?mode=${mode}`);
      await navigator.clipboard.writeText(txt);
    }, "Pedido copiado. Cole no Claude Code (skill /stark-cuts) ou outro CLI oficial e traga o JSON.");

  const importCuts = () =>
    run("import", async () => {
      const parsed = JSON.parse(opJson);
      await api(`/videos/${id}/cuts/import?mode=${mode}`, { method: "POST", json: { cuts: parsed.cuts ?? parsed } });
      setOpJson("");
    }, "Cortes do operador importados.");

  if (d.error) return <Note tone="bad">{d.error}</Note>;
  if (!d.data) return <p className="text-muted">carregando…</p>;
  const { video: v, candidates, clips, jobs, transcript, rights } = d.data;
  const clipFor = (c: Candidate) => clips.find((x) => x.candidate_id === c.id);
  const analyzing = jobs.some((j) => j.kind === "analyze" && (j.status === "running" || j.status === "queued"));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="hud-label"><Link href="/library" className="hover:text-cyan">vídeos</Link> / #{v.id}</p>
          <h1 className="mt-1 text-xl font-semibold">{v.title}</h1>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge status={v.status} />
            <Badge>{clock(v.duration_s)} · {v.width}×{v.height}</Badge>
            {rights[0] && <Badge className="border-ok/40 text-ok">{rights[0].rights_type} · {rights[0].holder}</Badge>}
            {rights[0] && !rights[0].allows_commercial && <Badge className="border-warn/40 text-warn">sem uso comercial</Badge>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="modo de duração" className="w-44">
            <option value="short">curto (viral)</option>
            <option value="long">longo &gt;60s (monetização)</option>
          </Select>
          <Button variant="primary" loading={busy === "proc" || analyzing} disabled={!v.rights_ok}
            onClick={() => run("proc", () => api(`/videos/${id}/process`, { method: "POST", json: { mode } }))}>
            {candidates.length ? "Reanalisar" : "Analisar"}
          </Button>
        </div>
      </div>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      {v.error && <Note tone="bad">{v.error}</Note>}

      <div className="grid gap-6 xl:grid-cols-[1fr_1.15fr]">
        <div className="space-y-6">
          <Panel eyebrow="original" title="Pré-visualização" id="pv">
            <video ref={player} src={`${BASE}/videos/${id}/media`} controls preload="metadata" className="aspect-video w-full rounded-lg bg-black"
              onTimeUpdate={(e) => {
                if (stopAt.current && e.currentTarget.currentTime >= stopAt.current) {
                  e.currentTarget.pause();
                  stopAt.current = null;
                }
              }} />
          </Panel>
          <Panel eyebrow="pipeline" title="Processamento" id="jobs">
            <JobTimeline jobs={jobs} onChange={d.reload} />
          </Panel>
          <Panel eyebrow="modo operador" title="Usar sua assinatura (Claude Code / CLI)" id="op">
            <p className="text-sm text-muted">
              Sem API paga: copie o pedido, rode no Claude Code (skill <code className="text-cyan">/stark-cuts</code>), Gemini CLI ou
              Codex autenticados na sua conta, e cole o JSON de volta. O motor valida índices, duração e sobreposição.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={copyRequest} loading={busy === "op"} disabled={!transcript} icon={<ClipboardCopy className="size-4" />}>Copiar pedido</Button>
            </div>
            <Textarea className="mt-3 font-mono text-xs" value={opJson} onChange={(e) => setOpJson(e.target.value)}
              placeholder='{"cuts":[{"start_idx":3,"end_idx":9,"title":"…","summary":"…","justification":"…","hook_score":80}]}' aria-label="JSON de cortes" />
            <div className="mt-2 flex justify-end">
              <Button onClick={importCuts} disabled={!opJson.trim()} loading={busy === "import"} icon={<Upload className="size-4" />}>Importar cortes</Button>
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel eyebrow="motor de cortes" title={`Candidatos (${candidates.length})`} id="cands">
            {!candidates.length ? (
              <Empty title={analyzing ? "Analisando…" : "Sem cortes ainda"}>
                {analyzing ? "Transcrição local + análise de momentos em andamento." : "Clique em Analisar. Se o conteúdo não render 3 cortes bons, o sistema entrega menos — nunca cortes artificiais."}
              </Empty>
            ) : (
              <ol className="space-y-4">
                {candidates.map((c) => {
                  const clip = clipFor(c);
                  return (
                    <li key={c.id} className={`rounded-xl border p-4 ${c.status === "rejected" ? "border-line opacity-55" : "border-cyan/25 bg-cyan/[0.03]"}`}>
                      <div className="flex gap-4">
                        <ScoreRing score={c.score} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-muted">#{c.rank}</span>
                            <Badge status={c.status} />
                            <Badge>{c.source}</Badge>
                            <span className="font-mono text-xs text-muted">{clock(c.start_s)}–{clock(c.end_s)} · {c.duration_s.toFixed(0)}s</span>
                          </div>
                          <h3 className="mt-1.5 font-medium">{c.title}</h3>
                          <p className="mt-1 text-sm text-muted">{c.justification}</p>
                        </div>
                      </div>
                      <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-8">
                        {Object.entries(FEAT).filter(([k]) => k in c.score_breakdown).map(([k, label]) => {
                          const val = c.score_breakdown[k];
                          const pct = k === "ai_hook" ? val : val * 100;
                          return (
                            <div key={k} title={`${label}: ${Math.round(pct)}`}>
                              <div className="h-1 rounded bg-white/10"><div className="h-1 rounded bg-cyan" style={{ width: `${pct}%` }} /></div>
                              <p className="mt-1 truncate text-[0.62rem] text-muted">{label}</p>
                            </div>
                          );
                        })}
                      </div>
                      <details className="mt-3 text-sm">
                        <summary className="cursor-pointer text-xs text-muted hover:text-cyan">transcrição do corte</summary>
                        <p className="mt-2 text-muted">{c.transcript_text}</p>
                      </details>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => preview(c)} icon={<Play className="size-3.5" />}>Prévia</Button>
                        <Button size="sm" variant="primary" onClick={() => openStudio(c)} loading={busy === `edit${c.id}`} icon={<Clapperboard className="size-3.5" />}>
                          {clip ? `Estúdio (${clip.status})` : "Editar no estúdio"}
                        </Button>
                        <Button size="sm" onClick={() => run(`ex${c.id}`, () => api(`/candidates/${c.id}/expand`, { method: "POST" }), "Versão longa criada.")}
                          loading={busy === `ex${c.id}`} icon={<Expand className="size-3.5" />}>Versão longa</Button>
                        {c.status !== "rejected" && !clip && (
                          <Button size="sm" variant="subtle" onClick={() => run(`rj${c.id}`, () => api(`/candidates/${c.id}`, { method: "PATCH", json: { status: "rejected" } }))}
                            icon={<ThumbsDown className="size-3.5" />}>Rejeitar</Button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>
          {transcript && (
            <Panel eyebrow={`transcrição · ${transcript.model} · ${transcript.language}`} title={`${transcript.words} palavras`} id="tr">
              <ol className="max-h-80 space-y-1 overflow-y-auto pr-2 text-sm">
                {transcript.segments.map(([s, , t], i) => (
                  <li key={i}>
                    <button className="font-mono text-xs text-cyan hover:underline" onClick={() => { if (player.current) { player.current.currentTime = s; player.current.play().catch(() => {}); } }}>
                      {clock(s)}
                    </button>{" "}
                    <span className="text-muted">{t}</span>
                  </li>
                ))}
              </ol>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
