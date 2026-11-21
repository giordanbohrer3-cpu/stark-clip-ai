"use client";
import { ExternalLink, Flame, Link2, MessageCircle, Radio, Scissors, ShieldCheck, Trash2, Zap } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Empty, Field, Input, Note, Panel, Toggle } from "@/components/ui";
import { api, usePoll } from "@/lib/api";
import { ago, num } from "@/lib/format";
import { CLOUD } from "@/lib/mode";
import type { ChannelRow, HotVideo, LiveRow, LiveStatus, MomentRow } from "@/lib/types";

const MOMENT: Record<string, [string, string]> = {
  detected: ["detectado", "border-blue/40 text-blue"], clipping: ["cortando", "border-cyan/50 text-cyan"],
  processing: ["legendando", "border-cyan/50 text-cyan"], ready: ["pronto", "border-ok/40 text-ok"],
  failed: ["falhou", "border-bad/50 text-bad"], skipped: ["sem autorização", "border-muted/40 text-muted"],
};

function Tile({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="hud-panel p-4">
      <p className="hud-label">{label}</p>
      <p className={`mt-1 font-mono text-3xl font-bold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}

function Chip({ ok, label }: { ok: boolean; label: string }) {
  return <Badge className={ok ? "border-ok/40 text-ok" : "border-warn/40 text-warn"}>{label}</Badge>;
}

export default function RadarPage() {
  const st = usePoll<LiveStatus>("/live/status", 5000);
  const lives = usePoll<LiveRow[]>("/live/streams?limit=60", 15000);
  const moments = usePoll<MomentRow[]>("/live/moments?limit=40", 5000);
  const hot = usePoll<HotVideo[]>("/live/videos?limit=40", 60000);
  const chans = usePoll<ChannelRow[]>("/live/channels", 0);
  const [chan, setChan] = useState({ channel: "", evidence: "", confirm: false });
  const [camp, setCamp] = useState({ url: "", campaign: "", evidence: "", credit: "", confirm: false });
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const s = st.data;
  const grantId = (c: string) => chans.data?.find((g) => g.channel === c)?.id;

  const run = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ tone: "ok", text: ok });
      chans.reload();
      moments.reload();
    } catch (e) {
      setMsg({ tone: "bad", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };
  const connect = () => run("tw", async () => {
    const r = await api<{ url: string }>("/live/twitch/connect");
    window.location.href = r.url;
  });
  const clipNow = (id: number, channel: string) =>
    run(`c${id}`, () => api(`/live/channels/${id}/clip`, { method: "POST" }), `Cortando os últimos 30 s de ${channel}…`);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/clipzou-96.png" alt="" className="size-14 rounded-full shadow-[0_0_30px_-6px_var(--violet)]" />
          <div>
            <p className="hud-label flex items-center gap-2"><span className={`size-2 rounded-full ${s?.radar_running ? "animate-pulse bg-violet" : "bg-muted"}`} />
              Torre de controle · {s?.radar_running ? "ao vivo agora" : "radar desligado"}</p>
            <h1 className="text-2xl font-bold sm:text-3xl">Enquanto os outros assistem, <span className="text-violet">você já tem o corte.</span></h1>
          </div>
        </div>
        <Link href="/feed"><Button variant="primary" icon={<Flame className="size-4" />}>Cortes prontos ({s?.clips_ready ?? 0})</Button></Link>
      </header>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="lives no radar" value={num(s?.lives ?? 0)} tone="text-cyan" />
        {s?.keyless
          ? <Tile label="msgs/min no chat" value={num(s?.chat_rate ?? 0)} tone="text-warn" />
          : <Tile label="espectadores" value={num(s?.viewers ?? 0)} tone="text-warn" />}
        <Tile label="momentos hoje" value={num(s?.moments_today ?? 0)} tone="text-violet" />
        <Tile label="cortes prontos" value={num(s?.clips_ready ?? 0)} tone="text-ok" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip ok={!!s?.radar_running} label={s?.radar_running ? "radar rodando" : "radar parado"} />
        <Chip ok={s?.chat === "conectado"} label={`chat: ${s?.chat ?? "—"} (${s?.chat_channels ?? 0} canais)`} />
        <Chip ok={s?.twitch_configured ? s.twitch_api === "ok" : s?.chat === "conectado"}
          label={s?.twitch_configured ? `Twitch API: ${s.twitch_api}` : `Twitch: ${s?.watching ?? 0} famosos vigiados pelo chat`} />
        <Chip ok={!!s?.youtube_rss && !s.youtube_rss.startsWith("0/") && !s.youtube_rss.startsWith("erro") && s.youtube_rss !== "—"}
          label={`YouTube: ${s?.youtube_rss ?? "—"}${s?.youtube_configured ? ` · API ${s.youtube_api}` : ""}`} />
        {s?.twitch_connected && <Chip ok label={`login Twitch: ${s.twitch_login}`} />}
      </div>
      {s && CLOUD && !s.pc_online && (
        <Note tone="warn">
          PC desligado{s.pc_seen_at ? ` (visto ${ago(s.pc_seen_at)})` : ""}: mostrando o último radar. Cortes novos saem quando ele ligar.
        </Note>
      )}
      {s && !s.radar_running && !(CLOUD && !s.pc_online) && (
        <Note tone="warn">Radar desligado: abra o Clipzou no PC (ícone no menu). Ele liga sozinho e se atualiza sozinho.</Note>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel eyebrow={s?.keyless ? "famosos ao vivo (chat da Twitch)" : `${s?.game ?? "lives"} + top geral`} title="Bombando ao vivo" id="lives">
          {!lives.data?.length ? (
            <Empty title="Nenhum famoso ao vivo agora" icon={<Radio className="size-6" />}>
              Vigiando {s?.watching ?? 0} streamers famosos pelo chat. Quando um entra ao vivo e o chat esquenta, aparece aqui
              (atualiza a cada 30 s). Mude a lista em Config → Radar.
            </Empty>
          ) : (
            <ul className="grid grid-cols-2 gap-3 md:grid-cols-3">
              {lives.data.map((l) => (
                <li key={l.id} className="overflow-hidden rounded-xl border border-line bg-black/20">
                  <a href={l.url} target="_blank" rel="noreferrer" className="relative block aspect-video bg-black/40">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {l.thumbnail_url && <img src={l.thumbnail_url} alt="" className="size-full object-cover" loading="lazy" />}
                    <span className="absolute left-2 top-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-mono text-xs">
                      <span className="size-1.5 animate-pulse rounded-full bg-bad" />
                      {l.viewers > 0 ? num(l.viewers) : <><MessageCircle className="size-3" />{num(l.chat_rate)}/min</>}
                    </span>
                    <span className="absolute right-2 top-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[0.65rem] uppercase">{l.platform}</span>
                  </a>
                  <div className="space-y-1 p-2">
                    <p className="truncate text-sm font-semibold">@{l.display_name || l.channel}</p>
                    <p className="line-clamp-2 text-xs text-muted">{l.title}</p>
                    {l.authorized && grantId(l.channel) ? (
                      <Button size="sm" variant="primary" className="w-full" loading={busy === `c${grantId(l.channel)}`}
                        onClick={() => clipNow(grantId(l.channel)!, l.channel)} icon={<Scissors className="size-3.5" />}>Cortar agora</Button>
                    ) : (
                      <p className="text-[0.65rem] text-muted">só referência: sem autorização de corte</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel eyebrow="chat explodiu" title="Momentos agora" id="moments">
            {!moments.data?.length ? <Empty title="Sem picos ainda">O chat das lives é lido ao vivo; picos aparecem aqui.</Empty> : (
              <ul className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
                {moments.data.map((m) => {
                  const [label, cls] = MOMENT[m.status] ?? [m.status, ""];
                  return (
                    <li key={m.id} className="rounded-lg border border-line p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-semibold">@{m.channel}</span>
                        <span className={`rounded-full border px-2 py-0.5 font-mono text-[0.65rem] uppercase ${cls}`}>{label}</span>
                      </div>
                      <div className="mt-1 h-1 rounded bg-white/10"><div className="h-1 rounded bg-gradient-to-r from-violet to-cyan" style={{ width: `${m.score}%` }} /></div>
                      <p className="mt-1 text-xs text-muted">{ago(m.at)} · {Math.round(m.rate)} msgs/10 s (normal {m.baseline}) · {num(m.viewers)} vendo</p>
                      {m.tokens.length > 0 && <p className="mt-1 truncate font-mono text-xs text-cyan">{m.tokens.join(" · ")}</p>}
                      {m.error && <p className="mt-1 text-xs text-bad">{m.error}</p>}
                      <div className="mt-2 flex gap-2">
                        <a href={m.watch_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-muted hover:text-cyan"><ExternalLink className="size-3" />ver live</a>
                        {m.status === "ready" && <Link href="/feed" className="text-xs text-ok">ver corte →</Link>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>

          <Panel eyebrow="youtubers famosos · views por hora" title="Vídeos bombando" id="yt">
            {!hot.data?.length ? <p className="text-sm text-muted">Lendo os canais famosos… (até 1 min depois de ligar)</p> : (
              <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
                {hot.data.slice(0, 20).map((v, i) => (
                  <li key={v.id}>
                    <a href={v.url} target="_blank" rel="noreferrer" className="flex gap-3 rounded-lg p-1 hover:bg-white/5">
                      <span className="w-4 shrink-0 pt-1 text-right font-mono text-[0.65rem] text-muted">{i + 1}</span>
                      <span className="relative shrink-0">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={v.thumbnail_url} alt="" className="h-12 w-20 rounded object-cover" loading="lazy" />
                        {v.short && <span className="absolute bottom-0.5 right-0.5 rounded bg-black/80 px-1 text-[0.55rem] uppercase text-violet">short</span>}
                      </span>
                      <span className="min-w-0">
                        <span className="line-clamp-2 text-xs">{v.title}</span>
                        <span className="text-[0.65rem] text-muted">{v.channel} · <b className="text-warn">{num(v.views_per_hour)}/h</b> · {num(v.views)} views{v.published_at ? ` · ${ago(v.published_at)}` : ""}</span>
                      </span>
                    </a>
                  </li>
                ))}
                <li className="pt-1 text-[0.65rem] text-muted">Referência do que está bombando. Corte só de vídeo autorizado (pasta de entrada, campanha ou canal que te deu editor).</li>
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <Panel eyebrow="o que vira corte automático" title="Fontes autorizadas" id="sources" actions={
        s?.twitch_connected
          ? <Button size="sm" onClick={() => run("dc", () => api("/live/twitch", { method: "DELETE" }))}>Desconectar @{s.twitch_login}</Button>
          : s?.twitch_configured && !CLOUD
            ? <Button size="sm" variant="primary" onClick={connect} loading={busy === "tw"} icon={<Zap className="size-3.5" />}>Conectar Twitch</Button>
            : CLOUD ? <span className="text-xs text-muted">conectar a Twitch: pelo PC</span>
            : <span className="text-xs text-muted">corte automático de live: precisa da chave grátis da Twitch (opcional)</span>
      }>
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-sm text-muted">
              Streamers que te deram <b className="text-ink">editor</b> na Twitch ou estão num programa de cortes. Quando o chat explode,
              o Clipzou cria o clipe oficial, baixa, legenda e põe no feed.
            </p>
            <ul className="mb-3 space-y-2">
              {chans.data?.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                  <span className="flex items-center gap-2"><ShieldCheck className="size-4 text-ok" />@{g.channel}</span>
                  <span className="flex items-center gap-1">
                    <Button size="sm" variant="subtle" onClick={() => clipNow(g.id, g.channel)} loading={busy === `c${g.id}`} icon={<Scissors className="size-3.5" />}>Cortar agora</Button>
                    <Button size="sm" variant="subtle" aria-label="remover" onClick={() => run(`d${g.id}`, () => api(`/live/channels/${g.id}`, { method: "DELETE" }))} icon={<Trash2 className="size-3.5" />} />
                  </span>
                </li>
              ))}
            </ul>
            <div className="grid gap-2 sm:grid-cols-2">
              <Field label="Canal (Twitch)"><Input value={chan.channel} onChange={(e) => setChan({ ...chan, channel: e.target.value })} placeholder="gaules ou twitch.tv/gaules" /></Field>
              <Field label="Prova da autorização"><Input value={chan.evidence} onChange={(e) => setChan({ ...chan, evidence: e.target.value })} placeholder="link do programa / print" /></Field>
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <Toggle checked={chan.confirm} onChange={(v) => setChan({ ...chan, confirm: v })} label="Este canal autorizou meus cortes" />
              <Button size="sm" disabled={!chan.channel || !chan.confirm} loading={busy === "ch"}
                onClick={() => run("ch", () => api("/live/channels", { method: "POST", json: chan }).then(() => setChan({ channel: "", evidence: "", confirm: false })), "Canal autorizado.")}>Adicionar</Button>
            </div>
          </div>
          <div>
            <p className="mb-2 text-sm text-muted">
              Campanha de clipes (pagam por views)? Cole o link do vídeo que eles fornecem (Google Drive, Dropbox ou MP4).
              O Clipzou baixa, acha os 3 melhores momentos e entrega no feed.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <Field label="Link do vídeo" className="sm:col-span-2"><Input value={camp.url} onChange={(e) => setCamp({ ...camp, url: e.target.value })} placeholder="https://drive.google.com/file/d/…" /></Field>
              <Field label="Campanha"><Input value={camp.campaign} onChange={(e) => setCamp({ ...camp, campaign: e.target.value })} placeholder="nome da campanha" /></Field>
              <Field label="Crédito no vídeo"><Input value={camp.credit} onChange={(e) => setCamp({ ...camp, credit: e.target.value })} placeholder="twitch.tv/streamer" /></Field>
              <Field label="Link da campanha" className="sm:col-span-2"><Input value={camp.evidence} onChange={(e) => setCamp({ ...camp, evidence: e.target.value })} placeholder="https://… (prova da permissão)" /></Field>
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <Toggle checked={camp.confirm} onChange={(v) => setCamp({ ...camp, confirm: v })} label="A campanha permite cortar e postar" />
              <Button size="sm" variant="primary" disabled={!camp.url || camp.campaign.length < 2 || !camp.confirm} loading={busy === "cp"} icon={<Link2 className="size-3.5" />}
                onClick={() => run("cp", () => api("/live/campaigns", { method: "POST", json: { ...camp, layout: "stream" } }).then(() => setCamp({ url: "", campaign: "", evidence: "", credit: "", confirm: false })), "Baixando e cortando. Os cortes aparecem no feed.")}>Gerar cortes</Button>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}
