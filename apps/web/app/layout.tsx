import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import Script from "next/script";
import { PwaRegister } from "@/components/pwa";
import { Shell } from "@/components/shell";
import { BIP_SCRIPT } from "@/lib/pwa-script";
import "./globals.css";

export const metadata: Metadata = {
  title: "STARK CLIP AI",
  description: "Central de comando: cortes com IA, legendas, render 9:16 e publicação assistida.",
  applicationName: "STARK CLIP AI",
  appleWebApp: { capable: true, title: "STARK", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = { themeColor: "#04060c", width: "device-width", initialScale: 1, viewportFit: "cover" };

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
