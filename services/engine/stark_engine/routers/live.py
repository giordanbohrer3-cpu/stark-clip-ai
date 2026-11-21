"""Máquina de clipes: radar ao vivo, momentos, canais autorizados, login Twitch, campanhas e feed."""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from ..config import get_settings
from ..importer import ImportError_, check_public, normalize
from ..jobqueue import enqueue
from ..live import twitch
from ..live.radar import read_state
from ..models import (
    ChannelGrant,
    ChannelGrantBase,
    ChannelGrantRead,
    ClipCandidate,
    EditedClip,
    EditedClipRead,
    Integration,
    Job,
    LiveMoment,
    LiveMomentRead,
    LiveStream,
    LiveStreamRead,
    SourceVideo,
    Trend,
    utcnow,
)
from ..security import CtxDep, require_role
from .videos import clip_read

router = APIRouter(prefix="/live", tags=["radar"])
feed_router = APIRouter(tags=["feed"])
_states: dict[str, tuple[int, float]] = {}  # state OAuth → (workspace, expira)


class ChannelIn(ChannelGrantBase):
    confirm: bool = False


class CampaignIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000)
    campaign: str = Field(min_length=2, max_length=120)
    evidence: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=200)
    layout: str = "auto"
    credit: str = Field(default="", max_length=80)
    allows_commercial: bool = True
    confirm: bool = False


class FeedItem(BaseModel):
    clip: EditedClipRead
    video_id: int
    title: str
    origin: str
    channel: str | None
    source_url: str | None


def _authorized(ctx) -> set[str]:
    return {g.channel for g in ctx.session.exec(select(ChannelGrant).where(
        ChannelGrant.workspace_id == ctx.ws.id, ChannelGrant.active.is_(True)))}


@router.get("/status", response_model=dict, summary="Estado do radar e das conexões")
def status_(ctx: CtxDep) -> dict:
    s = ctx.session
    day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    lives = s.exec(select(func.count(), func.coalesce(func.sum(LiveStream.viewers), 0)).where(
        LiveStream.workspace_id == ctx.ws.id, LiveStream.live.is_(True))).one()
    moments = s.exec(select(func.count()).select_from(LiveMoment).where(
        LiveMoment.workspace_id == ctx.ws.id, LiveMoment.at >= day)).one()
    ready = s.exec(select(func.count()).select_from(EditedClip).where(
        EditedClip.workspace_id == ctx.ws.id, EditedClip.status == "ready")).one()
    it = s.exec(select(Integration).where(Integration.workspace_id == ctx.ws.id,
                                          Integration.provider == "twitch")).first()
    st = read_state()
    fresh = False
    try:
        fresh = (datetime.fromisoformat(st.get("updated_at", "")) > utcnow() - timedelta(seconds=30))
    except ValueError:
        pass
    activity = st.get("activity") or {}
    return {"radar_running": bool(st.get("running")) and fresh, "chat": st.get("chat", "desligado"),
            "chat_channels": st.get("channels", 0), "twitch_api": st.get("twitch", "—"),
            "youtube_api": st.get("youtube", "—"), "youtube_rss": st.get("youtube_rss", "—"),
            "twitch_configured": twitch.configured(), "youtube_configured": bool(get_settings().youtube_api_key),
            "keyless": not twitch.configured(), "watching": len(ctx.settings["radar"].get("watch_twitch") or []),
            "chat_rate": int(sum(v for v in activity.values() if isinstance(v, int | float))),
            "twitch_connected": bool(it), "twitch_login": it.account_login if it else None,
            "lives": int(lives[0]), "viewers": int(lives[1]), "moments_today": int(moments), "clips_ready": int(ready),
            "game": ctx.settings["radar"].get("game"), "inbox": st.get("inbox") or {}}


@router.get("/streams", response_model=list[LiveStreamRead], summary="Lives no radar (mais assistidas primeiro)")
def streams(ctx: CtxDep, platform: str = "", limit: int = 120) -> list[LiveStreamRead]:
    q = select(LiveStream).where(LiveStream.workspace_id == ctx.ws.id, LiveStream.live.is_(True))
    if platform:
        q = q.where(LiveStream.platform == platform)
    auth, activity = _authorized(ctx), read_state().get("activity") or {}
    out = []
    for r in ctx.session.exec(q.order_by(LiveStream.viewers.desc()).limit(min(limit, 300))):
        row = LiveStreamRead.model_validate(r.model_dump())
        row.authorized = r.channel in auth
        row.chat_rate = int(activity.get(r.channel, 0)) if r.platform == "twitch" else 0
        out.append(row)
    return sorted(out, key=lambda x: (x.viewers, x.chat_rate), reverse=True)


@router.get("/moments", response_model=list[LiveMomentRead], summary="Picos de chat detectados")
def moments(ctx: CtxDep, limit: int = 60) -> list[LiveMomentRead]:
    auth = _authorized(ctx)
    out = []
    for m in ctx.session.exec(select(LiveMoment).where(LiveMoment.workspace_id == ctx.ws.id)
                              .order_by(LiveMoment.at.desc()).limit(min(limit, 200))):
        row = LiveMomentRead.model_validate(m.model_dump())
        row.authorized, row.watch_url = m.channel in auth, f"https://twitch.tv/{m.channel}"
        out.append(row)
    return out


@router.get("/videos", response_model=list[dict], summary="Vídeos bombando no YouTube (views por hora)")
def hot_videos(ctx: CtxDep, shorts: bool = True, limit: int = 60) -> list[dict]:
    """YouTubers famosos (feed público, sem chave) + em alta no BR (API, com chave). Ordem: views/hora."""
    out: dict[str, dict] = {}
    rows = ctx.session.exec(select(Trend).where(Trend.workspace_id == ctx.ws.id,
                                                Trend.source.in_(("youtube_api", "youtube_rss"))))
    for t in rows:
        m = t.metric or {}
        if (m.get("short") and not shorts) or not t.url:
            continue
        try:
            hours = max(1.0, (time.time() - datetime.fromisoformat(m["published_at"]).timestamp()) / 3600)
        except (KeyError, ValueError, AttributeError, TypeError):
            hours = 24.0
        views = int(m.get("views") or 0)
        item = {"id": t.id, "title": t.label, "url": t.url, "channel": m.get("channel"), "views": views,
                "likes": int(m.get("likes") or 0), "views_per_hour": int(views / hours),
                "thumbnail_url": m.get("thumbnail_url"), "duration_s": m.get("duration_s", 0),
                "published_at": m.get("published_at"), "short": bool(m.get("short")), "source": t.source}
        if t.url not in out or views > out[t.url]["views"]:
            out[t.url] = item
    return sorted(out.values(), key=lambda x: x["views_per_hour"], reverse=True)[:min(limit, 200)]


# ------------------------------------------------------------------ canais autorizados
@router.get("/channels", response_model=list[ChannelGrantRead], summary="Canais que autorizam cortes")
def channels(ctx: CtxDep) -> list[ChannelGrantRead]:
    rows = ctx.session.exec(select(ChannelGrant).where(ChannelGrant.workspace_id == ctx.ws.id))
    return [ChannelGrantRead.model_validate(g.model_dump()) for g in rows]


@router.post("/channels", response_model=ChannelGrantRead, status_code=status.HTTP_201_CREATED,
             summary="Registra canal autorizado (você é editor ou está no programa de cortes)")
def add_channel(ctx: CtxDep, body: ChannelIn) -> ChannelGrantRead:
    require_role(ctx, "owner")
    if not body.confirm:
        raise HTTPException(422, "confirme que o canal autorizou seus cortes")
    login = body.channel.strip().lower().lstrip("@").removeprefix("https://twitch.tv/").removeprefix("https://www.twitch.tv/")
    if not login.replace("_", "").isalnum():
        raise HTTPException(422, "nome de canal inválido")
    g = ctx.session.exec(select(ChannelGrant).where(ChannelGrant.workspace_id == ctx.ws.id,
                                                    ChannelGrant.channel == login)).first()
    g = g or ChannelGrant(workspace_id=ctx.ws.id, channel=login)
    for k, v in body.model_dump(exclude={"confirm", "channel"}).items():
        setattr(g, k, v)
    g.display_name = body.display_name or login
    ctx.session.add(g)
    ctx.audit("channel_grant", f"twitch:{login}", rights=body.rights_type, evidence=body.evidence[:200])
    ctx.session.commit()
    ctx.session.refresh(g)
    return ChannelGrantRead.model_validate(g.model_dump())


@router.delete("/channels/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove autorização")
def del_channel(ctx: CtxDep, grant_id: int) -> None:
    ctx.session.delete(ctx.get_owned(ChannelGrant, grant_id))
    ctx.session.commit()


@router.post("/channels/{grant_id}/clip", response_model=dict, status_code=status.HTTP_202_ACCEPTED,
             summary="Cortar agora (últimos ~30 s da live)")
def clip_now(ctx: CtxDep, grant_id: int) -> dict:
    g = ctx.get_owned(ChannelGrant, grant_id)
    m = LiveMoment(workspace_id=ctx.ws.id, channel=g.channel, score=50, tokens=["manual"], status="detected")
    ctx.session.add(m)
    ctx.session.commit()
    ctx.session.refresh(m)
    job = enqueue(ctx.session, ctx.ws.id, "twitch_clip", m.id)
    return {"moment_id": m.id, "job_id": job.id}


# ------------------------------------------------------------------ login Twitch (OAuth)
@router.get("/twitch/connect", response_model=dict, summary="URL de login Twitch")
def twitch_connect(ctx: CtxDep) -> dict:
    try:
        state = secrets.token_urlsafe(24)
        _states[state] = (ctx.ws.id, time.time() + 600)
        return {"url": twitch.authorize_url(state)}
    except twitch.TwitchError as e:
        raise HTTPException(424, str(e)) from e


@router.get("/twitch/callback", summary="Retorno do login Twitch")
def twitch_callback(ctx: CtxDep, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    ws_id, exp = _states.pop(state, (None, 0))
    if error or not code or ws_id != ctx.ws.id or time.time() > exp:
        return RedirectResponse("/?twitch=erro", status_code=302)
    try:
        twitch.exchange_code(ctx.session, ctx.ws.id, code)
    except twitch.TwitchError:
        return RedirectResponse("/?twitch=erro", status_code=302)
    ctx.audit("twitch_connect", "twitch")
    ctx.session.commit()
    return RedirectResponse("/?twitch=ok", status_code=302)


@router.delete("/twitch", status_code=status.HTTP_204_NO_CONTENT, summary="Desconecta Twitch")
def twitch_disconnect(ctx: CtxDep) -> None:
    for it in ctx.session.exec(select(Integration).where(Integration.workspace_id == ctx.ws.id,
                                                         Integration.provider == "twitch")):
        ctx.session.delete(it)
    ctx.session.commit()


# ------------------------------------------------------------------ campanhas
@router.post("/campaigns", response_model=dict, status_code=status.HTTP_202_ACCEPTED,
             summary="Importa vídeo de campanha por link (Drive/Dropbox/MP4) e gera os cortes")
def campaign(ctx: CtxDep, body: CampaignIn) -> dict:
    require_role(ctx, "owner", "editor")
    if not body.confirm:
        raise HTTPException(422, "confirme que a campanha permite cortar e postar este vídeo")
    try:
        check_public(normalize(body.url))
    except ImportError_ as e:
        raise HTTPException(422, str(e)) from e
    v = SourceVideo(workspace_id=ctx.ws.id, title=body.title or body.campaign, origin="campaign", url=body.url,
                    status="queued", niche=ctx.settings["radar"].get("game") or "")
    ctx.session.add(v)
    ctx.session.commit()
    ctx.session.refresh(v)
    job = enqueue(ctx.session, ctx.ws.id, "import_url", v.id, {**body.model_dump(exclude={"confirm"}),
                                                                "user_id": ctx.user.id})
    ctx.audit("campaign_import", f"video:{v.id}", campaign=body.campaign)
    ctx.session.commit()
    return {"video_id": v.id, "job_id": job.id}


# ------------------------------------------------------------------ feed de cortes prontos
@feed_router.get("/feed", response_model=list[FeedItem], summary="Cortes prontos para baixar e postar")
def feed(ctx: CtxDep, limit: int = 60) -> list[FeedItem]:
    out = []
    rows = ctx.session.exec(select(EditedClip).where(EditedClip.workspace_id == ctx.ws.id, EditedClip.status == "ready")
                            .order_by(EditedClip.updated_at.desc()).limit(min(limit, 200)))
    for ec in rows:
        v = ctx.session.get(SourceVideo, ec.video_id)
        c = ctx.session.get(ClipCandidate, ec.candidate_id)
        out.append(FeedItem(clip=clip_read(ec), video_id=v.id, origin=v.origin, channel=v.channel, source_url=v.url,
                            title=(ec.copy_text or {}).get("title") or (c.title if c else v.title)))
    return out


STAGE = {"analyze": "achando os melhores momentos", "render": "legendando e renderizando",
         "import_url": "baixando vídeo da campanha", "twitch_clip": "clipando a live"}


@feed_router.get("/feed/queue", response_model=list[dict], summary="Cortes sendo produzidos agora")
def feed_queue(ctx: CtxDep) -> list[dict]:
    s, out = ctx.session, []
    rows = s.exec(select(Job).where(Job.workspace_id == ctx.ws.id, Job.status.in_(("queued", "running")),
                                    Job.kind.in_(tuple(STAGE))).order_by(Job.created_at).limit(30))
    for j in rows:
        title = ""
        if j.kind in ("analyze", "import_url"):
            v = s.get(SourceVideo, j.ref_id)
            title = v.title if v else ""
        elif j.kind == "render":
            ec = s.get(EditedClip, j.ref_id)
            c = s.get(ClipCandidate, ec.candidate_id) if ec else None
            title = c.title if c else ""
        else:
            m = s.get(LiveMoment, j.ref_id)
            title = f"@{m.channel}" if m else ""
        out.append({"id": j.id, "kind": j.kind, "status": j.status, "progress": round(j.progress or 0, 2),
                    "stage": j.stage or STAGE[j.kind], "label": STAGE[j.kind], "title": title[:120]})
    return out
