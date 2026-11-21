"""Agendamento interno, cadência (limites + anti-spam), proteção contra duplicados e adaptadores.

Adaptadores: assisted (kit p/ publicar manualmente no navegador), export (pasta pronta),
api (oficial: TikTok Content Posting / Instagram Graph / Facebook Reels — exige OAuth aprovado; Fase 4).
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta

from sqlmodel import Session, select

from .config import get_settings
from .jobqueue import JobCtl, enqueue, paused_workspaces
from .models import AuditLog, EditedClip, Job, ScheduledPost, SocialAccount, Workspace, utcnow
from .security import data_file, rel_data, ws_settings

log = logging.getLogger(__name__)
LIVE = ("scheduled", "queued", "publishing", "ready_manual", "exported", "published")
UPLOAD_URLS = {
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/reels/create",
    "youtube": "https://studio.youtube.com/",
}


class PostError(ValueError):
    pass


def content_hash(clip: EditedClip) -> str:
    p = data_file(clip.output_path)
    h = hashlib.sha256(f"{clip.video_id}:{clip.start_s:.1f}:{clip.end_s:.1f}".encode())
    if p:
        h.update(str(p.stat().st_size).encode())
    return h.hexdigest()


def effective_cap(session: Session, acc: SocialAccount) -> int:
    """Reduz cadência sozinho: falhas/bloqueios recentes cortam o limite pela metade."""
    recent = session.exec(select(ScheduledPost).where(ScheduledPost.account_id == acc.id)
                          .order_by(ScheduledPost.scheduled_at.desc()).limit(6)).all()
    bad = sum(1 for p in recent if p.status in ("failed", "blocked"))
    cap = max(1, int(acc.daily_cap))
    return max(1, cap // 2) if bad >= 2 else cap


def _local_hour(dt: datetime, tz: float) -> float:
    t = dt + timedelta(hours=tz)
    return t.hour + t.minute / 60


def next_slots(session: Session, ws: Workspace, acc: SocialAccount, n: int = 1, after: datetime | None = None,
               exclude_post: int | None = None) -> list[datetime]:
    cad = ws_settings(ws)["cadence"]
    gap = timedelta(minutes=int(cad["min_gap_minutes"]))
    tz, qs, qe = float(cad["tz_offset_h"]), float(cad["quiet_start"]), float(cad["quiet_end"])
    taken = sorted(p.scheduled_at for p in session.exec(
        select(ScheduledPost).where(ScheduledPost.account_id == acc.id, ScheduledPost.status.in_(LIVE)))
        if p.id != exclude_post)
    cap = effective_cap(session, acc)
    t = max(after or utcnow(), utcnow()) + timedelta(minutes=1)
    t = t.replace(second=0, microsecond=0)
    out: list[datetime] = []
    for _ in range(24 * 60 // 15 * 14):  # varre até 14 dias em passos de 15 min
        if len(out) >= n:
            break
        h = _local_hour(t, tz)
        quiet = (qs <= h < qe) if qs <= qe else (h >= qs or h < qe)
        day = (t + timedelta(hours=tz)).date()
        same_day = [x for x in [*taken, *out] if (x + timedelta(hours=tz)).date() == day]
        near = any(abs((x - t).total_seconds()) < gap.total_seconds() for x in [*taken, *out])
        if not quiet and not near and len(same_day) < cap:
            out.append(t)
        t += timedelta(minutes=15)
    return out


def create_post(session: Session, ws: Workspace, clip: EditedClip, acc: SocialAccount, when: datetime | None,
                caption: str, hashtags: list[str], title: str, mode: str) -> ScheduledPost:
    if clip.status != "ready" or not data_file(clip.output_path):
        raise PostError("corte ainda não renderizado (render final)")
    if acc.status == "paused":
        raise PostError("conta pausada")
    if mode == "api" and acc.status != "connected":
        raise PostError("conta sem OAuth oficial conectado; use modo assistido ou exportação")
    h = content_hash(clip)
    dup = session.exec(select(ScheduledPost).where(ScheduledPost.account_id == acc.id, ScheduledPost.status.in_(LIVE),
                                                   (ScheduledPost.edited_clip_id == clip.id) | (ScheduledPost.content_hash == h))).first()
    if dup:
        raise PostError(f"duplicado: este corte já está na conta (post {dup.id})")
    slots = next_slots(session, ws, acc, 1, after=when - timedelta(minutes=1) if when else None)
    if not slots:
        raise PostError("sem horário livre nos próximos 14 dias (limite diário/intervalo)")
    slot = slots[0]
    autonomous = ws_settings(ws)["autonomy"] == "autonomous"
    post = ScheduledPost(workspace_id=ws.id, edited_clip_id=clip.id, account_id=acc.id, platform=acc.platform,
                         title=title[:150], caption=caption[:5000], hashtags=hashtags[:30], scheduled_at=slot,
                         mode=mode, approved=autonomous, content_hash=h)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def scheduler_tick(session: Session) -> int:
    """Promove posts aprovados e vencidos para a fila. Respeita pausa global."""
    paused, now, n = paused_workspaces(session), utcnow(), 0
    for post in session.exec(select(ScheduledPost).where(ScheduledPost.status == "scheduled",
                                                         ScheduledPost.approved.is_(True),
                                                         ScheduledPost.scheduled_at <= now)):
        if post.workspace_id in paused:
            continue
        post.status = "queued"
        session.add(post)
        session.commit()
        enqueue(session, post.workspace_id, "publish", post.id)
        n += 1
    return n


def _export(post: ScheduledPost, clip: EditedClip, acc: SocialAccount) -> str:
    base = get_settings().data_dir / "exports" / acc.platform / acc.handle.strip("@").replace("/", "_")
    d = base / f"{post.scheduled_at:%Y-%m-%d_%H%M}_post{post.id}"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(data_file(clip.output_path), d / "video.mp4")
    for attr, name in (("cover_path", "cover.jpg"), ("srt_path", "legenda.srt")):
        p = data_file(getattr(clip, attr))
        if p:
            shutil.copy2(p, d / name)
    (d / "caption.txt").write_text(post.caption, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"platform": acc.platform, "account": acc.handle, "title": post.title,
                                             "hashtags": post.hashtags, "scheduled_at": post.scheduled_at.isoformat(),
                                             "upload_url": UPLOAD_URLS.get(acc.platform)}, ensure_ascii=False, indent=2))
    return rel_data(d)


def run_publish(session: Session, job: Job, ctl: JobCtl) -> dict:
    post = session.get(ScheduledPost, job.ref_id)
    if post.status == "canceled":
        return {"skipped": "cancelado"}
    clip, acc = session.get(EditedClip, post.edited_clip_id), session.get(SocialAccount, post.account_id)
    ctl.progress(0.2, "preparando")
    post.status = "publishing"
    session.add(post)
    session.commit()
    if post.mode == "api":
        # Integração oficial exige app aprovado (TikTok audit / Meta App Review) + OAuth. Não implementada na v1.
        post.status = "blocked"
        post.error = "Publicação via API oficial pendente (Fase 4): exige app aprovado + OAuth. Use assistido/exportar."
    else:
        post.export_dir = _export(post, clip, acc)
        post.status = "ready_manual" if post.mode == "assisted" else "exported"
        post.error = None
    session.add(post)
    session.add(AuditLog(workspace_id=post.workspace_id, actor="agent", action=f"publish_{post.status}",
                         target=f"post:{post.id}", detail={"platform": post.platform, "mode": post.mode}))
    session.commit()
    return {"status": post.status, "export_dir": post.export_dir}
