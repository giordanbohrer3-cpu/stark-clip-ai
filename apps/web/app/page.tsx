"use client";
import { AlertTriangle, CheckCircle2, Cpu, XCircle } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { HoloCore } from "@/components/holo-core";
import { JobTimeline } from "@/components/job-timeline";
import { Button, Empty, Note, Panel, Stat } from "@/components/ui";
import { usePoll } from "@/lib/api";
import { num, usd } from "@/lib/format";
import type { Health, JobRow, SettingsResp, Stats } from "@/lib/types";

export default function Dashboard() {
  const stats = usePoll<Stats>("/stats", 5000);
  const jobs = usePoll<JobRow[]>("/jobs?limit=12", 2500);
  const health = usePoll<Health>("/health", 15000);
  const cfg = usePoll<SettingsResp>("/settings", 30000);
  const reduce = useReducedMotion();
  const s = stats.data;
  const a = s?.analytics;

  const tiles = s
    ? [
        { label: "Vídeos", value: s.videos.total, hint: `${s.videos.analyzed} analisados`, tone: "ink" as const },
        { label: "Cortes p/ aprovar", value: s.clips.awaiting_approval, hint: `${s.clips.candidates} candidatos`, tone: "warn" as const },
        { label: "Renderizando", value: s.clips.rendering, hint: `${s.jobs.active} jobs ativos`, tone: "cyan" as const },
        { label: "Prontos p/ postar", value: s.clips.ready, hint: `${s.clips.edited} editados`, tone: "ok" as const },
        { label: "Agendados", value: s.posts.scheduled, hint: "na fila de publicação", tone: "cyan" as const },
        { label: "Entregues", value: s.posts.done, hint: "publicados / kits / exportados", tone: "ok" as const },
        { label: "IA no mês", value: usd(s.ai.month_spend_usd), hint: cfg.data?.env.free_only ? "modo 100% grátis" : s.ai.budget_usd ? `orçamento ${usd(s.ai.budget_usd)}` : "APIs pagas desligadas", tone: "violet" as const },
        { label: "Armazenamento", value: `${num(s.storage_mb)} MB`, hint: "mídia + renders locais", tone: "ink" as const },
      ]
    : [];

  return (
    <div className="space-y-6">
      <section className="hud-panel relative overflow-hidden p-5 sm:p-7">
        <div className="grid items-center gap-6 md:grid-cols-[1fr_220px]">
          <div>
            <p className="hud-label">STARK CLIP AI · centro de comando</p>
            <h1 className="glow-text mt-2 text-2xl font-semibold sm:text-3xl">Do vídeo autorizado ao corte pronto.</h1>
            <p className="mt-2 max-w-xl text-sm text-muted">
              Transcrição local, 3 cortes por vídeo com score explicável, legendas animadas, reframe 9:16 e publicação
              assistida — com orçamento e pausa global sob seu controle.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/library"><Button variant="primary">Enviar vídeo</Button></Link>
              <Link href="/publish"><Button>Agenda</Button></Link>
            </div>
          </div>
          <HoloCore activity={s?.jobs.active ?? 0} className="mx-auto hidden size-[200px] md:block" />
        </div>
      </section>

      {stats.error && <Note tone="bad">Motor indisponível: {stats.error}</Note>}
      {s?.alerts.map((al) => (
        <Note key={al} tone="warn"><AlertTriangle className="mr-1 inline size-4" aria-hidden />{al}</Note>
      ))}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((t, i) => (
          <motion.div key={t.label} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <Stat {...t} />
          </motion.div>
        ))}
        {!s && !stats.error && Array.from({ length: 8 }, (_, i) => <div key={i} className="hud-panel h-[104px] animate-pulse" />)}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Panel eyebrow="pipeline" title="Timeline de tarefas" id="timeline">
          {jobs.data ? <JobTimeline jobs={jobs.data} onChange={jobs.reload} /> : <p className="text-sm text-muted">carregando…</p>}
        </Panel>
        <div className="space-y-6">
          <Panel eyebrow="resultados observados" title="Desempenho" id="perf">
            {a && a.posts_with_data > 0 ? (
              <dl className="grid grid-cols-2 gap-3 text-sm">
                {[["Visualizações", a.views], ["Curtidas", a.likes], ["Comentários", a.comments], ["Compart.", a.shares],
                  ["Seguidores", a.followers]].map(([k, v]) => (
                  <div key={k as string} className="rounded-lg border border-line p-3">
                    <dt className="hud-label">{k}</dt><dd className="mt-1 font-mono text-lg">{num(v as number)}</dd>
                  </div>
                ))}
                <div className="rounded-lg border border-line p-3">
                  <dt className="hud-label">Receita confirmada</dt><dd className="mt-1 font-mono text-lg">R$ {a.revenue_confirmed.toFixed(2)}</dd>
                </div>
                <p className="col-span-2 text-xs text-muted">Base: {a.posts_with_data} post(s) com dados registrados. Sem projeções misturadas.</p>
              </dl>
            ) : (
              <Empty title="Sem métricas observadas ainda">
                Registre resultados na agenda (manual) ou conecte APIs oficiais. Nada aqui é estimado.
              </Empty>
            )}
          </Panel>
          <Panel eyebrow="serviços" title="Estado do sistema" id="svc">
            <ul className="space-y-2 text-sm">
              {[
                ["Motor (API)", !!health.data && !health.error],
                ["FFmpeg", !!health.data?.ffmpeg],
                ["Banco de dados", !!health.data?.db],
                [`Whisper local (${health.data?.whisper_model ?? "?"})`, !!health.data],
                ["YouTube Data API", !!health.data?.youtube_api],
              ].map(([k, ok]) => (
                <li key={k as string} className="flex items-center justify-between">
                  <span className="text-muted">{k}</span>
                  {ok ? <CheckCircle2 className="size-4 text-ok" aria-label="ok" /> : <XCircle className="size-4 text-bad" aria-label="indisponível" />}
                </li>
              ))}
              {cfg.data?.providers.map((p) => (
                <li key={p.provider} className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted"><Cpu className="size-3.5" aria-hidden />{p.provider} · {p.model}</span>
                  <span className={p.enabled && p.has_key ? "text-ok" : "text-muted"}>
                    {p.enabled ? (p.has_key ? "ativo" : "sem chave") : "desligado"}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
