"use client";
import { CalendarClock, Check, ClipboardCopy, Download, ExternalLink, Plus, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Badge, Button, Empty, Field, Input, Note, Panel, Select, Textarea } from "@/components/ui";
import { api, fileUrl, usePoll } from "@/lib/api";
import { when } from "@/lib/format";
import type { Account, Clip, Platform, Post } from "@/lib/types";

const PLAT: Record<Platform, string> = { tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook", youtube: "YouTube Shorts" };
const bioFor = (niche: string) =>
  `Cortes diários de ${niche || "conteúdo que vale a pena"} 🔥 Os melhores momentos, legendados. Novos vídeos todo dia.`;

export default function PublishPage() {
  return (
    <Suspense fallback={<p className="text-muted">carregando…</p>}>
      <Publish />
    </Suspense>
  );
}

function Publish() {
  const params = useSearchParams();
  const accounts = usePoll<Account[]>("/accounts", 0);
  const clips = usePoll<Clip[]>("/clips?state=ready", 8000);
  const posts = usePoll<Post[]>("/posts", 4000);
  const [acc, setAcc] = useState({ platform: "tiktok" as Platform, handle: "", niche: "", bio: "", niche_hashtags: "", daily_cap: 5 });
  const [selClips, setSelClips] = useState<number[]>(() => (params.get("clip") ? [Number(params.get("clip"))] : []));
  const [selAcc, setSelAcc] = useState<number[]>([]);
  const [mode, setMode] = useState<"assisted" | "export">("assisted");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [pubUrl, setPubUrl] = useState<Record<number, string>>({});

  const run = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ tone: "ok", text: ok });
      posts.reload();
      accounts.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const addAccount = () => run("acc", () => api("/accounts", { method: "POST", json: {
    ...acc, handle: acc.handle.startsWith("@") ? acc.handle : `@${acc.handle}`, bio: acc.bio || bioFor(acc.niche),
    niche_hashtags: acc.niche_hashtags.split(/[\s,]+/).filter(Boolean),
  } }).then(() => setAcc({ ...acc, handle: "", bio: "" })), "Perfil cadastrado. Crie/verifique a conta na própria plataforma.");

  const schedule = () => run("bulk", async () => {
    const r = await api<Post[]>("/posts/bulk", { method: "POST", json: { edited_clip_ids: selClips, account_ids: selAcc, mode } });
    setMsg({ tone: "ok", text: `${r.length} publicação(ões) agendada(s) respeitando limite diário e intervalo. Aprove para liberar.` });
    setSelClips([]);
  });

  const patch = (p: Post, json: Record<string, unknown>, key: string) => run(key, () => api(`/posts/${p.id}`, { method: "PATCH", json }));

  const grouped = (posts.data ?? []).filter((p) => p.status !== "canceled").reduce<Record<string, Post[]>>((g, p) => {
    const day = new Date(/Z|[+-]\d\d:\d\d$/.test(p.scheduled_at) ? p.scheduled_at : `${p.scheduled_at}Z`).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
    (g[day] ??= []).push(p);
    return g;
  }, {});

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Publicação</h1>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      <Note tone="info">
        Sem app aprovado (TikTok audit / Meta App Review) a postagem direta por API não é permitida. Por isso o padrão é o
        <b> modo assistido</b>: no horário, o kit fica pronto (vídeo + legenda + link de upload) e você publica no navegador logado.
      </Note>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.3fr]">
        <Panel eyebrow="contas" title="Perfis" id="acc">
          <ul className="space-y-2">
            {accounts.data?.map((a) => (
              <li key={a.id} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={selAcc.includes(a.id)} onChange={(e) => setSelAcc((s) => e.target.checked ? [...s, a.id] : s.filter((x) => x !== a.id))} />
                    <span className="font-medium">{a.handle}</span><span className="text-xs text-muted">{PLAT[a.platform]}</span>
                  </label>
                  <div className="flex items-center gap-2"><Badge status={a.status} /><span className="font-mono text-xs text-muted">{a.daily_cap}/dia</span></div>
                </div>
                {a.bio && <p className="mt-1 text-xs text-muted">{a.bio}</p>}
              </li>
            ))}
            {!accounts.data?.length && <Empty title="Nenhum perfil">Cadastre os perfis que você já criou nas plataformas.</Empty>}
          </ul>
          <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
            <Field label="Plataforma"><Select value={acc.platform} onChange={(e) => setAcc({ ...acc, platform: e.target.value as Platform })}>
              {Object.entries(PLAT).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            <Field label="@handle"><Input value={acc.handle} onChange={(e) => setAcc({ ...acc, handle: e.target.value })} placeholder="@seu.perfil" /></Field>
            <Field label="Nicho"><Input value={acc.niche} onChange={(e) => setAcc({ ...acc, niche: e.target.value })} placeholder="finanças" /></Field>
            <Field label="Limite diário" hint="1–10; o sistema reduz sozinho após falhas">
              <Input type="number" min={1} max={10} value={acc.daily_cap} onChange={(e) => setAcc({ ...acc, daily_cap: +e.target.value })} /></Field>
            <Field label="Hashtags do nicho" className="sm:col-span-2"><Input value={acc.niche_hashtags} onChange={(e) => setAcc({ ...acc, niche_hashtags: e.target.value })} placeholder="#financas #investimentos" /></Field>
            <Field label="Bio" className="sm:col-span-2" hint="vazio = sugestão automática pelo nicho">
              <Textarea value={acc.bio} onChange={(e) => setAcc({ ...acc, bio: e.target.value })} placeholder={bioFor(acc.niche)} className="min-h-16" /></Field>
          </div>
          <div className="mt-3 flex justify-end"><Button onClick={addAccount} disabled={acc.handle.length < 2} loading={busy === "acc"} icon={<Plus className="size-4" />}>Cadastrar perfil</Button></div>
        </Panel>

        <Panel eyebrow="distribuição" title="Agendar cortes prontos" id="sch">
          {!clips.data?.length ? <Empty title="Nenhum corte pronto">Faça o render final no estúdio.</Empty> : (
            <ul className="grid max-h-72 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
              {clips.data.map((c) => (
                <li key={c.id}>
                  <label className={`block cursor-pointer overflow-hidden rounded-lg border ${selClips.includes(c.id) ? "border-cyan" : "border-line"}`}>
                    <input type="checkbox" className="sr-only" checked={selClips.includes(c.id)} onChange={(e) => setSelClips((s) => e.target.checked ? [...s, c.id] : s.filter((x) => x !== c.id))} />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={fileUrl(c.id, "cover")} alt="" className="aspect-[9/16] w-full object-cover" loading="lazy" />
                    <p className="line-clamp-2 p-1.5 text-[0.68rem]">{c.copy_text?.title || `#${c.id}`}</p>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <Field label="Modo"><Select value={mode} onChange={(e) => setMode(e.target.value as "assisted" | "export")} className="w-56">
              <option value="assisted">assistido (kit no horário)</option><option value="export">exportar pasta</option>
              <option value="api" disabled>API oficial (requer OAuth aprovado)</option></Select></Field>
            <Button variant="primary" onClick={schedule} disabled={!selClips.length || !selAcc.length} loading={busy === "bulk"} icon={<CalendarClock className="size-4" />}>
              Agendar {selClips.length}×{selAcc.length}
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted">Horários calculados pela cadência (intervalo mínimo, horário de silêncio, limite diário). Duplicados são bloqueados.</p>
        </Panel>
      </div>

      <Panel eyebrow="agenda" title="Fila de publicações" id="queue">
        {!Object.keys(grouped).length ? <Empty title="Agenda vazia" /> : (
          <div className="space-y-5">
            {Object.entries(grouped).map(([day, list]) => (
              <section key={day}>
                <h3 className="hud-label mb-2">{day}</h3>
                <ul className="space-y-2">
                  {list.map((p) => (
                    <li key={p.id} className="rounded-xl border border-line bg-black/20 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{p.clip_title || `corte #${p.edited_clip_id}`}</p>
                          <p className="text-xs text-muted">{when(p.scheduled_at)} · {PLAT[p.platform]} {p.account_handle} · {p.mode}</p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge status={p.status} />
                          {!p.approved && p.status === "scheduled" && <Button size="sm" variant="primary" onClick={() => patch(p, { approved: true }, `ap${p.id}`)} loading={busy === `ap${p.id}`} icon={<Check className="size-3.5" />}>Aprovar</Button>}
                          {p.approved && p.status === "scheduled" && <Badge className="border-ok/40 text-ok">aprovado</Badge>}
                          {["scheduled", "ready_manual", "exported", "blocked"].includes(p.status) && (
                            <Button size="sm" variant="subtle" onClick={() => patch(p, { status: "canceled" }, `cx${p.id}`)} aria-label="cancelar" icon={<X className="size-3.5" />} />
                          )}
                        </div>
                      </div>
                      {p.error && <p className="mt-2 text-xs text-bad">{p.error}</p>}
                      {(p.status === "ready_manual" || p.status === "exported") && (
                        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                          <a href={fileUrl(p.edited_clip_id, "output", true)} className="inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-line px-3 text-xs hover:text-cyan"><Download className="size-3.5" />Vídeo</a>
                          <Button size="sm" onClick={() => navigator.clipboard.writeText(p.caption)} icon={<ClipboardCopy className="size-3.5" />}>Copiar legenda</Button>
                          {p.upload_url && <a href={p.upload_url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-cyan/40 px-3 text-xs text-cyan"><ExternalLink className="size-3.5" />Abrir {PLAT[p.platform]}</a>}
                          <Input value={pubUrl[p.id] ?? ""} onChange={(e) => setPubUrl({ ...pubUrl, [p.id]: e.target.value })} placeholder="link do post publicado" className="h-8 max-w-64 text-xs" aria-label="link publicado" />
                          <Button size="sm" onClick={() => patch(p, { status: "published", external_url: pubUrl[p.id] || null }, `pb${p.id}`)} loading={busy === `pb${p.id}`}>Marcar publicado</Button>
                        </div>
                      )}
                      {p.status === "published" && p.external_url && <a href={p.external_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-cyan underline">ver publicação</a>}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
