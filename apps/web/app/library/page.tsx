"use client";
import { Link2, Search, Star, UploadCloud, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { Badge, Button, Empty, Field, Input, Note, Panel, Progress, Select, Toggle } from "@/components/ui";
import { api, BASE, uploadWithProgress, usePoll } from "@/lib/api";
import { clock, mb, num } from "@/lib/format";
import type { SettingsResp, VideoRow, YtResult } from "@/lib/types";

const RIGHTS = [
  ["own", "Conteúdo próprio (eu gravei / meu canal)"],
  ["creator_permission", "Permissão do criador (programa de cortes / contrato)"],
  ["licensed", "Licenciado (contrato/banco de mídia)"],
  ["cc_by", "Creative Commons BY (com atribuição)"],
  ["public_domain", "Domínio público"],
] as const;

export default function Library() {
  const videos = usePoll<VideoRow[]>("/videos", 4000);
  const cfg = usePoll<SettingsResp>("/settings", 0);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ title: "", niche: "", rights_type: "own", holder: "", evidence: "", allows_commercial: false, confirm: false, auto: true });
  const [refId, setRefId] = useState<number | null>(null);
  const [prog, setProg] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [url, setUrl] = useState("");
  const [q, setQ] = useState("");
  const [results, setResults] = useState<YtResult[] | null>(null);
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState("");
  const [sel, setSel] = useState<number[]>([]);
  const ytKey = cfg.data?.env.youtube_api;

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const upload = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(form).forEach(([k, v]) => k !== "auto" && fd.append(k, String(v)));
    if (refId) fd.append("reference_id", String(refId));
    setMsg(null);
    setProg(0);
    try {
      const v = (await uploadWithProgress("/videos/upload", fd, setProg)) as VideoRow;
      if (form.auto) await api(`/videos/${v.id}/process`, { method: "POST", json: {} });
      setMsg({ tone: "ok", text: `“${v.title}” enviado${form.auto ? " e na fila de análise" : ""}.` });
      setFile(null);
      setRefId(null);
      videos.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setProg(null);
    }
  };

  const addRef = async (u: string) => {
    setBusy(u);
    try {
      await api("/videos/reference", { method: "POST", json: { url: u, niche: form.niche } });
      setMsg({ tone: "warn", text: "Referência salva. Para cortar, envie o arquivo original com registro de direitos." });
      videos.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const search = async () => {
    setBusy("search");
    try {
      setResults(await api<YtResult[]>(`/youtube/search?q=${encodeURIComponent(q)}&order=viewCount&days=30`));
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const process = async (ids: number[]) => {
    for (const id of ids) {
      try {
        await api(`/videos/${id}/process`, { method: "POST", json: {} });
      } catch (e) {
        setMsg({ tone: "bad", text: `#${id}: ${(e as Error).message}` });
      }
    }
    setSel([]);
    videos.reload();
  };

  const fav = async (v: VideoRow) => {
    await api(`/videos/${v.id}`, { method: "PATCH", json: { favorite: !v.favorite } });
    videos.reload();
  };

  const list = (videos.data ?? []).filter((v) =>
    filter === "fav" ? v.favorite : filter ? v.status === filter : true);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Vídeos-fonte</h1>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel eyebrow="entrada autorizada" title={refId ? `Enviar arquivo para referência #${refId}` : "Upload do original"} id="up">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0] ?? null); }}
            className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-cyan/30 bg-cyan/5 p-6 text-center">
            <UploadCloud className="size-8 text-cyan" aria-hidden />
            <p className="text-sm">{file ? `${file.name} · ${mb(file.size)}` : "Arraste o vídeo aqui (MP4, MOV, MKV, WEBM)"}</p>
            <input ref={fileRef} type="file" accept="video/*" className="sr-only" id="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button size="sm" onClick={() => fileRef.current?.click()}>Escolher arquivo</Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Título"><Input value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="opcional" /></Field>
            <Field label="Nicho"><Input value={form.niche} onChange={(e) => set("niche", e.target.value)} placeholder="ex.: finanças" /></Field>
            <Field label="Base legal do uso" className="sm:col-span-2">
              <Select value={form.rights_type} onChange={(e) => set("rights_type", e.target.value)}>
                {RIGHTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label="Titular dos direitos"><Input value={form.holder} onChange={(e) => set("holder", e.target.value)} placeholder="nome/canal" required /></Field>
            <Field label="Evidência"><Input value={form.evidence} onChange={(e) => set("evidence", e.target.value)} placeholder="link do contrato, e-mail, licença…" /></Field>
          </div>
          <div className="mt-4 space-y-3">
            <Toggle checked={form.allows_commercial} onChange={(v) => set("allows_commercial", v)} label="Uso comercial/monetizado permitido" />
            <Toggle checked={form.auto} onChange={(v) => set("auto", v)} label="Analisar automaticamente após envio" />
            <Toggle checked={form.confirm} onChange={(v) => set("confirm", v)} label="Declaro que tenho direito de editar e publicar este material"
              hint="Registrado na auditoria. Link do YouTube não é autorização." />
          </div>
          {prog !== null && <div className="mt-4"><Progress value={prog} active label="envio" /></div>}
          <div className="mt-4 flex justify-end gap-2">
            {refId && <Button variant="subtle" onClick={() => setRefId(null)}>cancelar vínculo</Button>}
            <Button variant="primary" onClick={upload} loading={prog !== null}
              disabled={!file || !form.confirm || form.holder.trim().length < 2} icon={<UploadCloud className="size-4" />}>
              Enviar
            </Button>
          </div>
        </Panel>

        <Panel eyebrow="YouTube" title="Referências e pesquisa" id="yt">
          <Note tone="info">
            O app não baixa vídeos do YouTube. Use referências para planejar; para editar, envie o arquivo original
            (seu canal: YouTube Studio → Download) ou material com permissão do criador.
          </Note>
          <div className="mt-4 flex gap-2">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtube.com/watch?v=…" aria-label="URL do YouTube" />
            <Button onClick={() => addRef(url)} loading={busy === url} disabled={!url} icon={<Link2 className="size-4" />}>Adicionar</Button>
          </div>
          <div className="mt-3 flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={ytKey ? "buscar: tema, canal…" : "defina STARK_YOUTUBE_API_KEY para buscar"}
              disabled={!ytKey} aria-label="Buscar no YouTube" onKeyDown={(e) => e.key === "Enter" && q && search()} />
            <Button onClick={search} disabled={!ytKey || !q} loading={busy === "search"} icon={<Search className="size-4" />}>Buscar</Button>
          </div>
          {results && (
            <ul className="mt-4 grid max-h-[420px] gap-2 overflow-y-auto pr-1">
              {results.map((r) => (
                <li key={r.youtube_id} className="flex gap-3 rounded-lg border border-line p-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={r.thumbnail_url} alt="" className="h-16 w-28 shrink-0 rounded object-cover" loading="lazy" />
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm">{r.title}</p>
                    <p className="text-xs text-muted">{r.channel} · {clock(r.duration_s)} · {num(r.views)} views · {r.license === "creativeCommon" ? "CC" : "padrão YouTube"}</p>
                  </div>
                  <Button size="sm" onClick={() => addRef(r.url)} loading={busy === r.url}>Salvar</Button>
                </li>
              ))}
              {!results.length && <li className="text-sm text-muted">Nada encontrado.</li>}
            </ul>
          )}
        </Panel>
      </div>

      <Panel eyebrow="acervo" title="Biblioteca" id="lib" actions={
        <>
          <Select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filtrar" className="h-8 w-40 text-xs">
            <option value="">todos</option><option value="fav">favoritos</option><option value="reference">referências</option>
            <option value="uploaded">enviados</option><option value="ready">com cortes</option><option value="error">com erro</option>
          </Select>
          <Button size="sm" variant="primary" disabled={!sel.length} onClick={() => process(sel)} icon={<Wand2 className="size-3.5" />}>
            Processar lote ({sel.length})
          </Button>
        </>
      }>
        {!list.length ? (
          <Empty title="Nenhum vídeo" icon={<UploadCloud className="size-6" />}>Envie um original autorizado para gerar os 3 cortes.</Empty>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {list.map((v) => (
              <li key={v.id} className="overflow-hidden rounded-xl border border-line bg-black/20">
                <div className="relative aspect-video bg-black/40">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {(v.has_file || v.thumbnail_url) && <img src={v.has_file ? `${BASE}/videos/${v.id}/thumb` : v.thumbnail_url!} alt="" className="size-full object-cover" loading="lazy" />}
                  <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 font-mono text-xs">{clock(v.duration_s)}</span>
                  <button onClick={() => fav(v)} aria-label={v.favorite ? "remover dos favoritos" : "favoritar"} aria-pressed={v.favorite}
                    className="absolute right-2 top-2 rounded-full bg-black/60 p-1.5"><Star className={`size-4 ${v.favorite ? "fill-warn text-warn" : "text-muted"}`} /></button>
                  {v.has_file && v.rights_ok && (
                    <label className="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/60 px-2 py-1 text-xs">
                      <input type="checkbox" checked={sel.includes(v.id)} onChange={(e) => setSel((s) => e.target.checked ? [...s, v.id] : s.filter((x) => x !== v.id))} />
                      lote
                    </label>
                  )}
                </div>
                <div className="space-y-2 p-3">
                  <p className="line-clamp-2 text-sm font-medium">{v.title}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge status={v.status} />
                    {v.rights_ok ? <Badge className="border-ok/40 text-ok">direitos ok</Badge> : <Badge className="border-warn/40 text-warn">sem autorização</Badge>}
                    {v.niche && <Badge>{v.niche}</Badge>}
                  </div>
                  {v.error && <p className="text-xs text-bad">{v.error}</p>}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {v.has_file ? (
                      <>
                        <Link href={`/videos/${v.id}`}><Button size="sm" variant="primary">Abrir</Button></Link>
                        {v.rights_ok && v.status !== "analyzing" && v.status !== "queued" && (
                          <Button size="sm" onClick={() => process([v.id])}>{v.status === "ready" ? "Reprocessar" : "Processar"}</Button>
                        )}
                      </>
                    ) : (
                      <Button size="sm" onClick={() => { setRefId(v.id); setForm((f) => ({ ...f, title: v.title, holder: v.channel ?? "" })); document.getElementById("up")?.scrollIntoView({ behavior: "smooth" }); }}>
                        Enviar original
                      </Button>
                    )}
                    {v.url && <a href={v.url} target="_blank" rel="noreferrer" className="text-xs text-muted underline-offset-2 hover:underline">ver no YouTube</a>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
