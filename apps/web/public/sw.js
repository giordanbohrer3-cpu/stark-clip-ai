/* Clipzou service worker: instalação PWA + página offline.
   Regras: /api nunca é cacheado; /_next/static (nomes com hash) cache-first; páginas network-first. */
const VERSION = "clipzou-v4";
const MAX_STATIC = 250; // evita acumular arquivos de versões antigas
const OFFLINE = "/offline.html";
const PRECACHE = [OFFLINE, "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then(async (c) => {
            await c.put(req, copy);
            const keys = (await c.keys()).filter((k) => !PRECACHE.includes(new URL(k.url).pathname));
            for (const k of keys.slice(0, Math.max(0, keys.length - MAX_STATIC))) await c.delete(k);
          });
        }
        return res;
      })),
    );
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
  }
});
