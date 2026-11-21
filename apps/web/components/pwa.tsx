"use client";
import { Download } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { runInstall, useInstallPrompt, useStandalone } from "@/lib/pwa";

/** Registra o service worker (produção + contexto seguro: HTTPS ou localhost). */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator) || !window.isSecureContext) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  }, []);
  return null;
}

/** Botão compacto no cabeçalho: instala direto (Chrome/Edge/Android) ou leva ao guia /install. */
export function InstallChip() {
  const evt = useInstallPrompt();
  const standalone = useStandalone();
  if (standalone) return null;
  const cls = "inline-flex h-9 items-center gap-2 rounded-[10px] border border-cyan/40 bg-cyan/10 px-3 text-xs font-semibold text-cyan";
  return evt ? (
    <button type="button" onClick={() => runInstall(evt)} className={cls}>
      <Download className="size-4" aria-hidden /> Instalar app
    </button>
  ) : (
    <Link href="/install" className={cls}>
      <Download className="size-4" aria-hidden /> Instalar
    </Link>
  );
}
