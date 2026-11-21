"use client";
/* Estado PWA via useSyncExternalStore (sem setState em effect). O evento beforeinstallprompt é
   capturado cedo por um script inline no <head> (layout) e guardado em window.__starkBip. */
import { useSyncExternalStore } from "react";

export type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };
type W = Window & { __starkBip?: InstallEvent | null; __starkInstalled?: boolean };

export const BIP_SCRIPT =
  "window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();window.__starkBip=e;" +
  "window.dispatchEvent(new Event('stark-bip'))});window.addEventListener('appinstalled',function(){" +
  "window.__starkBip=null;window.__starkInstalled=true;window.dispatchEvent(new Event('stark-bip'))});";

const onBip = (cb: () => void) => {
  window.addEventListener("stark-bip", cb);
  return () => window.removeEventListener("stark-bip", cb);
};

export function useInstallPrompt(): InstallEvent | null {
  return useSyncExternalStore(onBip, () => (window as W).__starkBip ?? null, () => null);
}

export function useJustInstalled(): boolean {
  return useSyncExternalStore(onBip, () => !!(window as W).__starkInstalled, () => false);
}

const STANDALONE = "(display-mode: standalone)";
export function useStandalone(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(STANDALONE);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(STANDALONE).matches || (navigator as Navigator & { standalone?: boolean }).standalone === true,
    () => false,
  );
}

export type Platform = "ios" | "android" | "desktop" | "unknown";
const noop = () => () => {};

export function usePlatform(): Platform {
  return useSyncExternalStore(noop, () => {
    const ua = navigator.userAgent;
    if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
    if (/Android/i.test(ua)) return "android";
    return "desktop";
  }, () => "unknown");
}

export function useOrigin(): { origin: string; secure: boolean; local: boolean } {
  const origin = useSyncExternalStore(noop, () => window.location.origin, () => "");
  const secure = useSyncExternalStore(noop, () => window.isSecureContext, () => true);
  return { origin, secure, local: /\/\/(127\.0\.0\.1|localhost|\[::1\])(:|$)/.test(origin) };
}

export async function runInstall(evt: InstallEvent): Promise<boolean> {
  await evt.prompt();
  const { outcome } = await evt.userChoice;
  (window as W).__starkBip = null;
  window.dispatchEvent(new Event("stark-bip"));
  return outcome === "accepted";
}
