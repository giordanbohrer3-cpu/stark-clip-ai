import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import Script from "next/script";
import { PwaRegister } from "@/components/pwa";
import { Shell } from "@/components/shell";
import { BIP_SCRIPT } from "@/lib/pwa-script";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clipzou",
  description: "Máquina de clipes: radar das lives e vídeos bombando e cortes prontos para postar.",
  applicationName: "Clipzou",
  appleWebApp: { capable: true, title: "Clipzou", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = { themeColor: "#0b0614", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Script id="stark-bip" strategy="beforeInteractive">{BIP_SCRIPT}</Script>
        <PwaRegister />
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
