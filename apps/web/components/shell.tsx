"use client";
import clsx from "clsx";
import { Film, Flame, LayoutDashboard, Pause, Play, Radar, Send, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Suspense, useState } from "react";
import { api, usePoll } from "@/lib/api";
import { InstallChip } from "./pwa";
import type { Health, SettingsResp } from "@/lib/types";

const NAV = [
  { href: "/", label: "Radar", icon: Radar },
  { href: "/feed", label: "Feed", icon: Flame },
  { href: "/library", label: "Vídeos", icon: Film },
  { href: "/publish", label: "Publicar", icon: Send },
  { href: "/painel", label: "Painel", icon: LayoutDashboard },
  { href: "/settings", label: "Config", icon: Settings2 },
];

function isActive(path: string, href: string) {
  return href === "/" ? path === "/" || path.startsWith("/trends") : path.startsWith(href)
    || (href === "/feed" && path.startsWith("/studio")) || (href === "/library" && path.startsWith("/videos"));
}

function NavItems({ mobile, path = "" }: { mobile?: boolean; path?: string }) {
  return NAV.map(({ href, label, icon: Icon }) => {
    const on = !!path && isActive(path, href);
    return mobile ? (
      <Link key={href} href={href} aria-current={on ? "page" : undefined}
        className={clsx("flex flex-col items-center gap-1 py-2.5 text-[0.65rem]", on ? "text-cyan" : "text-muted")}>
        <Icon className="size-5" aria-hidden />
        {label}
      </Link>
    ) : (
      <Link key={href} href={href} aria-current={on ? "page" : undefined}
        className={clsx("flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm transition",
          on ? "border border-cyan/40 bg-cyan/10 text-cyan" : "border border-transparent text-muted hover:text-ink")}>
        <Icon className="size-4" aria-hidden />
        {label}
      </Link>
    );
  });
}

function LiveNav({ mobile }: { mobile?: boolean }) {
  return <NavItems mobile={mobile} path={usePathname()} />;
}

export function Shell({ children }: { children: ReactNode }) {
  const health = usePoll<Health>("/health", 15000);
  const cfg = usePoll<SettingsResp>("/settings", 15000);
  const [busy, setBusy] = useState(false);
  const paused = cfg.data?.settings.paused;
  const online = !health.error && health.data?.ok;

  const toggle = async () => {
    if (!paused && !confirm("Pausar o agente? Nenhum job ou publicação será executado até retomar.")) return;
    setBusy(true);
    try {
      await api(`/agent/${paused ? "resume" : "pause"}`, { method: "POST" });
      await cfg.reload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative z-10 flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-cyan focus:px-3 focus:py-2 focus:text-black">
        Pular para o conteúdo
      </a>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line bg-black/30 px-4 py-6 backdrop-blur lg:flex">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/clipzou-96.png" alt="" className="size-11 rounded-full shadow-[0_0_22px_-4px_var(--violet)]" />
          <span>
            <span className="block text-base font-bold tracking-wide">Clipzou</span>
            <span className="hud-label">máquina de clipes</span>
          </span>
        </Link>
        <nav aria-label="Principal" className="flex flex-col gap-1">
          <Suspense fallback={<NavItems />}><LiveNav /></Suspense>
        </nav>
        <div className="mt-auto space-y-2 px-2 text-xs text-muted">
          <p className="flex items-center gap-2">
            <span className={clsx("size-2 rounded-full", online ? "bg-ok shadow-[0_0_8px_var(--ok)]" : "bg-bad")} />
            motor {online ? "online" : "offline"} {health.data && `v${health.data.version}`}
          </p>
          {health.data && <p className="font-mono">whisper: {health.data.whisper_model}</p>}
          <Link href="/install" className="block text-cyan hover:underline">Instalar no celular/PC</Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-line bg-black/40 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur sm:px-6">
          <span className="flex items-center gap-2 text-sm font-bold lg:hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/clipzou-96.png" alt="" className="size-7 rounded-full" />
            Clipzou
          </span>
          <div className="hidden items-center gap-2 text-xs text-muted lg:flex">
            <span className="hud-label">modo</span>
            <span className="font-mono text-ink">{cfg.data?.settings.autonomy ?? "—"}</span>
          </div>
          <div className="flex items-center gap-2">
            <InstallChip />
            {!online && <span className="rounded-full border border-bad/50 px-2 py-0.5 text-xs text-bad">motor offline</span>}
            <button onClick={toggle} disabled={busy || !cfg.data} aria-pressed={!!paused}
              className={clsx("inline-flex h-9 items-center gap-2 rounded-[10px] border px-3 text-xs font-semibold uppercase tracking-wider",
                paused ? "border-warn/60 bg-warn/15 text-warn" : "border-line text-muted hover:border-bad/50 hover:text-bad")}>
              {paused ? <Play className="size-4" aria-hidden /> : <Pause className="size-4" aria-hidden />}
              {paused ? "Retomar agente" : "Pausa global"}
            </button>
          </div>
        </header>
        {paused && (
          <div role="status" className="border-b border-warn/30 bg-warn/10 px-4 py-2 text-center text-xs text-warn sm:px-6">
            Agente pausado — fila e publicações congeladas.
          </div>
        )}
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-28 pt-6 sm:px-6 lg:pb-10">
          <Suspense fallback={<p className="text-muted">carregando…</p>}>{children}</Suspense>
        </main>
      </div>

      <nav aria-label="Principal (móvel)" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-line bg-black/85 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        <Suspense fallback={<NavItems mobile />}><LiveNav mobile /></Suspense>
      </nav>
    </div>
  );
}
