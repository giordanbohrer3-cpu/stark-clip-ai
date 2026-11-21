/* App online (Vercel): lê o radar/feed que o PC sobe para o Supabase e manda pedidos ao PC.
   A chave secreta fica só no servidor. Cache curto + "só o que mudou" para gastar pouco da cota grátis. */
import { cookieFrom, validSession } from "./session";

const BASE = (process.env.SUPABASE_URL ?? "https://pyxbnpplflraaztljgos.supabase.co").replace(/\/$/, "");
const KEY = process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const TTL_MS = 8000;
const PC_ONLINE_S = 90;
const EGRESS_CAP = Number(process.env.CLIPZOU_EGRESS_CAP_MB ?? 2048) * 1024 * 1024; // protege seus outros apps
const ALLOWED: [string, RegExp][] = [
  ["POST", /^\/inbox\/scan$/], ["POST", /^\/inbox\/confirm$/], ["DELETE", /^\/inbox\/confirm$/],
  ["POST", /^\/live\/channels$/], ["DELETE", /^\/live\/channels\/\d+$/], ["POST", /^\/live\/channels\/\d+\/clip$/],
  ["POST", /^\/live\/campaigns$/], ["POST", /^\/system\/update$/], ["PATCH", /^\/settings$/],
  ["POST", /^\/agent\/(pause|resume)$/],
];

type Entry = { data: unknown; at: string };
type FeedRow = { clip: { id: number }; cloud: { output: string; cover: string | null; size: number } | null };

class CloudError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { apikey: KEY, "content-type": "application/json" };
  if (!KEY.startsWith("sb_")) h.authorization = `Bearer ${KEY}`; // chave antiga (JWT)
  return h;
}

async function rpc<T>(fn: string, args: Record<string, unknown> = {}): Promise<T> {
  const r = await fetch(`${BASE}/rest/v1/rpc/${fn}`, { method: "POST", headers: headers(), body: JSON.stringify(args), cache: "no-store" });
  if (!r.ok) throw new CloudError(r.status, `nuvem respondeu ${r.status}`);
  const t = await r.text();
  return (t ? JSON.parse(t) : null) as T;
}

/* ---------------------------------------------------------------- radar e feed (cache por instância) */
const cache = { data: new Map<string, Entry>(), hashes: {} as Record<string, string>, fetched: 0, beat: null as string | null };
let inflight: Promise<void> | null = null;

async function refresh(force = false): Promise<void> {
  if (!force && Date.now() - cache.fetched < TTL_MS) return;
  inflight ??= (async () => {
    const rev = await rpc<{ data: { beat: string; hashes: Record<string, string> }; at: string } | null>("clipzou_get", { p_key: "rev" });
    if (rev) {
      cache.beat = rev.at;
      const changed = Object.entries(rev.data.hashes ?? {}).filter(([k, h]) => cache.hashes[k] !== h);
      await Promise.all(changed.map(async ([k, h]) => {
        const e = await rpc<Entry | null>("clipzou_get", { p_key: k });
        if (e) {
          cache.data.set(k, e);
          cache.hashes[k] = h;
        }
      }));
    }
    cache.fetched = Date.now();
  })().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function snap<T>(key: string, fallback: T): Promise<T> {
  await refresh();
  return (cache.data.get(key)?.data as T) ?? fallback;
}

function pc(): { pc_online: boolean; pc_seen_at: string | null } {
  const seen = cache.beat;
  return { pc_online: !!seen && Date.now() - Date.parse(seen) < PC_ONLINE_S * 1000, pc_seen_at: seen };
}

/* ---------------------------------------------------------------- arquivos (URL assinada, 1 h) */
const signed = new Map<string, { url: string; exp: number }>();

async function signedUrl(path: string, download?: string): Promise<string> {
  const k = `${path}|${download ?? ""}`;
  const hit = signed.get(k);
  if (hit && hit.exp > Date.now() + 5 * 60_000) return hit.url;
  const r = await fetch(`${BASE}/storage/v1/object/sign/clipzou/${path}`, {
    method: "POST", headers: headers(), body: JSON.stringify({ expiresIn: 3600 }), cache: "no-store",
  });
  if (!r.ok) throw new CloudError(r.status, "arquivo não encontrado na nuvem");
  const j = (await r.json()) as { signedURL: string };
  const url = `${BASE}/storage/v1${j.signedURL}${download ? `&download=${encodeURIComponent(download)}` : ""}`;
  signed.set(k, { url, exp: Date.now() + 3600_000 });
  return url;
}

async function file(id: number, kind: string, download: boolean): Promise<Response> {
  const feed = await snap<FeedRow[]>("feed", []);
  const item = feed.find((f) => f.clip.id === id);
  if (!item?.cloud) return Response.json({ detail: "Esse corte está só no PC (ainda não subiu ou é grande demais)." }, { status: 404 });
  if (kind === "cover") {
    if (!item.cloud.cover) return new Response(null, { status: 404 });
    return Response.redirect(await signedUrl(item.cloud.cover), 302);
  }
  if (kind !== "output") return Response.json({ detail: "só o MP4 e a capa ficam na nuvem" }, { status: 404 });
  const key = `${item.cloud.output}|${download ? `clipzou-${id}.mp4` : ""}`;
  if (!signed.has(key)) { // conta o download do mês (cota grátis dividida com seus outros apps)
    const used = await rpc<number>("clipzou_egress");
    if (used > EGRESS_CAP) {
      return Response.json({ detail: "Limite de download do mês na nuvem atingido (protege seus outros apps). Baixe pelo PC." }, { status: 429 });
    }
    await rpc("clipzou_egress_add", { p_bytes: item.cloud.size });
  }
  return Response.redirect(await signedUrl(item.cloud.output, download ? `clipzou-${id}.mp4` : undefined), 302);
}

/* ---------------------------------------------------------------- pedidos ao PC */
async function command(method: string, path: string, body: unknown): Promise<Response> {
  const id = await rpc<number>("clipzou_cmd_add", { p_method: method, p_path: path, p_body: body ?? null });
  for (let i = 0; i < 8; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const c = await rpc<{ status: string; http_status: number | null; result: unknown } | null>("clipzou_cmd_get", { p_id: id });
    if (c && (c.status === "done" || c.status === "error")) {
      cache.fetched = 0; // próxima leitura já pega o resultado
      return Response.json(c.result ?? {}, { status: c.http_status ?? 200 });
    }
  }
  return Response.json({ detail: "Pedido enviado ao PC: ele faz assim que estiver ligado.", queued: true, imported: 0 }, { status: 202 });
}

/* ---------------------------------------------------------------- rotas /api/engine/* no modo nuvem */
export async function cloudRoute(req: Request, parts: string[]): Promise<Response> {
  if (!validSession(cookieFrom(req))) return Response.json({ detail: "faça login" }, { status: 401 });
  if (!KEY) return Response.json({ detail: "Falta SUPABASE_SECRET_KEY nas variáveis da Vercel." }, { status: 503 });
  const path = `/${parts.join("/")}`;
  const url = new URL(req.url);
  try {
    if (req.method !== "GET") {
      if (!ALLOWED.some(([m, re]) => m === req.method && re.test(path))) {
        return Response.json({ detail: "Isso só funciona no PC: abra o Clipzou no computador." }, { status: 503 });
      }
      const body = req.method === "DELETE" ? null : await req.json().catch(() => null);
      return await command(req.method, path, body);
    }
    const m = path.match(/^\/clips\/(\d+)\/file\/(\w+)$/);
    if (m) return await file(Number(m[1]), m[2], url.searchParams.get("download") === "true");
    await refresh();
    const online = pc();
    switch (path) {
      case "/health": {
        const h = await snap<Record<string, unknown>>("health", {});
        return Response.json({ ...h, ok: online.pc_online, cloud: true, ...online });
      }
      case "/live/status": {
        const s = await snap<Record<string, unknown>>("status", {});
        return Response.json({ ...s, radar_running: !!s.radar_running && online.pc_online, cloud: true, ...online });
      }
      case "/live/streams": return Response.json(await snap("streams", []));
      case "/live/moments": return Response.json(await snap("moments", []));
      case "/live/videos": return Response.json(await snap("videos", []));
      case "/live/channels": return Response.json(await snap("channels", []));
      case "/feed": return Response.json(await snap("feed", []));
      case "/feed/queue": return Response.json(online.pc_online ? await snap("queue", []) : []);
      case "/inbox": return Response.json(await snap("inbox", { path: "", confirmed: false, pending: [], imported: 0, errors: [] }));
      case "/system/version": return Response.json({ ...(await snap<Record<string, unknown>>("version", {})), cloud: true });
      case "/settings": return Response.json(await snap("settings", {}));
      case "/cloud/status": {
        const used = await rpc<number>("clipzou_egress");
        return Response.json({ cloud: true, ...online, egress_mb: Math.round(used / 1e5) / 10, egress_cap_mb: Math.round(EGRESS_CAP / 1048576) });
      }
      default:
        return Response.json({ detail: "Isso só funciona no PC: abra o Clipzou no computador." }, { status: 503 });
    }
  } catch (e) {
    const status = e instanceof CloudError && e.status === 401 ? 503 : 502;
    return Response.json({ detail: status === 503 ? "A Vercel não conseguiu entrar no Supabase: confira SUPABASE_SECRET_KEY." : "Nuvem indisponível agora. Tente de novo." }, { status });
  }
}
