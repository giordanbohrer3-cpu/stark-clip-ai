"use client";
import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Panel({ title, eyebrow, actions, children, className, id }: {
  title?: ReactNode; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={clsx("hud-panel p-4 sm:p-5", className)} aria-labelledby={id ? `${id}-t` : undefined}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {eyebrow && <p className="hud-label">{eyebrow}</p>}
            {title && <h2 id={id ? `${id}-t` : undefined} className="mt-0.5 text-base font-semibold text-ink">{title}</h2>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

const tones = {
  cyan: "text-cyan", violet: "text-violet", ok: "text-ok", warn: "text-warn", bad: "text-bad", ink: "text-ink",
} as const;

export function Stat({ label, value, hint, tone = "ink" }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: keyof typeof tones;
}) {
  return (
    <div className="hud-panel p-4">
      <p className="hud-label">{label}</p>
      <p className={clsx("mt-2 font-mono text-2xl font-semibold tabular-nums", tones[tone])}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

const STATUS: Record<string, [string, string]> = {
  queued: ["na fila", "border-blue/40 text-blue"], running: ["executando", "border-cyan/50 text-cyan"],
  done: ["concluído", "border-ok/40 text-ok"], error: ["erro", "border-bad/50 text-bad"],
  canceled: ["cancelado", "border-muted/40 text-muted"], uploaded: ["enviado", "border-blue/40 text-blue"],
  reference: ["referência", "border-violet/40 text-violet"], analyzing: ["analisando", "border-cyan/50 text-cyan"],
  ready: ["pronto", "border-ok/40 text-ok"], draft: ["rascunho", "border-muted/40 text-muted"],
  rendering: ["renderizando", "border-cyan/50 text-cyan"], candidate: ["aguardando", "border-warn/40 text-warn"],
  approved: ["aprovado", "border-ok/40 text-ok"], rejected: ["rejeitado", "border-muted/40 text-muted"],
  scheduled: ["agendado", "border-blue/40 text-blue"], publishing: ["publicando", "border-cyan/50 text-cyan"],
  ready_manual: ["kit pronto", "border-violet/50 text-violet"], exported: ["exportado", "border-ok/40 text-ok"],
  published: ["publicado", "border-ok/50 text-ok"], failed: ["falhou", "border-bad/50 text-bad"],
  blocked: ["bloqueado", "border-bad/50 text-bad"], needs_oauth: ["sem OAuth", "border-warn/40 text-warn"],
  connected: ["conectada", "border-ok/40 text-ok"], paused: ["pausada", "border-muted/40 text-muted"],
};

export function Badge({ status, children, className }: { status?: string; children?: ReactNode; className?: string }) {
  const [label, cls] = STATUS[status ?? ""] ?? [status ?? "", "border-line text-muted"];
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[0.68rem] uppercase tracking-wider", cls, className)}>
      {children ?? label}
    </span>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "subtle"; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode;
};

export function Button({ variant = "ghost", size = "md", loading, icon, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-[10px] font-medium transition-[background,border,box-shadow,color] disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
        variant === "primary" && "bg-gradient-to-r from-cyan to-blue text-[#021018] shadow-[0_0_24px_-6px_var(--cyan)] hover:brightness-110",
        variant === "ghost" && "border border-line bg-surface-2 text-ink hover:border-cyan/50 hover:text-cyan",
        variant === "subtle" && "text-muted hover:text-cyan",
        variant === "danger" && "border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20",
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Progress({ value, label, active }: { value: number; label?: string; active?: boolean }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label ?? "progresso"}>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full bg-gradient-to-r from-cyan via-blue to-violet transition-[width] duration-500" style={{ width: `${pct}%` }} />
        {active && <div className="scan absolute inset-0" aria-hidden />}
      </div>
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="hud-label">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const control = "w-full rounded-[10px] border border-line bg-black/30 px-3 text-sm text-ink placeholder:text-muted/60 focus:border-cyan/60 focus:outline-none";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={clsx(control, "h-10", className)} />
);
export const Select = ({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={clsx(control, "h-10", className)}>{children}</select>
);
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={clsx(control, "min-h-24 py-2", className)} />
);

export function Toggle({ checked, onChange, label, hint, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean;
}) {
  return (
    <label className={clsx("flex cursor-pointer items-start gap-3", disabled && "opacity-50")}>
      <input type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="relative mt-0.5 h-5 w-9 shrink-0 rounded-full border border-line bg-black/40 transition peer-checked:border-cyan/60 peer-checked:bg-cyan/25 peer-focus-visible:outline-2 peer-focus-visible:outline-cyan after:absolute after:left-0.5 after:top-0.5 after:size-3.5 after:rounded-full after:bg-muted after:transition peer-checked:after:translate-x-4 peer-checked:after:bg-cyan" />
      <span>
        <span className="text-sm text-ink">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
    </label>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-10 text-center">
      {icon && <div className="text-cyan/70">{icon}</div>}
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Note({ tone = "info", children }: { tone?: "info" | "warn" | "bad" | "ok"; children: ReactNode }) {
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={clsx("rounded-[10px] border px-3 py-2 text-sm",
      tone === "info" && "border-blue/30 bg-blue/10 text-ink", tone === "warn" && "border-warn/30 bg-warn/10 text-warn",
      tone === "bad" && "border-bad/40 bg-bad/10 text-bad", tone === "ok" && "border-ok/30 bg-ok/10 text-ok")}>
      {children}
    </div>
  );
}

export function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const r = size / 2 - 5;
  const c = 2 * Math.PI * r;
  const tone = score >= 70 ? "var(--ok)" : score >= 50 ? "var(--cyan)" : "var(--warn)";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`score ${Math.round(score)} de 100`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / .08)" strokeWidth="4" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth="4" strokeLinecap="round"
        strokeDasharray={`${(c * score) / 100} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="54%" textAnchor="middle" dominantBaseline="middle" className="fill-ink font-mono text-[13px] font-semibold">
        {Math.round(score)}
      </text>
    </svg>
  );
}
