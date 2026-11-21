import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "STARK CLIP AI",
  description: "Central de comando: cortes com IA, legendas, render 9:16 e publicação assistida.",
};

export const viewport: Viewport = { themeColor: "#04060c", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
