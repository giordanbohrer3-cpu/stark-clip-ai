/* App online: tudo exige login (senha única). No PC não faz nada. */
import { type NextRequest, NextResponse } from "next/server";
import { CLOUD_SERVER, COOKIE, validSession } from "./lib/session";

const OPEN = ["/login", "/api/login"];

export function proxy(req: NextRequest) {
  if (!CLOUD_SERVER) return NextResponse.next();
  const { pathname, search } = req.nextUrl;
  if (OPEN.includes(pathname) || validSession(req.cookies.get(COOKIE)?.value)) return NextResponse.next();
  if (pathname.startsWith("/api/")) return NextResponse.json({ detail: "faça login" }, { status: 401 });
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|icons/|brand/|favicon.ico|icon.png|apple-icon.png|manifest.webmanifest|sw.js|offline.html).*)"],
};
