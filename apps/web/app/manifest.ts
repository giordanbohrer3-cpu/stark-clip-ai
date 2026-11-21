import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Clipzou",
    short_name: "Clipzou",
    description: "Máquina de clipes: radar das lives e vídeos bombando e cortes prontos para TikTok, Reels e Shorts.",
    lang: "pt-BR",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#0b0614",
    theme_color: "#0b0614",
    categories: ["productivity", "photo", "video"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Feed de cortes", url: "/feed", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Radar ao vivo", url: "/", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Publicar", url: "/publish", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
