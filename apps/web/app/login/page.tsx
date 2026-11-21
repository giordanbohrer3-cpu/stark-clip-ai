"use client";
import { LockKeyhole } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button, Input, Note } from "@/components/ui";

function nextPath(): string {
  if (typeof window === "undefined") return "/";
  const n = new URLSearchParams(window.location.search).get("next") ?? "/";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/";
}

export default function LoginPage() {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const r = await fetch("/api/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ password: pw }) });
      if (!r.ok) {
        setErr(((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? "Não deu certo.");
        return;
      }
      window.location.replace(nextPath());
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-[#0b0614] px-4">
      <form onSubmit={submit} className="hud-panel w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/clipzou-96.png" alt="" className="size-12 rounded-full shadow-[0_0_24px_-4px_var(--violet)]" />
          <div>
            <h1 className="text-xl font-bold">Clipzou</h1>
            <p className="text-xs text-muted">app online · só você entra</p>
          </div>
        </div>
        {err && <Note tone="bad">{err}</Note>}
        <label className="block space-y-1.5">
          <span className="hud-label">senha</span>
          <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" autoFocus required />
        </label>
        <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!pw} icon={<LockKeyhole className="size-4" />}>Entrar</Button>
      </form>
    </div>
  );
}
