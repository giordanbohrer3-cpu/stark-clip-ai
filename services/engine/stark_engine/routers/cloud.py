"""Nuvem (app online sem Tailscale): colar a chave secreta do Supabase, link do app e estado da sincronização."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import cloud
from ..security import CtxDep, require_role

router = APIRouter(prefix="/cloud", tags=["nuvem"])
APP_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?(/.*)?$")


class CloudIn(BaseModel):
    key: str | None = Field(default=None, max_length=600)
    url: str | None = Field(default=None, max_length=200)
    app_url: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


def _status() -> dict:
    cfg, st = cloud.load_config(), cloud.read_status()
    return {"configured": bool(cfg["key"]), "enabled": cfg["enabled"], "url": cfg["url"], "app_url": cfg["app_url"],
            "running": st.get("running", False), "error": st.get("error") or "",
            "last_sync_at": st.get("last_sync_at"), "uploaded_mb": round((st.get("bytes") or 0) / 1e6, 1),
            "storage_limit_mb": cloud.MAX_STORAGE_MB, "egress_mb": round((st.get("egress_bytes") or 0) / 1e6, 1)}


@router.get("/status", response_model=dict, summary="Estado da sincronização com o app online")
def status(ctx: CtxDep) -> dict:
    return _status()


@router.post("/config", response_model=dict, summary="Salva a chave secreta do Supabase (criptografada) e o link")
def configure(ctx: CtxDep, body: CloudIn) -> dict:
    require_role(ctx, "owner")
    cfg = cloud.load_config()
    url = (body.url or cfg["url"]).strip().rstrip("/")
    if body.app_url and not APP_URL_RE.match(body.app_url.strip()):
        raise HTTPException(422, "link do app inválido: use https://… (ex.: https://clipzou.vercel.app)")
    key = (body.key or "").strip()
    if key or body.url:
        try:
            cloud.check_key(url, key or cfg["key"])
        except cloud.CloudError as e:
            raise HTTPException(422, str(e)) from e
    cloud.save_config(url=url, key=key or None, app_url=body.app_url.strip() if body.app_url is not None else None,
                      enabled=body.enabled)
    ctx.audit("cloud_config", "cloud", key_changed=bool(key), app_url=bool(body.app_url))
    ctx.session.commit()
    return _status()


@router.delete("/config", response_model=dict, summary="Desliga a nuvem e apaga a chave deste PC")
def disconnect(ctx: CtxDep) -> dict:
    require_role(ctx, "owner")
    cloud.save_config(clear_key=True)
    ctx.audit("cloud_disconnect", "cloud")
    ctx.session.commit()
    return _status()
