"""Handlers dos jobs: analyze (transcrição -> 3 cortes) e render (edição -> MP4/SRT/ASS/capa)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlmodel import Session, delete, select

from . import media
from .ai.planner import llm_plan
from .ai.providers import AIError
from .clipper import ClipAnalyzer, pad_bounds
from .config import get_settings
from .copywriter import generate_copy
from .jobqueue import JobCtl, enqueue
from .models import (
    AuditLog,
    ClipCandidate,
    EditedClip,
    Job,
    RightsGrant,
    SourceVideo,
    Transcript,
    Workspace,
    utcnow,
)
from .render import RenderSpec, render_clip
from .security import data_file, deep_merge, rel_data, ws_settings

log = logging.getLogger(__name__)


class PermissionDenied(RuntimeError):
    pass


def rights_ok(session: Session, video: SourceVideo) -> RightsGrant | None:
    now = utcnow()
    for g in session.exec(select(RightsGrant).where(RightsGrant.video_id == video.id)):
        if g.allows_edit and (g.expires_at is None or g.expires_at > now):
            return g
    return None


def video_dir(video: SourceVideo) -> Path:
    d = get_settings().data_dir / "media" / str(video.id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_words(session: Session, video: SourceVideo) -> list:
    tr = session.exec(select(Transcript).where(Transcript.video_id == video.id)
                      .order_by(Transcript.created_at.desc())).first()
    return tr.words if tr else []


def _audit(session: Session, ws_id: int, action: str, target: str, **detail) -> None:
    session.add(AuditLog(workspace_id=ws_id, actor="agent", action=action, target=target, detail=detail))


def run_analyze(session: Session, job: Job, ctl: JobCtl) -> dict:
    video = session.get(SourceVideo, job.ref_id)
    ws = session.get(Workspace, video.workspace_id)
    if not rights_ok(session, video):
        raise PermissionDenied("sem autorização de uso válida para este vídeo")
    src = data_file(video.file_path)
    if not src:
        raise FileNotFoundError("arquivo original ausente")
    if not video.has_audio:
        raise media.MediaError("vídeo sem áudio: transcrição impossível")
    s, cfg = get_settings(), ws_settings(ws)
    video.status = "analyzing"
    session.add(video)
    session.commit()

    vdir = video_dir(video)
    ctl.progress(0.02, "extraindo áudio")
    wav = media.extract_audio(src, vdir / "audio16k.wav")
    tr = session.exec(select(Transcript).where(Transcript.file_hash == video.file_hash,
                                               Transcript.model == s.whisper_model)).first()
    if tr and tr.video_id != video.id:  # cache entre vídeos idênticos
        tr = Transcript(**{**tr.model_dump(exclude={"id", "created_at"}), "video_id": video.id})
        session.add(tr)
        session.commit()
    if not tr:
        from .transcribe import transcribe

        ctl.progress(0.05, "transcrevendo (local)")
        data = transcribe(wav, video.duration_s, on_progress=lambda f: ctl.progress(0.05 + 0.6 * f, "transcrevendo (local)"))
        tr = Transcript(video_id=video.id, file_hash=video.file_hash, model=data["model"], language=data["language"],
                        text=data["text"], words=data["words"], segments=data["segments"])
        session.add(tr)
        session.commit()
    if ctl.should_cancel():
        raise media.Canceled("cancelado")

    ctl.progress(0.7, "detectando cenas")
    scenes_file = vdir / "scenes.json"
    if scenes_file.exists():
        scenes = json.loads(scenes_file.read_text())
    else:
        scenes = media.detect_scenes(src)
        scenes_file.write_text(json.dumps(scenes))
    ctl.progress(0.8, "pontuando momentos")
    mode = job.payload.get("mode") or cfg["clips"]["mode"]
    target = int(cfg["clips"]["target"])
    an = ClipAnalyzer(tr.words, video.duration_s, media.audio_energy(wav), scenes, mode)
    whole = bool(job.payload.get("whole"))
    chosen, note = ([], "") if whole else an.select(target, float(cfg["clips"]["min_score"]))
    picks = [(w, {"source": "heuristic"}) for w in chosen]
    ai_note = ""
    try:
        if cfg["ai"]["routing"]["cut_planning"] != "heuristic" and not whole:
            ctl.progress(0.88, "refinando com IA")
            hints = sorted(an.candidates(), key=lambda w: w.score, reverse=True)
            picks = llm_plan(session, ws, an, hints, target) or picks
    except AIError as e:
        ai_note = f"IA indisponível ({e}); heurística usada"

    # substitui candidatos antigos não aprovados e sem edição
    edited_ids = {e.candidate_id for e in session.exec(select(EditedClip).where(EditedClip.video_id == video.id))}
    session.exec(delete(ClipCandidate).where(ClipCandidate.video_id == video.id, ClipCandidate.status == "candidate",
                                             ClipCandidate.id.not_in(edited_ids or {-1})))
    created = []
    for rank, (w, meta) in enumerate(picks, 1):
        d = an.describe(w)
        st, en = pad_bounds(w, video.duration_s)
        c = ClipCandidate(video_id=video.id, rank=rank, start_s=round(st, 2), end_s=round(en, 2),
                          title=meta.get("title") or d["title"], summary=meta.get("summary") or d["summary"],
                          justification=meta.get("justification") or d["justification"], hook=d["hook"],
                          score=w.score, score_breakdown=w.features, keywords=w.keywords,
                          transcript_text=d["transcript_text"], source=meta["source"])
        session.add(c)
        created.append(c)
    if whole:  # clipe do radar já é o momento: 1 corte com o vídeo inteiro
        desc = an.describe(an.window(0, len(an.sents) - 1)) if an.sents else {}
        hint = str(job.payload.get("hint") or "")
        c = ClipCandidate(video_id=video.id, rank=1, start_s=0.0, end_s=round(video.duration_s, 2),
                          title=(desc.get("title") or hint or video.title)[:90], summary=desc.get("summary", ""),
                          justification=f"Pico no chat ao vivo (score {job.payload.get('score', '?')})",
                          hook=desc.get("hook", ""), score=float(job.payload.get("score") or 0),
                          transcript_text=desc.get("transcript_text", ""), source="radar")
        session.add(c)
        created.append(c)
    video.status, video.error = "ready", None
    session.add(video)
    _audit(session, ws.id, "analysis_done", f"video:{video.id}", cuts=len(created), note=note, ai=ai_note)
    session.commit()

    if cfg["autonomy"] in ("semi", "autonomous") or job.payload.get("auto_render"):  # publicação segue regras
        for c in created:
            session.refresh(c)
            ec = new_edit(session, video, c)
            ec.layout = str(job.payload.get("layout") or ec.layout)
            ec.remove_pauses = not whole
            ec.caption_style = {"title": c.title, "credit": str(job.payload.get("credit") or "")}
            session.add(ec)
            session.commit()
            enqueue(session, ws.id, "render", ec.id, {"preview": False})
        _audit(session, ws.id, "auto_render_queued", f"video:{video.id}", n=len(created))
        session.commit()
    return {"candidates": len(created), "note": note, "ai_note": ai_note, "bounds": [an.lo, an.hi],
            "sentences": len(an.sents), "language": tr.language}


def new_edit(session: Session, video: SourceVideo, cand: ClipCandidate) -> EditedClip:
    ec = EditedClip(workspace_id=video.workspace_id, candidate_id=cand.id, video_id=video.id,
                    start_s=cand.start_s, end_s=cand.end_s)
    session.add(ec)
    session.commit()
    session.refresh(ec)
    return ec


def run_render(session: Session, job: Job, ctl: JobCtl) -> dict:
    ec = session.get(EditedClip, job.ref_id)
    video = session.get(SourceVideo, ec.video_id)
    ws = session.get(Workspace, ec.workspace_id)
    if not rights_ok(session, video):
        raise PermissionDenied("sem autorização de uso válida para este vídeo")
    src = data_file(video.file_path)
    if not src:
        raise FileNotFoundError("arquivo original ausente")
    cfg = ws_settings(ws)
    preview = bool(job.payload.get("preview"))
    words = ec.words_override or get_words(session, video)
    br = cfg["branding"]
    spec = RenderSpec(start=ec.start_s, end=ec.end_s, layout=ec.layout, remove_pauses=ec.remove_pauses,
                      denoise=ec.denoise, logo_path=data_file(br.get("logo_path")) if ec.logo else None,
                      logo_opacity=float(br.get("logo_opacity", 0.9)), logo_scale=float(br.get("logo_scale", 0.14)),
                      style=deep_merge(cfg["captions"], ec.caption_style or {}))
    ec.status = "rendering"
    session.add(ec)
    session.commit()
    out_dir = get_settings().data_dir / "clips" / str(ec.id)
    info = {"width": video.width, "height": video.height, "has_audio": video.has_audio}
    res = render_clip(src, info, words, spec, out_dir, preview, ctl.progress, ctl.should_cancel)
    session.refresh(ec)
    if preview:
        ec.preview_path = rel_data(res["video"])
    else:
        ec.output_path, ec.cover_path = rel_data(res["video"]), rel_data(res["cover"])
        ec.status = "ready"
        if not ec.copy_text:
            cand = session.get(ClipCandidate, ec.candidate_id)
            ec.copy_text = generate_copy(session, ws, cand.title, cand.transcript_text, cand.keywords, video.niche)
    ec.srt_path, ec.ass_path = rel_data(res["srt"]), rel_data(res["ass"])
    ec.duration_s, ec.layout_used, ec.error, ec.updated_at = res["duration"], res["layout"], None, utcnow()
    if preview and ec.status == "rendering":
        ec.status = "draft" if not ec.output_path else "ready"
    session.add(ec)
    _audit(session, ws.id, "render_done", f"clip:{ec.id}", preview=preview, layout=res["layout"],
           duration=res["duration"])
    if not preview:  # momento do radar vira "pronto" no feed
        from .models import LiveMoment

        for m in session.exec(select(LiveMoment).where(LiveMoment.video_id == video.id)):
            m.status = "ready"
            session.add(m)
    session.commit()
    return {"duration": res["duration"], "layout": res["layout"], "plan": res["plan"], "preview": preview}
