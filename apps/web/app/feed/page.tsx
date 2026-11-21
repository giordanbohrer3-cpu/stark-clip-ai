"use client";
import { CalendarClock, ClipboardCopy, Download, Flame, PenLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Empty, Note } from "@/components/ui";
import { fileUrl, usePoll } from "@/lib/api";
import { ago } from "@/lib/format";
import type { FeedItem } from "@/lib/types";

const ORIGIN: Record<string, string> = { twitch_clip: "Twitch ao vivo", campaign: "campanha", upload: "seu vídeo" };

export default function FeedPage() {
  const feed = usePoll<FeedItem[]>("/feed?limit=90", 5000);
  const [copied, setCopied] = useState<number | null>(null);

  const copy = async (it: FeedItem) => {
    const c = it.clip.copy_text?.captions;
    const text = c?.tiktok || c?.instagram || it.title;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(it.clip.id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard bloqueado: usuário copia no estúdio */
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <p className="hud-label flex items-center gap-2"><Flame className="size-3.5 text-violet" />cortes reais feitos pela máquina</p>
        <h1 className="mt-1 text-2xl font-bold">Prontos para baixar e postar</h1>
        <p className="text-sm text-muted">9:16 com gancho, legenda animada e crédito do canal. Escolha, baixe, poste.</p>
      </header>
      {feed.error && <Note tone="bad">{feed.error}</Note>}
      {!feed.data?.length ? (
        <Empty title="Nenhum corte pronto ainda" icon={<Flame className="size-6" />}>
          Autorize canais no Radar (corte automático quando o chat explode), cole links de campanhas ou envie seus vídeos.
        </Empty>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {feed.data.map((it) => (
            <li key={it.clip.id} className="overflow-hidden rounded-2xl border border-line bg-black/30">
              <div className="relative aspect-[9/16] bg-black">
                <video src={fileUrl(it.clip.id, "output")} poster={fileUrl(it.clip.id, "cover")} controls playsInline preload="none"
                  className="size-full object-cover" />
                <span className="pointer-events-none absolute left-2 top-2"><Badge className="border-violet/50 bg-black/60 text-violet">{ORIGIN[it.origin] ?? it.origin}</Badge></span>
              </div>
              <div className="space-y-2 p-2.5">
                <p className="line-clamp-2 text-sm font-semibold">{it.title}</p>
                <p className="text-[0.7rem] text-muted">{it.channel ? `@${it.channel} · ` : ""}{it.clip.duration_s.toFixed(0)} s · {ago(it.clip.updated_at)}</p>
                <div className="grid grid-cols-2 gap-1.5">
                  <a href={fileUrl(it.clip.id, "output", true)} className="inline-flex h-8 items-center justify-center gap-1 rounded-[10px] bg-gradient-to-r from-violet to-cyan text-xs font-semibold text-[#12041a]">
                    <Download className="size-3.5" />Baixar
                  </a>
                  <Button size="sm" onClick={() => copy(it)} icon={<ClipboardCopy className="size-3.5" />}>{copied === it.clip.id ? "Copiado" : "Legenda"}</Button>
                  <Link href={`/studio/${it.clip.id}`}><Button size="sm" variant="subtle" className="w-full" icon={<PenLine className="size-3.5" />}>Editar</Button></Link>
                  <Link href={`/publish?clip=${it.clip.id}`}><Button size="sm" variant="subtle" className="w-full" icon={<CalendarClock className="size-3.5" />}>Agendar</Button></Link>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
