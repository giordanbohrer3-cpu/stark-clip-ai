"""Operação: jobs, configurações (IA/orçamento/autonomia/pausa), métricas, auditoria e tendências."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlmodel import select

from .. import media
from ..ai.providers import PAID, AIError, call_json, free_only, month_spend, provider_status, route
from ..config import get_settings
from ..copywriter import to_tag
from ..jobqueue import request_cancel, retry
from ..models import (
    AIUsage,
    AnalyticsSnapshot,
    AuditLog,
    ClipCandidate,
    EditedClip,
    Job,
    JobRead,
    ScheduledPost,
    SourceVideo,
    Transcript,
    Trend,
    TrendRead,
    utcnow,
)
from ..schemas import SettingsPatch, Stats, TrendIn
from ..security import DEFAULT_SETTINGS, CtxDep, deep_merge, rel_data, require_role, safe_path
from ..youtube import YouTubeError, search, trending

router = APIRouter(tags=["operação"])
_storage_cache: dict = {"t": datetime.min.replace(tzinfo=UTC), "mb": 0.0}


# ------------------------------------------------------------------ jobs
@router.get("/jobs", response_model=list[JobRead], summary="Fila de processamento")
def list_jobs(ctx: CtxDep, state: str = "", limit: int = 50) -> list[JobRead]:
    stmt = select(Job).where(Job.workspace_id == ctx.ws.id).order_by(Job.created_at.desc())
    if state:
        stmt = stmt.where(Job.status == state)
    return [JobRead.model_validate(j.model_dump()) for j in ctx.session.exec(stmt.limit(min(limit, 200)))]


@router.post("/jobs/{job_id}/cancel", response_model=JobRead, summary="Cancela job")
def cancel_job(ctx: CtxDep, job_id: int) -> JobRead:
    job = request_cancel(ctx.session, ctx.get_owned(Job, job_id))
    ctx.audit("job_cancel", f"job:{job_id}")
    ctx.session.commit()
    return JobRead.model_validate(job.model_dump())


@router.post("/jobs/{job_id}/retry", response_model=JobRead, summary="Reenfileira job com erro")
def retry_job(ctx: CtxDep, job_id: int) -> JobRead:
    job = retry(ctx.session, ctx.get_owned(Job, job_id))
    ctx.audit("job_retry", f"job:{job_id}")
    ctx.session.commit()
    return JobRead.model_validate(job.model_dump())


# ------------------------------------------------------------------ settings
def _validate(new: dict, old: dict, confirm_paid: bool) -> None:
    if new["autonomy"] not in ("assisted", "semi", "autonomous"):
        raise HTTPException(422, "autonomy inválida")
    if float(new["ai"]["monthly_budget_usd"]) < 0:
        raise HTTPException(422, "orçamento não pode ser negativo")
    if new["clips"]["mode"] not in ("short", "long") or not 1 <= int(new["clips"]["target"]) <= 5:
        raise HTTPException(422, "clips inválido")
    for p, cfg in new["ai"]["providers"].items():
        if p not in DEFAULT_SETTINGS["ai"]["providers"]:
            raise HTTPException(422, f"provedor desconhecido: {p}")
        was = old["ai"]["providers"][p]["enabled"]
        if cfg["enabled"] and free_only() and p in PAID:
            raise HTTPException(403, f"modo 100% grátis: {p} é pago (STARK_FREE_ONLY=false para liberar)")
        if cfg["enabled"] and not was and p != "ollama" and not free_only() and not confirm_paid:
            raise HTTPException(428, f"ativar {p} gera cobrança na API: envie confirm_paid=true")
    for k, v in new["ai"]["routing"].items():
        if v not in ("heuristic", "auto", *DEFAULT_SETTINGS["ai"]["providers"]):
            raise HTTPException(422, f"rota inválida para {k}")
        if free_only() and v in PAID:
            raise HTTPException(403, f"modo 100% grátis: rota {k} não pode usar {v}")


@router.get("/settings", response_model=dict, summary="Configurações efetivas do workspace")
def get_ws_settings(ctx: CtxDep) -> dict:
    return {"settings": ctx.settings, "providers": provider_status(ctx.ws),
            "env": {"youtube_api": bool(get_settings().youtube_api_key), "whisper_model": get_settings().whisper_model,
                    "free_only": free_only()}}


@router.patch("/settings", response_model=dict, summary="Atualiza configurações (merge profundo)")
def patch_settings(ctx: CtxDep, body: SettingsPatch, confirm_paid: bool = False) -> dict:
    require_role(ctx, "owner")
    allowed = set(DEFAULT_SETTINGS)
    if not set(body.data) <= allowed:
        raise HTTPException(422, f"chaves permitidas: {sorted(allowed)}")
    old = ctx.settings
    new = deep_merge(old, body.data)
    _validate(new, old, confirm_paid)
    ctx.ws.settings = deep_merge(ctx.ws.settings or {}, body.data)
    ctx.session.add(ctx.ws)
    ctx.audit("settings_update", "workspace", keys=list(body.data), confirm_paid=confirm_paid)
    ctx.session.commit()
    return get_ws_settings(ctx)


@router.post("/agent/{action}", response_model=dict, summary="Pausa/retoma global do agente")
def agent_toggle(ctx: CtxDep, action: str) -> dict:
    if action not in ("pause", "resume"):
        raise HTTPException(404, "ação inválida")
    ctx.ws.settings = deep_merge(ctx.ws.settings or {}, {"paused": action == "pause"})
    ctx.session.add(ctx.ws)
    ctx.audit(f"agent_{action}", "workspace")
    ctx.session.commit()
    return {"paused": action == "pause"}


@router.post("/branding/logo", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Envia logo PNG")
def upload_logo(ctx: CtxDep, file: Annotated[UploadFile, File()]) -> dict:
    require_role(ctx, "owner")
    data = file.file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(415, "envie PNG (até 5 MB), de preferência com fundo transparente")
    p = safe_path(get_settings().data_dir / "branding", f"logo_ws{ctx.ws.id}.png")
    p.write_bytes(data)
    ctx.ws.settings = deep_merge(ctx.ws.settings or {}, {"branding": {"logo_path": rel_data(p)}})
    ctx.session.add(ctx.ws)
    ctx.audit("logo_upload", "workspace")
    ctx.session.commit()
    return {"logo_path": rel_data(p)}


# ------------------------------------------------------------------ métricas
def _storage_mb() -> float:
    if utcnow() - _storage_cache["t"] < timedelta(seconds=60):
        return _storage_cache["mb"]
    total = 0
    for root, _, files in os.walk(get_settings().data_dir):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    _storage_cache.update(t=utcnow(), mb=round(total / 1e6, 1))
    return _storage_cache["mb"]


def _count(ctx, model, *conds) -> int:
    return int(ctx.session.exec(select(func.count()).select_from(model).where(*conds)).one())


@router.get("/stats", response_model=Stats, summary="Métricas reais do painel")
def stats(ctx: CtxDep) -> Stats:
    ws = ctx.ws.id
    vids = ctx.session.exec(select(SourceVideo.status, func.count()).where(SourceVideo.workspace_id == ws)
                            .group_by(SourceVideo.status)).all()
    vids_d = {k: v for k, v in vids}
    vid_ids = select(SourceVideo.id).where(SourceVideo.workspace_id == ws)
    analyzed = int(ctx.session.exec(select(func.count(func.distinct(Transcript.video_id)))
                                    .where(Transcript.video_id.in_(vid_ids))).one())
    cands = ctx.session.exec(select(ClipCandidate.status, func.count()).where(ClipCandidate.video_id.in_(vid_ids))
                             .group_by(ClipCandidate.status)).all()
    edits = ctx.session.exec(select(EditedClip.status, func.count()).where(EditedClip.workspace_id == ws)
                             .group_by(EditedClip.status)).all()
    day = utcnow() - timedelta(hours=24)
    jobs = ctx.session.exec(select(Job.status, func.count()).where(Job.workspace_id == ws, Job.created_at >= day)
                            .group_by(Job.status)).all()
    running = _count(ctx, Job, Job.workspace_id == ws, Job.status.in_(("queued", "running")))
    posts = dict(ctx.session.exec(select(ScheduledPost.status, func.count()).where(ScheduledPost.workspace_id == ws)
                                  .group_by(ScheduledPost.status)).all())
    # métricas observadas: último snapshot de cada post
    post_ids = select(ScheduledPost.id).where(ScheduledPost.workspace_id == ws)
    latest = {}
    for snap in ctx.session.exec(select(AnalyticsSnapshot).where(AnalyticsSnapshot.post_id.in_(post_ids))
                                 .order_by(AnalyticsSnapshot.captured_at)):
        latest[snap.post_id] = snap
    obs = [s for s in latest.values() if s.kind != "projection"]
    analytics = {"posts_with_data": len(obs), "views": sum(s.views for s in obs), "likes": sum(s.likes for s in obs),
                 "comments": sum(s.comments for s in obs), "shares": sum(s.shares for s in obs),
                 "followers": sum(s.followers_gained for s in obs),
                 "revenue_confirmed": round(sum(s.revenue or 0 for s in obs if s.kind == "confirmed"), 2)}
    cfg = ctx.settings
    spend = month_spend(ctx.session, ws)
    budget = float(cfg["ai"]["monthly_budget_usd"])
    calls = _count(ctx, AIUsage, AIUsage.workspace_id == ws,
                   AIUsage.created_at >= datetime(utcnow().year, utcnow().month, 1, tzinfo=UTC))
    alerts = []
    if cfg["paused"]:
        alerts.append("Agente PAUSADO: nenhum job ou publicação será executado")
    if budget and spend >= budget * cfg["ai"]["alert_pct"] / 100:
        alerts.append(f"Consumo de IA em {spend / budget:.0%} do orçamento mensal")
    if dict(jobs).get("error"):
        alerts.append(f"{dict(jobs)['error']} job(s) com erro nas últimas 24h")
    if posts.get("blocked") or posts.get("failed"):
        alerts.append(f"{posts.get('blocked', 0) + posts.get('failed', 0)} publicação(ões) bloqueada(s)/falha")
    if not media.tool_ok("ffmpeg"):
        alerts.append("FFmpeg não encontrado no PATH")
    return Stats(
        videos={"total": sum(vids_d.values()), "analyzed": analyzed, "by_status": vids_d},
        clips={"candidates": sum(v for _, v in cands), "awaiting_approval": dict(cands).get("candidate", 0),
               "approved": dict(cands).get("approved", 0), "edited": sum(v for _, v in edits),
               "rendering": dict(edits).get("rendering", 0), "ready": dict(edits).get("ready", 0)},
        jobs={"active": running, "last24h": dict(jobs)},
        posts={"by_status": posts, "scheduled": posts.get("scheduled", 0) + posts.get("queued", 0),
               "done": posts.get("published", 0) + posts.get("ready_manual", 0) + posts.get("exported", 0)},
        analytics=analytics,
        ai={"month_spend_usd": round(spend, 4), "budget_usd": budget, "calls_month": calls,
            "providers_enabled": [p["provider"] for p in provider_status(ctx.ws) if p["enabled"]]},
        storage_mb=_storage_mb(), alerts=alerts,
    )


@router.get("/audit", response_model=list[dict], summary="Auditoria de ações")
def audit(ctx: CtxDep, limit: int = 100) -> list[dict]:
    rows = ctx.session.exec(select(AuditLog).where(AuditLog.workspace_id == ctx.ws.id)
                            .order_by(AuditLog.created_at.desc()).limit(min(limit, 500)))
    return [r.model_dump() for r in rows]


@router.get("/ai/usage", response_model=list[dict], summary="Consumo de IA por chamada")
def ai_usage(ctx: CtxDep, limit: int = 100) -> list[dict]:
    rows = ctx.session.exec(select(AIUsage).where(AIUsage.workspace_id == ctx.ws.id)
                            .order_by(AIUsage.created_at.desc()).limit(min(limit, 500)))
    return [r.model_dump() for r in rows]


# ------------------------------------------------------------------ YouTube & tendências
@router.get("/youtube/search", response_model=list[dict], summary="Busca YouTube (Data API v3)")
def yt_search(ctx: CtxDep, q: str, order: str = "relevance", days: int = 0, max_results: int = 12) -> list[dict]:
    after = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ") if days else None
    try:
        return search(q, max_results, order, published_after=after)
    except YouTubeError as e:
        raise HTTPException(424, str(e)) from e


@router.get("/trends", response_model=list[TrendRead], summary="Tendências salvas")
def list_trends(ctx: CtxDep) -> list[TrendRead]:
    rows = ctx.session.exec(select(Trend).where(Trend.workspace_id == ctx.ws.id).order_by(Trend.fetched_at.desc()).limit(200))
    return [TrendRead.model_validate(t.model_dump()) for t in rows]


@router.post("/trends", response_model=TrendRead, status_code=status.HTTP_201_CREATED, summary="Registra tendência")
def add_trend(ctx: CtxDep, body: TrendIn) -> TrendRead:
    t = Trend(workspace_id=ctx.ws.id, **body.model_dump())
    ctx.session.add(t)
    ctx.session.commit()
    ctx.session.refresh(t)
    return TrendRead.model_validate(t.model_dump())


@router.post("/trends/youtube", response_model=list[TrendRead], status_code=status.HTTP_201_CREATED,
             summary="Importa 'Em alta' do YouTube (região) como tendências")
def import_youtube_trending(ctx: CtxDep, region: str = "BR") -> list[TrendRead]:
    try:
        items = trending(region[:2].upper())
    except YouTubeError as e:
        raise HTTPException(424, str(e)) from e
    out = []
    for it in items:
        t = Trend(workspace_id=ctx.ws.id, source="youtube_api", region=region, kind="video", label=it["title"][:200],
                  url=it["url"], confidence=0.9, license_note="referência: não reutilize sem autorização",
                  metric={"views": it["views"], "likes": it["likes"], "comments": it["comments"],
                          "channel": it["channel"], "tags": it["tags"], "duration_s": it["duration_s"]})
        ctx.session.add(t)
        out.append(t)
    ctx.session.commit()
    return [TrendRead.model_validate(t.model_dump()) for t in out]


@router.delete("/trends/{trend_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove tendência")
def del_trend(ctx: CtxDep, trend_id: int) -> None:
    ctx.session.delete(ctx.get_owned(Trend, trend_id))
    ctx.session.commit()


@router.post("/trends/ideas", response_model=list[dict], summary="Ideias editoriais a partir de tendências + nicho")
def ideas(ctx: CtxDep, body: dict) -> list[dict]:
    niche = str(body.get("niche", "geral"))[:80]
    labels = [str(x)[:200] for x in body.get("topics", [])][:8]
    if not labels:
        labels = [t.label for t in ctx.session.exec(select(Trend).where(Trend.workspace_id == ctx.ws.id)
                                                    .order_by(Trend.fetched_at.desc()).limit(5))]
    if not labels:
        raise HTTPException(422, "informe topics ou importe tendências")
    for provider in route(ctx.ws, "copywriting"):
        try:
            d = call_json(ctx.session, ctx.ws, provider, "ideas",
                          "Estrategista de conteúdo curto PT-BR. Ideias originais e transformadoras; nada de repost. JSON.",
                          f"Nicho: {niche}\nTemas: {labels}\nJSON: {{\"ideas\": [{{\"angle\",\"hook\",\"audience\",\"format\","
                          "\"duration_s\",\"title\",\"cta\",\"hashtags\",\"originality\"}}]}} (máx 6)", 1500)
            return [dict(i, source=f"llm:{provider}") for i in d.get("ideas", [])][:6]
        except AIError:
            continue
    out = []
    for lab in labels[:6]:
        kw = lab.split(" ")[:4]
        out.append({"angle": f"Sua opinião/análise sobre '{lab}' aplicada a {niche}",
                    "hook": f"Ninguém está falando disso sobre {' '.join(kw)}…",
                    "audience": f"público de {niche} no Brasil", "format": "falando para câmera + legenda dinâmica",
                    "duration_s": 45, "title": f"O que '{lab[:50]}' ensina sobre {niche}",
                    "cta": "Comenta sua opinião 👇", "hashtags": [to_tag(niche), *(to_tag(k) for k in kw if len(k) > 3)][:4],
                    "originality": "alta: comentário próprio, não reupload", "source": "heuristic"})
    return out
