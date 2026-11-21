"""Contas sociais, agenda de publicações e métricas (manuais ou via API autorizada)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..models import (
    AnalyticsSnapshot,
    ClipCandidate,
    EditedClip,
    ScheduledPost,
    SocialAccount,
    SocialAccountRead,
    utcnow,
)
from ..publishing import UPLOAD_URLS, PostError, create_post, next_slots
from ..schemas import AccountIn, AccountPatch, BulkScheduleIn, PostIn, PostPatch, PostRow, SnapshotIn
from ..security import CtxDep, require_role

router = APIRouter(tags=["publicação"])


def acc_read(a: SocialAccount) -> SocialAccountRead:
    return SocialAccountRead.model_validate(a.model_dump(exclude={"token_encrypted"}))


def post_row(ctx, p: ScheduledPost) -> PostRow:
    acc = ctx.session.get(SocialAccount, p.account_id)
    ec = ctx.session.get(EditedClip, p.edited_clip_id)
    cand = ctx.session.get(ClipCandidate, ec.candidate_id) if ec else None
    r = PostRow.model_validate(p.model_dump())
    r.account_handle = acc.handle if acc else "?"
    r.clip_title = (ec.copy_text or {}).get("title") or (cand.title if cand else "")
    r.upload_url = UPLOAD_URLS.get(p.platform)
    return r


@router.get("/accounts", response_model=list[SocialAccountRead], summary="Contas do workspace")
def list_accounts(ctx: CtxDep) -> list[SocialAccountRead]:
    return [acc_read(a) for a in ctx.session.exec(select(SocialAccount).where(SocialAccount.workspace_id == ctx.ws.id))]


@router.post("/accounts", response_model=SocialAccountRead, status_code=status.HTTP_201_CREATED,
             summary="Cadastra perfil (criação real da conta é feita por você na plataforma)")
def add_account(ctx: CtxDep, body: AccountIn) -> SocialAccountRead:
    require_role(ctx, "owner")
    a = SocialAccount(workspace_id=ctx.ws.id, **body.model_dump())
    ctx.session.add(a)
    ctx.audit("account_add", f"{a.platform}:{a.handle}")
    ctx.session.commit()
    ctx.session.refresh(a)
    return acc_read(a)


@router.patch("/accounts/{acc_id}", response_model=SocialAccountRead, summary="Edita perfil/limite diário")
def patch_account(ctx: CtxDep, acc_id: int, body: AccountPatch) -> SocialAccountRead:
    require_role(ctx, "owner")
    a = ctx.get_owned(SocialAccount, acc_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(a, k, v)
    ctx.session.add(a)
    ctx.audit("account_update", f"account:{a.id}")
    ctx.session.commit()
    ctx.session.refresh(a)
    return acc_read(a)


@router.get("/accounts/{acc_id}/slots", response_model=list[str], summary="Próximos horários livres (cadência)")
def slots(ctx: CtxDep, acc_id: int, n: int = 5) -> list[str]:
    a = ctx.get_owned(SocialAccount, acc_id)
    return [t.isoformat() for t in next_slots(ctx.session, ctx.ws, a, min(n, 20))]


@router.get("/posts", response_model=list[PostRow], summary="Agenda e histórico")
def list_posts(ctx: CtxDep, state: str = "") -> list[PostRow]:
    stmt = select(ScheduledPost).where(ScheduledPost.workspace_id == ctx.ws.id).order_by(ScheduledPost.scheduled_at)
    if state:
        stmt = stmt.where(ScheduledPost.status == state)
    return [post_row(ctx, p) for p in ctx.session.exec(stmt.limit(500))]


def _make(ctx, ec: EditedClip, acc: SocialAccount, body: PostIn | None, mode: str) -> ScheduledPost:
    copy = ec.copy_text or {}
    caption = (body.caption if body and body.caption else None) or (copy.get("captions") or {}).get(acc.platform, "")
    tags = (body.hashtags if body and body.hashtags else None) or (copy.get("hashtags") or {}).get(acc.platform, [])
    title = (body.title if body and body.title else None) or copy.get("title", "")
    return create_post(ctx.session, ctx.ws, ec, acc, body.scheduled_at if body else None, caption, tags, title, mode)


@router.post("/posts", response_model=PostRow, status_code=status.HTTP_201_CREATED, summary="Agenda publicação")
def add_post(ctx: CtxDep, body: PostIn) -> PostRow:
    require_role(ctx, "owner", "editor")
    ec, acc = ctx.get_owned(EditedClip, body.edited_clip_id), ctx.get_owned(SocialAccount, body.account_id)
    try:
        p = _make(ctx, ec, acc, body, body.mode)
    except PostError as e:
        raise HTTPException(409, str(e)) from e
    ctx.audit("post_scheduled", f"post:{p.id}", platform=p.platform, at=p.scheduled_at.isoformat())
    ctx.session.commit()
    return post_row(ctx, p)


@router.post("/posts/bulk", response_model=list[PostRow], status_code=status.HTTP_201_CREATED,
             summary="Distribui cortes nas contas respeitando cadência")
def bulk(ctx: CtxDep, body: BulkScheduleIn) -> list[PostRow]:
    require_role(ctx, "owner", "editor")
    out, errors = [], []
    for aid in body.account_ids:
        acc = ctx.get_owned(SocialAccount, aid)
        for cid in body.edited_clip_ids:
            try:
                out.append(_make(ctx, ctx.get_owned(EditedClip, cid), acc, None, body.mode))
            except PostError as e:
                errors.append(f"{acc.handle}/{cid}: {e}")
    ctx.audit("post_bulk", "", created=len(out), errors=errors[:20])
    ctx.session.commit()
    if not out and errors:
        raise HTTPException(409, "; ".join(errors[:5]))
    return [post_row(ctx, p) for p in out]


@router.patch("/posts/{post_id}", response_model=PostRow, summary="Aprova, reagenda, cancela ou marca publicado")
def patch_post(ctx: CtxDep, post_id: int, body: PostPatch) -> PostRow:
    require_role(ctx, "owner", "editor")
    p = ctx.get_owned(ScheduledPost, post_id)
    data = body.model_dump(exclude_none=True)
    if "scheduled_at" in data:
        acc = ctx.session.get(SocialAccount, p.account_id)
        slot = next_slots(ctx.session, ctx.ws, acc, 1, after=data.pop("scheduled_at"), exclude_post=p.id)
        if not slot:
            raise HTTPException(409, "sem horário livre")
        p.scheduled_at = slot[0]
    if data.get("status") == "canceled":
        if p.status in ("published",):
            raise HTTPException(409, "já publicado")
        p.status = "canceled"
    elif data.get("status") == "published":
        p.status, p.published_at = "published", utcnow()
        p.external_url = data.get("external_url") or p.external_url
    for k in ("approved", "caption", "hashtags"):
        if k in data:
            setattr(p, k, data[k])
    ctx.session.add(p)
    ctx.audit("post_update", f"post:{p.id}", **{k: str(v) for k, v in body.model_dump(exclude_none=True).items()})
    ctx.session.commit()
    ctx.session.refresh(p)
    return post_row(ctx, p)


@router.post("/posts/{post_id}/snapshots", status_code=status.HTTP_201_CREATED, response_model=dict,
             summary="Registra métricas observadas (manual) do post")
def add_snapshot(ctx: CtxDep, post_id: int, body: SnapshotIn) -> dict:
    p = ctx.get_owned(ScheduledPost, post_id)
    snap = AnalyticsSnapshot(post_id=p.id, **body.model_dump())
    ctx.session.add(snap)
    ctx.audit("analytics_manual", f"post:{p.id}", views=body.views)
    ctx.session.commit()
    return {"id": snap.id}
