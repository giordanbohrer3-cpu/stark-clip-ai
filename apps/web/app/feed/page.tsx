"use client";
import { CalendarClock, ClipboardCopy, Download, Flame, FolderInput, FolderOpen, Loader2, PenLine, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Empty, Field, Input, Note, Panel, Select, Toggle } from "@/components/ui";
import { api, fileUrl, usePoll } from "@/lib/api";
import { ago } from "@/lib/format";
import { CLOUD } from "@/lib/mode";
import type { FeedItem, InboxStatus, QueueItem } from "@/lib/types";

const ORIGIN: Record<string, string> = {
  twitch_clip: "Twitch ao vivo", campaign: "campanha", upload: "seu vídeo", inbox: "pasta de entrada",
};
const RIGHTS: [string, string][] = [
  ["own", "São vídeos meus (meu canal / minhas lives)"],
  ["licensed", "Campanha ou licença que permite cortar"],
  ["creator_permission", "O criador me autorizou"],
];

function InboxCard() {
  const box = usePoll<InboxStatus>("/inbox", 8000);
  const [decl, setDecl] = useState({ rights_type: "own", holder: "", confirm: false });
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const b = box.data;

  const run = async (key: string, fn: () => Promise<{ imported?: number; status?: string } | unknown>) => {
    setBusy(key);
    setMsg(null);
    try {
      const r = (await fn()) as { imported?: number; status?: string } | undefined;
      if (r && typeof r.imported === "number") {
        setMsg({ tone: "ok", text: r.imported ? `${r.imported} vídeo(s) entrando na produção.` : r.status === "já buscando" ? "Já estou buscando…" : "Nada novo na pasta." });
      }
      box.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  return (
    <Panel eyebrow="automático" title="Pasta de entrada" id="inbox" actions={b?.confirmed && (
      <span className="flex gap-1.5">
        {!CLOUD && <Button size="sm" variant="subtle" loading={busy === "open"} icon={<FolderOpen className="size-3.5" />}
          onClick={() => run("open", () => api("/inbox/open", { method: "POST" }))}>Abrir pasta</Button>}
        <Button size="sm" variant="primary" loading={busy === "scan"} icon={<RefreshCw className="size-3.5" />}
          onClick={() => run("scan", () => api("/inbox/scan", { method: "POST" }))}>Buscar agora</Button>
      </span>
    )}>
      {msg && <div className="mb-3"><Note tone={msg.tone}>{msg.text}</Note></div>}
      <p className="text-sm text-muted">
        Jogue vídeos (MP4, MOV, MKV, WEBM) em <code className="break-all text-cyan">{b?.path ?? "~/Clipzou/Entrada"}</code>.
        O Clipzou acha os 3 melhores momentos de cada um, legenda, deixa em 9:16 e coloca aqui embaixo. Sozinho.
      </p>
      {b && !b.confirmed ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Esses vídeos são">
            <Select value={decl.rights_type} onChange={(e) => setDecl({ ...decl, rights_type: e.target.value })}>
              {RIGHTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Dono / campanha (opcional)"><Input value={decl.holder} onChange={(e) => setDecl({ ...decl, holder: e.target.value })} placeholder="ex.: meu canal, Campanha X" /></Field>
          <Button variant="primary" disabled={!decl.confirm} loading={busy === "ok"} icon={<FolderInput className="size-4" />}
            onClick={() => run("ok", () => api("/inbox/confirm", { method: "POST", json: decl }))}>Ativar pasta</Button>
          <div className="sm:col-span-3">
            <Toggle checked={decl.confirm} onChange={(v) => setDecl({ ...decl, confirm: v })}
              label="Declaro que tenho autorização para cortar e postar os vídeos que coloco nesta pasta" />
          </div>
        </div>
      ) : b ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <Badge className="border-ok/40 text-ok">ativa · {b.imported} importado(s)</Badge>
          {b.pending.length > 0 && <Badge className="border-warn/40 text-warn">{b.pending.length} na pasta aguardando</Badge>}
          {b.pending.slice(0, 4).map((p) => (
            <span key={p.name} className="truncate text-muted">{p.copying ? "copiando: " : ""}{p.name} ({p.size_mb} MB)</span>
          ))}
          {b.errors.slice(-2).map((e) => <span key={e.title} className="text-bad">{e.title}: {e.error}</span>)}
        </div>
      ) : null}
    </Panel>
  );
}

function Queue() {
  const q = usePoll<QueueItem[]>("/feed/queue", 4000);
  if (!q.data?.length) return null;
  return (
    <div className="hud-panel space-y-2 p-4">
      <p className="hud-label flex items-center gap-2"><Loader2 className="size-3.5 animate-spin text-cyan" />produzindo agora ({q.data.length})</p>
      <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {q.data.slice(0, 9).map((j) => (
          <li key={j.id} className="rounded-lg border border-line p-2.5">
            <p className="truncate text-sm font-semibold">{j.title || "vídeo"}</p>
            <p className="truncate text-[0.7rem] text-muted">{j.status === "queued" ? "na fila · " : ""}{j.stage || j.label}</p>
            <div className="mt-1.5 h-1 rounded bg-white/10">
              <div className="h-1 rounded bg-gradient-to-r from-violet to-cyan transition-[width]" style={{ width: `${Math.max(3, Math.round(j.progress * 100))}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

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
      <InboxCard />
      <Queue />
      {feed.error && <Note tone="bad">{feed.error}</Note>}
      {!feed.data?.length ? (
        <Empty title="Nenhum corte pronto ainda" icon={<Flame className="size-6" />}>
          Ative a pasta de entrada acima e jogue um vídeo nela. Também vale: link de campanha no Radar ou canal que te deu editor na Twitch.
        </Empty>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {feed.data.map((it) => (
            <li key={it.clip.id} className="overflow-hidden rounded-2xl border border-line bg-black/30">
              <div className="relative aspect-[9/16] bg-black">
                {!CLOUD || it.cloud ? (
                  <video src={fileUrl(it.clip.id, "output")} poster={fileUrl(it.clip.id, "cover")} controls playsInline preload="none"
                    className="size-full object-cover" />
                ) : <div className="grid size-full place-items-center p-4 text-center text-xs text-muted">{it.title}</div>}
                <span className="pointer-events-none absolute left-2 top-2"><Badge className="border-violet/50 bg-black/60 text-violet">{ORIGIN[it.origin] ?? it.origin}</Badge></span>
              </div>
              <div className="space-y-2 p-2.5">
                <p className="line-clamp-2 text-sm font-semibold">{it.title}</p>
                <p className="text-[0.7rem] text-muted">{it.channel ? `@${it.channel} · ` : ""}{it.clip.duration_s.toFixed(0)} s · {ago(it.clip.updated_at)}</p>
                {CLOUD && !it.cloud && <p className="text-[0.7rem] text-warn">{it.only_pc || "subindo para a nuvem…"}</p>}
                <div className="grid grid-cols-2 gap-1.5">
                  {!CLOUD || it.cloud ? (
                    <a href={fileUrl(it.clip.id, "output", true)} className="inline-flex h-8 items-center justify-center gap-1 rounded-[10px] bg-gradient-to-r from-violet to-cyan text-xs font-semibold text-[#12041a]">
                      <Download className="size-3.5" />Baixar
                    </a>
                  ) : <span className="inline-flex h-8 items-center justify-center rounded-[10px] border border-line text-xs text-muted">só no PC</span>}
                  <Button size="sm" onClick={() => copy(it)} icon={<ClipboardCopy className="size-3.5" />}>{copied === it.clip.id ? "Copiado" : "Legenda"}</Button>
                  {!CLOUD && <Link href={`/studio/${it.clip.id}`}><Button size="sm" variant="subtle" className="w-full" icon={<PenLine className="size-3.5" />}>Editar</Button></Link>}
                  {!CLOUD && <Link href={`/publish?clip=${it.clip.id}`}><Button size="sm" variant="subtle" className="w-full" icon={<CalendarClock className="size-3.5" />}>Agendar</Button></Link>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
