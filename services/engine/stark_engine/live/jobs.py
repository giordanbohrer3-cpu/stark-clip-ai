"""Jobs da máquina de clipes: clipe Twitch de canal autorizado e importação de campanha por link."""
from __future__ import annotations

import logging
import time

from sqlmodel import Session, select

from .. import media
from ..config import get_settings
from ..importer import ImportError_, download
from ..jobqueue import JobCtl, enqueue
from ..models import AuditLog, ChannelGrant, Job, LiveMoment, RightsGrant, SourceVideo, User, Workspace
from ..pipeline import PermissionDenied, video_dir
from ..security import rel_data
from . import twitch

log = logging.getLogger(__name__)


def _owner(session: Session, ws_id: int) -> int:
    u = session.exec(select(User).where(User.workspace_id == ws_id, User.role == "owner")).first()
    return u.id if u else 1


def register_file(session: Session, video: SourceVideo, path, grant: dict, declared_by: int) -> SourceVideo:
    """Valida o arquivo baixado e grava metadados + autorização (RightsGrant)."""
    try:
        info = media.probe(path)
    except media.MediaError:
        path.unlink(missing_ok=True)
        raise
    video.file_path, video.size_bytes, video.file_hash = rel_data(path), path.stat().st_size, media.file_hash(path)
    video.duration_s, video.width, video.height = info["duration"], info["width"], info["height"]
    video.fps, video.has_audio, video.status = info["fps"], info["has_audio"], "uploaded"
    try:
        media.grab_frame(path, min(info["duration"] * 0.3, 10), video_dir(video) / "thumb.jpg", width=480)
    except Exception as e:  # noqa: BLE001 - miniatura é opcional
        log.warning("miniatura falhou: %s", e)
    session.add(RightsGrant(workspace_id=video.workspace_id, video_id=video.id, declared_by=declared_by, **grant))
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


def run_twitch_clip(session: Session, job: Job, ctl: JobCtl) -> dict:
    moment = session.get(LiveMoment, job.ref_id)
    ws = session.get(Workspace, moment.workspace_id)
    grant = session.exec(select(ChannelGrant).where(ChannelGrant.workspace_id == ws.id, ChannelGrant.active.is_(True),
                                                    ChannelGrant.channel == moment.channel)).first()
    if not grant:
        moment.status, moment.error = "skipped", "canal sem autorização"
        session.add(moment)
        session.commit()
        raise PermissionDenied("canal sem autorização registrada")
    token, editor_id = twitch.user_token(session, ws.id)
    if not grant.broadcaster_id:
        grant.broadcaster_id = twitch.user_ids([grant.channel]).get(grant.channel)
        session.add(grant)
        session.commit()
    ctl.progress(0.05, "criando clipe na Twitch")
    clip_id = moment.clip_id or twitch.create_clip(token, grant.broadcaster_id)
    moment.clip_id, moment.status = clip_id, "clipping"
    session.add(moment)
    session.commit()

    url = None
    for i in range(18):  # a Twitch leva ~15–60 s para processar o clipe
        ctl.progress(0.1 + i * 0.02, "aguardando a Twitch processar")
        try:
            url = twitch.clip_download_url(token, editor_id, grant.broadcaster_id, clip_id)
        except twitch.TwitchError as e:
            if "403" in str(e):
                raise PermissionDenied("você não é editor deste canal na Twitch: peça ao streamer") from e
            raise
        if url:
            break
        time.sleep(5)
    if not url:
        raise twitch.TwitchError("clipe não ficou pronto a tempo")

    video = SourceVideo(workspace_id=ws.id, title=f"{grant.display_name or grant.channel} · momento",
                        origin="twitch_clip", channel=grant.channel, url=f"https://clips.twitch.tv/{clip_id}",
                        niche="GTA VI")
    session.add(video)
    session.commit()
    session.refresh(video)
    dst = video_dir(video) / "original.mp4"
    ctl.progress(0.5, "baixando clipe")
    download(url, dst, 800, lambda f: ctl.progress(0.5 + 0.3 * f, "baixando clipe"))
    register_file(session, video, dst, {"rights_type": grant.rights_type, "holder": grant.channel,
                                        "evidence": grant.evidence or "editor na Twitch",
                                        "allows_commercial": grant.allows_commercial}, _owner(session, ws.id))
    moment.video_id, moment.status = video.id, "processing"
    session.add(moment)
    session.add(AuditLog(workspace_id=ws.id, actor="agent", action="twitch_clip", target=f"moment:{moment.id}",
                         detail={"clip_id": clip_id, "channel": grant.channel}))
    session.commit()
    hook = " ".join(moment.tokens[:3]).upper() if moment.tokens else ""
    enqueue(session, ws.id, "analyze", video.id, {"whole": True, "auto_render": True, "layout": "stream",
                                                   "credit": f"twitch.tv/{grant.channel}", "hint": hook,
                                                   "score": moment.score, "moment_id": moment.id})
    return {"clip_id": clip_id, "video_id": video.id}


def run_import_url(session: Session, job: Job, ctl: JobCtl) -> dict:
    p = job.payload
    ws = session.get(Workspace, job.workspace_id)
    video = session.get(SourceVideo, job.ref_id)
    dst = video_dir(video) / "original.mp4"
    try:
        download(p["url"], dst, get_settings().max_upload_mb, lambda f: ctl.progress(0.05 + 0.8 * f, "baixando"))
    except ImportError_ as e:
        video.status, video.error = "error", str(e)
        session.add(video)
        session.commit()
        raise ValueError(str(e)) from e
    register_file(session, video, dst, {"rights_type": "licensed", "holder": p.get("campaign") or "campanha",
                                        "evidence": p.get("evidence") or p["url"],
                                        "allows_commercial": bool(p.get("allows_commercial", True))},
                  p.get("user_id") or _owner(session, ws.id))
    enqueue(session, ws.id, "analyze", video.id, {"auto_render": True, "layout": p.get("layout", "auto"),
                                                   "credit": p.get("credit", "")})
    return {"video_id": video.id, "size": dst.stat().st_size}
