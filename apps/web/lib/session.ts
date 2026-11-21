/* Sessão do app online (Vercel): senha única (CLIPZOU_PASSWORD) → cookie assinado (HMAC), sem banco. */
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const COOKIE = "cz_session";
export const MAX_AGE_S = 60 * 24 * 3600;

/** Modo nuvem no servidor: na Vercel (VERCEL=1) ou forçado com CLIPZOU_MODE=cloud. */
export const CLOUD_SERVER = process.env.VERCEL === "1" || process.env.CLIPZOU_MODE === "cloud";

function secret(): string | null {
  const pw = process.env.CLIPZOU_PASSWORD;
  if (!pw) return null;
  const extra = process.env.CLIPZOU_SESSION_SECRET ?? process.env.SUPABASE_SECRET_KEY ?? "";
  return createHash("sha256").update(`clipzou|${pw}|${extra}`).digest("hex");
}

const mac = (key: string, msg: string) => createHmac("sha256", key).update(msg).digest("hex");

function same(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export const passwordConfigured = () => !!process.env.CLIPZOU_PASSWORD;

export function checkPassword(input: string): boolean {
  const pw = process.env.CLIPZOU_PASSWORD;
  if (!pw) return false;
  const h = (s: string) => createHash("sha256").update(s).digest("hex");
  return same(h(input), h(pw));
}

export function newSession(): string {
  const key = secret();
  if (!key) throw new Error("CLIPZOU_PASSWORD não definida");
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_S;
  return `${exp}.${mac(key, String(exp))}`;
}

export function validSession(token: string | undefined | null): boolean {
  const key = secret();
  if (!key || !token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !/^\d+$/.test(exp) || Number(exp) < Date.now() / 1000) return false;
  return same(sig, mac(key, exp));
}

export function cookieFrom(req: Request): string | undefined {
  const raw = req.headers.get("cookie") ?? "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === COOKIE) return decodeURIComponent(v.join("="));
  }
  return undefined;
}
