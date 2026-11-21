"use client";
import { Clapperboard } from "lucide-react";
import Link from "next/link";
import { Badge, Empty, Note, Panel } from "@/components/ui";
import { fileUrl, usePoll } from "@/lib/api";
import { ago } from "@/lib/format";
import type { Clip } from "@/lib/types";

export default function StudioList() {
  const clips = usePoll<Clip[]>("/clips", 4000);
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Estúdio</h1>
      {clips.error && <Note tone="bad">{clips.error}</Note>}
      <Panel eyebrow="cortes em edição" title={`${clips.data?.length ?? 0} cortes`} id="clips">
        {!clips.data?.length ? (
          <Empty title="Nenhum corte no estúdio" icon={<Clapperboard className="size-6" />}>
            Abra um vídeo analisado e clique em “Editar no estúdio”.
          </Empty>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {clips.data.map((c) => (
              <li key={c.id}>
                <Link href={`/studio/${c.id}`} className="group block overflow-hidden rounded-xl border border-line bg-black/20 hover:border-cyan/50">
                  <div className="aspect-[9/16] bg-black/50">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {c.files.includes("cover") && <img src={fileUrl(c.id, "cover")} alt="" className="size-full object-cover" loading="lazy" />}
                  </div>
                  <div className="space-y-1 p-2">
                    <p className="line-clamp-2 text-xs">{c.copy_text?.title || `Corte #${c.id}`}</p>
                    <div className="flex items-center justify-between"><Badge status={c.status} /><span className="text-[0.65rem] text-muted">{ago(c.updated_at)}</span></div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
