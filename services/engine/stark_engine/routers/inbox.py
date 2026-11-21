"""Pasta de entrada: declaração única de direitos, status, buscar agora e abrir a pasta no PC."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from .. import inbox
from ..models import SourceVideo, utcnow
from ..security import CtxDep, deep_merge, require_role

router = APIRouter(prefix="/inbox", tags=["pasta de entrada"])


class InboxConfirm(BaseModel):
    confirm: bool = False
    rights_type: Literal["own", "licensed", "creator_permission", "public_domain", "cc_by"] = "own"
    holder: str = Field(default="", max_length=120)
    allows_commercial: bool = True


@router.get("", response_model=dict, summary="Pasta de entrada: caminho, declaração e arquivos na fila")
def status(ctx: CtxDep) -> dict:
    cfg = ctx.settings["inbox"]
    d = inbox.folder(cfg)
    try:
        d.mkdir(parents=True, exist_ok=True)
        exists = True
    except OSError:
        exists = False
    vids = list(ctx.session.exec(select(SourceVideo).where(SourceVideo.workspace_id == ctx.ws.id,
                                                           SourceVideo.origin == "inbox")))
    return {"path": str(d), "exists": exists, "enabled": bool(cfg.get("enabled", True)),
            "confirmed": bool(cfg.get("confirmed")), "confirmed_at": cfg.get("confirmed_at"),
            "rights_type": cfg.get("rights_type"), "holder": cfg.get("holder"),
            "pending": inbox.pending(ctx.session, ctx.ws) if exists else [], "imported": len(vids),
            "errors": [{"title": v.title, "error": v.error} for v in vids if v.status == "error"][-5:]}


@router.post("/confirm", response_model=dict, summary="Declaração única: os vídeos desta pasta são autorizados")
def confirm(ctx: CtxDep, body: InboxConfirm) -> dict:
    require_role(ctx, "owner")
    if not body.confirm:
        raise HTTPException(422, "confirme que você tem autorização para os vídeos que coloca na pasta")
    decl = {"confirmed": True, "confirmed_at": utcnow().isoformat(), "rights_type": body.rights_type,
            "holder": body.holder.strip(), "allows_commercial": body.allows_commercial}
    ctx.ws.settings = deep_merge(ctx.ws.settings or {}, {"inbox": decl})
    ctx.session.add(ctx.ws)
    ctx.audit("inbox_declaration", "inbox", **decl)
    ctx.session.commit()
    return {"ok": True, **inbox.scan(ctx.session, ctx.ws)}


@router.delete("/confirm", response_model=dict, summary="Desativa a pasta (revoga a declaração)")
def revoke(ctx: CtxDep) -> dict:
    require_role(ctx, "owner")
    ctx.ws.settings = deep_merge(ctx.ws.settings or {}, {"inbox": {"confirmed": False}})
    ctx.session.add(ctx.ws)
    ctx.audit("inbox_revoke", "inbox")
    ctx.session.commit()
    return {"ok": True}


@router.post("/scan", response_model=dict, summary="Busca vídeos novos na pasta agora")
def scan(ctx: CtxDep) -> dict:
    require_role(ctx, "owner", "editor")
    return inbox.scan(ctx.session, ctx.ws)


@router.post("/open", response_model=dict, summary="Abre a pasta no gerenciador de arquivos do PC")
def open_(ctx: CtxDep) -> dict:
    require_role(ctx, "owner")
    d = inbox.folder(ctx.settings["inbox"])
    try:
        inbox.open_folder(d)
    except OSError as e:
        raise HTTPException(424, f"abra manualmente: {d} ({e})") from e
    return {"ok": True, "path": str(d)}
