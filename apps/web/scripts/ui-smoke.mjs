// Smoke de UI: abre as telas, falha se houver erro de JS/console ou overflow horizontal no mobile.
// Pré-requisito: app rodando (pnpm dev) + `npx playwright install chromium`.
// Uso: node apps/web/scripts/ui-smoke.mjs [http://127.0.0.1:3000]
const BASE = process.argv[2] ?? "http://127.0.0.1:3000";
import { createRequire } from "node:module";
let pw;
try {
  pw = await import("playwright");
} catch {
  try {
    pw = createRequire(import.meta.url)("playwright"); // NODE_PATH / instalação global
  } catch {
    console.error("instale: npm i -D playwright && npx playwright install chromium");
    process.exit(2);
  }
}
const { chromium, devices } = pw.default ?? pw;
const browser = await chromium.launch();
const errors = [];
const routes = ["/", "/library", "/studio", "/publish", "/trends", "/settings"];
for (const ctxOpts of [{ viewport: { width: 1440, height: 900 } }, devices["iPhone 13"]]) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${page.url()} :: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${page.url()} :: ${m.text()}`));
  for (const r of routes) {
    await page.goto(BASE + r, { waitUntil: "networkidle" });
    const w = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (w > 1) errors.push(`overflow horizontal ${w}px em ${r} (${ctxOpts.viewport?.width}px)`);
  }
  await ctx.close();
}
await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`ok: ${routes.length} rotas × 2 viewports sem erros`);
