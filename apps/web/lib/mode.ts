/* Onde o app está rodando: no PC (completo) ou online na Vercel (radar, feed e pedidos ao PC). */
export const CLOUD = process.env.NEXT_PUBLIC_CLIPZOU_CLOUD === "1";
