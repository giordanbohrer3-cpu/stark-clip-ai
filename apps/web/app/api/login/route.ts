/* Login do app online: senha → cookie assinado (60 dias). DELETE = sair. */
import { checkPassword, CLOUD_SERVER, COOKIE, MAX_AGE_S, newSession, passwordConfigured } from "@/lib/session";

const cookie = (value: string, maxAge: number) =>
  `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;

export async function POST(req: Request) {
  if (!CLOUD_SERVER) return Response.json({ detail: "login só existe no app online" }, { status: 404 });
  if (!passwordConfigured()) {
    return Response.json({ detail: "Defina CLIPZOU_PASSWORD nas variáveis da Vercel e faça Redeploy." }, { status: 503 });
  }
  const body = (await req.json().catch(() => ({}))) as { password?: unknown };
  const pw = typeof body.password === "string" ? body.password.slice(0, 200) : "";
  if (!checkPassword(pw)) {
    await new Promise((r) => setTimeout(r, 600)); // freia tentativa e erro
    return Response.json({ detail: "Senha errada." }, { status: 401 });
  }
  return Response.json({ ok: true }, { headers: { "set-cookie": cookie(newSession(), MAX_AGE_S) } });
}

export async function DELETE() {
  return Response.json({ ok: true }, { headers: { "set-cookie": cookie("", 0) } });
}
