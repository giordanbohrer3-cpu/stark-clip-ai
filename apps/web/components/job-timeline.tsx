"use client";
import { RotateCcw, X } from "lucide-react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import type { JobRow } from "@/lib/types";
import { Badge, Button, Empty, Progress } from "./ui";

const KIND: Record<string, string> = { analyze: "Análise + cortes", render: "Render", publish: "Publicação" };

export function JobTimeline({ jobs, onChange, compact }: { jobs: JobRow[]; onChange?: () => void; compact?: boolean }) {
  if (!jobs.length) return <Empty title="Fila vazia">Envie um vídeo autorizado para iniciar o pipeline.</Empty>;
  const act = async (id: number, op: "cancel" | "retry") => {
    await api(`/jobs/${id}/${op}`, { method: "POST" });
    onChange?.();
  };
  return (
    <ol className="space-y-3" aria-live="polite">
      {jobs.map((j) => {
        const live = j.status === "running" || j.status === "queued";
        return (
          <li key={j.id} className="rounded-xl border border-line bg-black/20 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-xs text-muted">#{j.id}</span>
                <span className="truncate text-sm font-medium">{KIND[j.kind] ?? j.kind}</span>
                <span className="font-mono text-xs text-muted">ref {j.ref_id}</span>
                {j.kind === "render" && <span className="text-xs text-muted">{j.payload?.preview ? "prévia" : "final"}</span>}
              </div>
              <div className="flex items-center gap-2">
                <Badge status={j.status} />
                <span className="text-xs text-muted">{ago(j.created_at)}</span>
                {live && !compact && (
                  <Button size="sm" variant="subtle" onClick={() => act(j.id, "cancel")} aria-label={`cancelar job ${j.id}`} icon={<X className="size-3.5" />} />
                )}
                {(j.status === "error" || j.status === "canceled") && !compact && (
                  <Button size="sm" variant="subtle" onClick={() => act(j.id, "retry")} aria-label={`repetir job ${j.id}`} icon={<RotateCcw className="size-3.5" />} />
                )}
              </div>
            </div>
            {(live || j.status === "done") && (
              <div className="mt-2 space-y-1">
                <Progress value={j.progress} active={j.status === "running"} label={`job ${j.id}`} />
                <p className="text-xs text-muted">{j.stage} · {Math.round(j.progress * 100)}% · tentativa {j.attempts}/{j.max_attempts}</p>
              </div>
            )}
            {j.error && <p className="mt-2 break-words text-xs text-bad">{j.error}</p>}
          </li>
        );
      })}
    </ol>
  );
}
