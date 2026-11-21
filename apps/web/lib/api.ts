"use client";
/* Cliente tipado da API v1 via proxy /api/engine (token fica no servidor Next). */
import { useCallback, useEffect, useRef, useState } from "react";
import type { JobRow } from "./types";

export const BASE = "/api/engine";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Init = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : init.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const d = await res.json();
      msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail ?? d);
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

/** Busca com polling; pausa quando a aba está oculta. */
export function usePoll<T>(path: string | null, ms = 4000) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      if (alive.current) {
        setData(d);
        setError(undefined);
      }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    const first = setTimeout(load, 0);
    const id = ms ? setInterval(() => !document.hidden && load(), ms) : undefined;
    return () => {
      alive.current = false;
      clearTimeout(first);
      clearInterval(id);
    };
  }, [load, ms]);

  return { data, error, loading, reload: load, setData };
}

export const fileUrl = (clipId: number, kind: string, download = false) =>
  `${BASE}/clips/${clipId}/file/${kind}${download ? "?download=true" : ""}`;

export const activeJob = (jobs: JobRow[] | undefined) =>
  jobs?.find((j) => j.status === "running" || j.status === "queued");

/** Upload com progresso (fetch não expõe progresso de envio). */
export function uploadWithProgress(path: string, form: FormData, onProgress: (f: number) => void) {
  return new Promise<unknown>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { detail?: unknown } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* vazio */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(xhr.status, String(body.detail ?? xhr.statusText)));
    };
    xhr.onerror = () => reject(new ApiError(0, "falha de rede"));
    xhr.send(form);
  });
}
