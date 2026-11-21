/* Proxy seguro p/ o motor FastAPI: injeta o token no servidor (nunca vai ao navegador),
   repassa Range (seek de vídeo) e faz streaming de uploads/downloads. */
import { readFileSync } from "node:fs";
import path from "node:path";

const ENGINE = process.env.STARK_ENGINE_URL ?? "http://127.0.0.1:8787";
const PASS_REQ = ["content-type", "range", "accept", "if-none-match", "if-range"];
const PASS_RES = ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "etag", "last-modified", "location"];

function token(): string {
  if (process.env.STARK_API_TOKEN) return process.env.STARK_API_TOKEN;
  const file = process.env.STARK_TOKEN_FILE ?? path.resolve(process.cwd(), "../../services/engine/data/.api_token");
  try {
    return readFileSync(/*turbopackIgnore: true*/ file, "utf8").trim();
  } catch {
    return "";
  }
}

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path: parts } = await ctx.params;
  if (parts.some((p) => p === ".." || p === "." || p.includes("\\"))) {
    return Response.json({ detail: "caminho inválido" }, { status: 400 });
  }
  const search = new URL(req.url).search;
  const target = `${ENGINE}/api/v1/${parts.map(encodeURIComponent).join("/")}${search}`;
  const headers = new Headers({ authorization: `Bearer ${token()}` });
  for (const h of PASS_REQ) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const init: RequestInit & { duplex?: "half" } = { method: req.method, headers, redirect: "manual", cache: "no-store" };
  if (req.method !== "GET" && req.method !== "HEAD" && req.body) {
    init.body = req.body;
    init.duplex = "half";
  }
  let res: Response;
  try {
    res = await fetch(target, init);
  } catch {
    return Response.json({ detail: "motor offline: inicie services/engine (porta 8787)" }, { status: 502 });
  }
  const out = new Headers({ "cache-control": "no-store" });
  for (const h of PASS_RES) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export { forward as DELETE, forward as GET, forward as PATCH, forward as POST, forward as PUT };
