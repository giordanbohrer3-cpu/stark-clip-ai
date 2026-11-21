"""Estúdio: edição do corte, render (prévia/final), arquivos e textos de publicação."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import select

from ..copywriter import generate_copy
from ..jobqueue import enqueue
from ..models import ClipCandidate, EditedClip, EditedClipRead, Job, JobRead, SourceVideo, utcnow
from ..pipeline import get_words, rights_ok
from ..schemas import EditPatch, RenderIn
from ..security import CtxDep, data_file, require_role
from .videos import clip_read

router = APIRouter(prefix="/clips", tags=["estúdio"])
FILES = {"output": ("video/mp4", "corte.mp4"), "preview": ("video/mp4", "previa.mp4"),
         "srt": ("application/x-subrip", "legenda.srt"), "ass": ("text/plain", "legenda.ass"),
         "cover": ("image/jpeg", "capa.jpg")}


@router.get("", response_model=list[EditedClipRead], summary="Lista cortes editados")
def list_clips(ctx: CtxDep, state: str = "") -> list[EditedClipRead]:
    stmt = select(EditedClip).where(EditedClip.workspace_id == ctx.ws.id).order_by(EditedClip.updated_at.desc())
    if state:
        stmt = stmt.where(EditedClip.status == state)
    return [clip_read(c) for c in ctx.session.exec(stmt.limit(300))]


@router.get("/{clip_id}", response_model=EditedClipRead, summary="Detalhe do corte editado")
def get_clip(ctx: CtxDep, clip_id: int) -> EditedClipRead:
    return clip_read(ctx.get_owned(EditedClip, clip_id))


@router.get("/{clip_id}/context", summary="Dados p/ editor: palavras do trecho, candidato e vídeo")
def clip_context(ctx: CtxDep, clip_id: int) -> dict:
    ec = ctx.get_owned(EditedClip, clip_id)
    v = ctx.session.get(SourceVideo, ec.video_id)
    cand = ctx.session.get(ClipCandidate, ec.candidate_id)
    words = ec.words_override or [w for w in get_words(ctx.session, v) if w[1] > ec.start_s - 5 and w[0] < ec.end_s + 5]
    return {"words": words, "video": {"id": v.id, "title": v.title, "duration_s": v.duration_s, "width": v.width,
                                      "height": v.height, "niche": v.niche},
            "candidate": {"id": cand.id, "title": cand.title, "score": cand.score, "justification": cand.justification,
                          "start_s": cand.start_s, "end_s": cand.end_s} if cand else None,
            "caption_defaults": ctx.settings["captions"]}


@router.patch("/{clip_id}", response_model=EditedClipRead, summary="Ajusta trecho, layout, legendas, áudio")
def patch_clip(ctx: CtxDep, clip_id: int, body: EditPatch) -> EditedClipRead:
    require_role(ctx, "owner", "editor")
    ec = ctx.get_owned(EditedClip, clip_id)
    v = ctx.session.get(SourceVideo, ec.video_id)
    data = body.model_dump(exclude_none=True)
    for k, val in data.items():
        setattr(ec, k, val)
    if ec.end_s <= ec.start_s or ec.end_s > v.duration_s + 0.5 or ec.end_s - ec.start_s > 600:
        raise HTTPException(422, "intervalo inválido (máx 10 min)")
    if "words_override" in data:
        for w in ec.words_override:
            if len(w) < 3 or not isinstance(w[2], str) or float(w[1]) < float(w[0]):
                raise HTTPException(422, "palavras devem ser [início, fim, texto]")
    if any(k in data for k in ("start_s", "end_s", "layout", "remove_pauses", "denoise", "logo", "caption_style",
                               "words_override")) and ec.status == "ready":
        ec.status = "draft"  # mudou: precisa novo render
    ec.updated_at = utcnow()
    ctx.session.add(ec)
    ctx.audit("clip_update", f"clip:{ec.id}", fields=list(data))
    ctx.session.commit()
    ctx.session.refresh(ec)
    return clip_read(ec)


@router.post("/{clip_id}/render", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED,
             summary="Enfileira render (prévia baixa resolução ou final 1080x1920)")
def render(ctx: CtxDep, clip_id: int, body: RenderIn) -> JobRead:
    require_role(ctx, "owner", "editor")
    ec = ctx.get_owned(EditedClip, clip_id)
    if not rights_ok(ctx.session, ctx.session.get(SourceVideo, ec.video_id)):
        raise HTTPException(403, "sem autorização de uso válida")
    job = enqueue(ctx.session, ctx.ws.id, "render", ec.id, {"preview": body.preview})
    ctx.audit("render_queued", f"clip:{ec.id}", preview=body.preview, job=job.id)
    ctx.session.commit()
    return JobRead.model_validate(job.model_dump())


@router.get("/{clip_id}/jobs", response_model=list[JobRead], summary="Jobs de render do corte")
def clip_jobs(ctx: CtxDep, clip_id: int) -> list[JobRead]:
    ctx.get_owned(EditedClip, clip_id)
    rows = ctx.session.exec(select(Job).where(Job.kind == "render", Job.ref_id == clip_id)
                            .order_by(Job.created_at.desc()).limit(10))
    return [JobRead.model_validate(j.model_dump()) for j in rows]


@router.get("/{clip_id}/file/{kind}", summary="Baixa MP4/prévia/SRT/ASS/capa")
def clip_file(ctx: CtxDep, clip_id: int, kind: Literal["output", "preview", "srt", "ass", "cover"],
              download: bool = False) -> FileResponse:
    ec = ctx.get_owned(EditedClip, clip_id)
    p = data_file(getattr(ec, f"{kind}_path"))
    if not p:
        raise HTTPException(404, "arquivo ainda não gerado")
    mime, name = FILES[kind]
    return FileResponse(p, media_type=mime, filename=f"stark_{clip_id}_{name}" if download else None)


@router.post("/{clip_id}/copy", response_model=EditedClipRead, summary="(Re)gera título, legendas e hashtags")
def regen_copy(ctx: CtxDep, clip_id: int) -> EditedClipRead:
    ec = ctx.get_owned(EditedClip, clip_id)
    cand = ctx.session.get(ClipCandidate, ec.candidate_id)
    v = ctx.session.get(SourceVideo, ec.video_id)
    text = " ".join(w[2] for w in ec.words_override) if ec.words_override else cand.transcript_text
    ec.copy_text = generate_copy(ctx.session, ctx.ws, cand.title, text, cand.keywords, v.niche)
    ctx.session.add(ec)
    ctx.audit("copy_generated", f"clip:{ec.id}", source=ec.copy_text.get("source"))
    ctx.session.commit()
    ctx.session.refresh(ec)
    return clip_read(ec)
