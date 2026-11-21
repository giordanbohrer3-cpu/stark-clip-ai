import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "STARK CLIP AI",
    short_name: "STARK",
    description: "Cortes verticais com IA local: transcrição, 3 cortes, legendas, render 9:16 e agenda.",
    lang: "pt-BR",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#04060c",
    theme_color: "#04060c",
    categories: ["productivity", "photo", "video"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Enviar vídeo", url: "/library", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Estúdio", url: "/studio", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Publicar", url: "/publish", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
