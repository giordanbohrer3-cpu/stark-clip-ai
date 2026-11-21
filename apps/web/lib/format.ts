export const clock = (s: number) => {
  const t = Math.max(0, s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = Math.floor(t % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};

export const clockMs = (s: number) => `${clock(s)}.${String(Math.floor((s % 1) * 10))}`;

const asDate = (iso: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);

export const when = (iso: string | null | undefined) =>
  iso ? asDate(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";

export const ago = (iso: string) => {
  const d = (Date.now() - asDate(iso).getTime()) / 1000;
  if (d < 60) return "agora";
  if (d < 3600) return `${Math.floor(d / 60)} min`;
  if (d < 86400) return `${Math.floor(d / 3600)} h`;
  return `${Math.floor(d / 86400)} d`;
};

export const num = (n: number) => new Intl.NumberFormat("pt-BR", { notation: n > 9999 ? "compact" : "standard" }).format(n);

export const mb = (bytes: number) => `${(bytes / 1e6).toFixed(1)} MB`;

export const usd = (n: number) => `US$ ${n.toFixed(n < 1 ? 3 : 2)}`;

export const toLocalInput = (d: Date) => {
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
