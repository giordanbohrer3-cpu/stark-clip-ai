"""Vídeos-fonte, direitos, transcrição e candidatos a corte."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from secrets import token_urlsafe as random_id
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlmodel import Session, delete, select
from starlette.concurrency import run_in_threadpool

from .. import media
from ..ai.planner import apply_cuts, operator_request
from ..clipper import ClipAnalyzer, pad_bounds
from ..config import get_settings
from ..jobqueue import enqueue
from ..models import (
    ClipCandidate,
    ClipCandidateRead,
    EditedClip,
    EditedClipRead,
    Job,
    JobRead,
    RightsGrant,
    RightsGrantRead,
    ScheduledPost,
    SourceVideo,
    SourceVideoRead,
    Transcript,
)
from ..pipeline import get_words, new_edit, rights_ok, video_dir
from ..schemas import (
    CandidatePatch,
    CutsImport,
    ProcessIn,
    ReferenceIn,
    RightsIn,
    UploadInit,
    UploadSession,
    VideoDetail,
    VideoPatch,
)
from ..security import CtxDep, data_file, rel_data, require_role, safe_path, ws_settings
from ..youtube import YouTubeError, oembed, parse_id

router = APIRouter(prefix="/videos", tags=["videos"])
cand_router = APIRouter(prefix="/candidates", tags=["cortes"])
log = logging.getLogger(__name__)
RIGHTS = ("own", "licensed", "creator_permission", "public_domain", "cc_by")


def video_read(session: Session, v: SourceVideo) -> SourceVideoRead:
    r = SourceVideoRead.model_validate(v.model_dump())
    r.has_file, r.rights_ok = bool(v.file_path), bool(rights_ok(session, v))
    return r


def cand_read(c: ClipCandidate) -> ClipCandidateRead:
    r = ClipCandidateRead.model_validate(c.model_dump())
    r.duration_s = round(c.end_s - c.start_s, 2)
    return r


def clip_read(c: EditedClip) -> EditedClipRead:
    r = EditedClipRead.model_validate(c.model_dump())
    r.files = [k for k in ("output", "preview", "srt", "ass", "cover") if data_file(getattr(c, f"{k}_path"))]
    return r


@router.get("", response_model=list[SourceVideoRead], summary="Lista vídeos do workspace")
def list_videos(ctx: CtxDep, q: str = "", state: Annotated[str, Query(alias="status")] = "",
                favorite: bool | None = None) -> list[SourceVideoRead]:
    stmt = select(SourceVideo).where(SourceVideo.workspace_id == ctx.ws.id).order_by(SourceVideo.created_at.desc())
    if state:
        stmt = stmt.where(SourceVideo.status == state)
    rows = ctx.session.exec(stmt.limit(300)).all()
    if q:
        rows = [v for v in rows if q.lower() in (v.title + " " + (v.channel or "") + " " + v.niche).lower()]
    if favorite is not None:
        rows = [v for v in rows if v.favorite == favorite]
    return [video_read(ctx.session, v) for v in rows]


CHUNK = 48 * 1024 * 1024  # partes < 100 MB: retomável em rede instável e compatível com proxies/túneis
UPLOAD_ID = re.compile(r"^[A-Za-z0-9_-]{20,40}$")


def _ext(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in get_settings().allowed_ext:
        raise HTTPException(415, f"formato não suportado; use {', '.join(get_settings().allowed_ext)}")
    return ext


def _check_grant(rights_type: str, confirm: bool) -> None:
    if rights_type not in RIGHTS:
        raise HTTPException(422, f"rights_type deve ser um de {RIGHTS}")
    if not confirm:
        raise HTTPException(422, "confirme que você tem direito de uso deste material")


def _target_video(ctx, filename: str, title: str, niche: str, reference_id: int | None) -> tuple[SourceVideo, bool]:
    if reference_id:
        video = ctx.get_owned(SourceVideo, reference_id)
        if video.file_path:
            raise HTTPException(409, "referência já possui arquivo")
        return video, False
    video = SourceVideo(workspace_id=ctx.ws.id, title=title or filename or "vídeo", origin="upload", niche=niche)
    ctx.session.add(video)
    ctx.session.commit()
    ctx.session.refresh(video)
    return video, True


def _discard(ctx, video: SourceVideo, created: bool, dst: Path) -> None:
    dst.unlink(missing_ok=True)
    if created:
        shutil.rmtree(video_dir(video), ignore_errors=True)
        ctx.session.delete(video)
        ctx.session.commit()


def _finalize(ctx, video: SourceVideo, created: bool, dst: Path, size: int, grant: dict, title: str,
              niche: str) -> SourceVideoRead:
    s = get_settings()
    try:
        info = media.probe(dst)
    except media.MediaError as e:
        _discard(ctx, video, created, dst)
        raise HTTPException(422, f"arquivo inválido: {e}") from e
    if info["duration"] > s.max_duration_s:
        _discard(ctx, video, created, dst)
        raise HTTPException(422, f"duração acima do limite ({s.max_duration_s // 60} min)")
    video.file_path, video.size_bytes, video.file_hash = rel_data(dst), size, media.file_hash(dst)
    video.duration_s, video.width, video.height = info["duration"], info["width"], info["height"]
    video.fps, video.has_audio, video.status = info["fps"], info["has_audio"], "uploaded"
    if title:
        video.title = title
    if niche:
        video.niche = niche
    try:
        media.grab_frame(dst, min(info["duration"] * 0.1, 30), video_dir(video) / "thumb.jpg", width=480)
    except (OSError, subprocess.SubprocessError) as e:  # miniatura é opcional
        log.warning("miniatura falhou para vídeo %s: %s", video.id, e)
    ctx.session.add(RightsGrant(workspace_id=ctx.ws.id, video_id=video.id, declared_by=ctx.user.id, **grant))
    ctx.audit("video_upload", f"video:{video.id}", size=size, rights=grant["rights_type"], holder=grant["holder"])
    ctx.session.add(video)
    ctx.session.commit()
    ctx.session.refresh(video)
    return video_read(ctx.session, video)


@router.post("/upload", response_model=SourceVideoRead, status_code=status.HTTP_201_CREATED,
             summary="Envia arquivo original (requisição única) + declaração de direitos")
def upload(
    ctx: CtxDep, request: Request, file: Annotated[UploadFile, File()],
    rights_type: Annotated[str, Form()], holder: Annotated[str, Form(min_length=2, max_length=120)],
    confirm: Annotated[bool, Form()], title: Annotated[str, Form(max_length=200)] = "",
    niche: Annotated[str, Form(max_length=80)] = "", evidence: Annotated[str, Form(max_length=1000)] = "",
    allows_edit: Annotated[bool, Form()] = True, allows_commercial: Annotated[bool, Form()] = False,
    reference_id: Annotated[int | None, Form()] = None,
) -> SourceVideoRead:
    require_role(ctx, "owner", "editor")
    _check_grant(rights_type, confirm)
    ext = _ext(file.filename or "")
    limit = get_settings().max_upload_mb * 1024 * 1024
    if int(request.headers.get("content-length") or 0) > limit + 1024 * 1024:
        raise HTTPException(413, f"arquivo excede {get_settings().max_upload_mb} MB")
    video, created = _target_video(ctx, file.filename or "", title, niche, reference_id)
    dst = safe_path(video_dir(video), f"original{ext}")
    size = 0
    with dst.open("wb") as out:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                out.close()
                _discard(ctx, video, created, dst)
                raise HTTPException(413, f"arquivo excede {get_settings().max_upload_mb} MB")
            out.write(chunk)
    grant = {"rights_type": rights_type, "holder": holder, "evidence": evidence, "allows_edit": allows_edit,
             "allows_commercial": allows_commercial}
    return _finalize(ctx, video, created, dst, size, grant, title, niche)


# ------------------------------------------------------------------ upload em partes (celular / Cloudflare)
def _uploads_root() -> Path:
    root = get_settings().data_dir / "tmp" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _session_dir(ctx, upload_id: str) -> tuple[Path, dict]:
    if not UPLOAD_ID.match(upload_id):
        raise HTTPException(404, "upload não encontrado")
    d = safe_path(_uploads_root(), upload_id)
    meta_file = d / "meta.json"
    if not meta_file.exists():
        raise HTTPException(404, "upload não encontrado ou expirado")
    meta = json.loads(meta_file.read_text())
    if meta["workspace_id"] != ctx.ws.id or meta["user_id"] != ctx.user.id:
        raise HTTPException(404, "upload não encontrado")
    return d, meta


def _purge_stale(hours: int = 24) -> None:
    limit = time.time() - hours * 3600
    for d in _uploads_root().iterdir():
        if d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)


@router.post("/uploads", response_model=UploadSession, status_code=status.HTTP_201_CREATED,
             summary="Inicia upload em partes (cada parte < 100 MB)")
def init_upload(ctx: CtxDep, body: UploadInit) -> UploadSession:
    require_role(ctx, "owner", "editor")
    _check_grant(body.rights_type, body.confirm)
    _ext(body.filename)
    if body.size > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"arquivo excede {get_settings().max_upload_mb} MB")
    if body.reference_id:
        ref = ctx.get_owned(SourceVideo, body.reference_id)
        if ref.file_path:
            raise HTTPException(409, "referência já possui arquivo")
    _purge_stale()
    upload_id = random_id(18)
    d = safe_path(_uploads_root(), upload_id)
    d.mkdir()
    with (d / "data.bin").open("wb") as f:
        f.truncate(body.size)  # arquivo esparso: partes escrevem na posição certa, sem cópia final
    meta = {**body.model_dump(), "workspace_id": ctx.ws.id, "user_id": ctx.user.id, "created": time.time()}
    (d / "meta.json").write_text(json.dumps(meta))
    return UploadSession(upload_id=upload_id, chunk_size=CHUNK, chunks=-(-body.size // CHUNK))


@router.put("/uploads/{upload_id}/{index}", status_code=status.HTTP_204_NO_CONTENT,
            summary="Envia uma parte (corpo binário)")
async def put_chunk(ctx: CtxDep, upload_id: str, index: int, request: Request) -> None:
    d, meta = _session_dir(ctx, upload_id)
    chunks = -(-meta["size"] // CHUNK)
    if not 0 <= index < chunks:
        raise HTTPException(422, "índice de parte inválido")
    expected = min(CHUNK, meta["size"] - index * CHUNK)
    written = 0
    with (d / "data.bin").open("r+b") as f:
        f.seek(index * CHUNK)
        async for piece in request.stream():
            written += len(piece)
            if written > expected:
                raise HTTPException(413, "parte maior que o esperado")
            await run_in_threadpool(f.write, piece)
    if written != expected:
        raise HTTPException(422, f"parte incompleta ({written}/{expected} bytes)")
    (d / f"{index:05d}.ok").touch()


@router.post("/uploads/{upload_id}/complete", response_model=SourceVideoRead, status_code=status.HTTP_201_CREATED,
             summary="Finaliza upload em partes e registra direitos")
def complete_upload(ctx: CtxDep, upload_id: str) -> SourceVideoRead:
    d, meta = _session_dir(ctx, upload_id)
    chunks = -(-meta["size"] // CHUNK)
    missing = [i for i in range(chunks) if not (d / f"{i:05d}.ok").exists()]
    if missing:
        raise HTTPException(409, f"faltam partes: {missing[:10]}")
    video, created = _target_video(ctx, meta["filename"], meta["title"], meta["niche"], meta["reference_id"])
    dst = safe_path(video_dir(video), f"original{_ext(meta['filename'])}")
    os.replace(d / "data.bin", dst)  # mesmo disco: rename atômico
    shutil.rmtree(d, ignore_errors=True)
    grant = {k: meta[k] for k in ("rights_type", "holder", "evidence", "allows_edit", "allows_commercial")}
    return _finalize(ctx, video, created, dst, meta["size"], grant, meta["title"], meta["niche"])


@router.post("/reference", response_model=SourceVideoRead, status_code=status.HTTP_201_CREATED,
             summary="Adiciona referência do YouTube (metadados; não baixa)")
def add_reference(ctx: CtxDep, body: ReferenceIn) -> SourceVideoRead:
    try:
        vid = parse_id(body.url)
    except YouTubeError as e:
        raise HTTPException(422, str(e)) from e
    existing = ctx.session.exec(select(SourceVideo).where(SourceVideo.workspace_id == ctx.ws.id,
                                                          SourceVideo.youtube_id == vid)).first()
    if existing:
        return video_read(ctx.session, existing)
    try:
        meta = oembed(vid)
    except YouTubeError as e:
        raise HTTPException(404, str(e)) from e
    v = SourceVideo(workspace_id=ctx.ws.id, origin="youtube_ref", status="reference", niche=body.niche, **meta)
    ctx.session.add(v)
    ctx.audit("youtube_reference", vid)
    ctx.session.commit()
    ctx.session.refresh(v)
    return video_read(ctx.session, v)


@router.get("/{video_id}", response_model=VideoDetail, summary="Detalhe completo do vídeo")
def get_video(ctx: CtxDep, video_id: int) -> VideoDetail:
    v = ctx.get_owned(SourceVideo, video_id)
    s = ctx.session
    tr = s.exec(select(Transcript).where(Transcript.video_id == v.id).order_by(Transcript.created_at.desc())).first()
    jobs = s.exec(select(Job).where(Job.kind == "analyze", Job.ref_id == v.id).order_by(Job.created_at.desc()).limit(5)).all()
    clips = s.exec(select(EditedClip).where(EditedClip.video_id == v.id)).all()
    jobs += s.exec(select(Job).where(Job.kind == "render", Job.ref_id.in_([c.id for c in clips] or [-1]))
                   .order_by(Job.created_at.desc()).limit(20)).all()
    return VideoDetail(
        video=video_read(s, v),
        rights=[RightsGrantRead.model_validate(g.model_dump()) for g in
                s.exec(select(RightsGrant).where(RightsGrant.video_id == v.id))],
        candidates=[cand_read(c) for c in s.exec(select(ClipCandidate).where(ClipCandidate.video_id == v.id)
                                                 .order_by(ClipCandidate.rank))],
        clips=[clip_read(c) for c in clips],
        jobs=[JobRead.model_validate(j.model_dump()) for j in jobs],
        transcript={"language": tr.language, "model": tr.model, "words": len(tr.words), "text": tr.text[:20000],
                    "segments": tr.segments[:2000]} if tr else None,
    )


@router.patch("/{video_id}", response_model=SourceVideoRead, summary="Edita título/nicho/favorito")
def patch_video(ctx: CtxDep, video_id: int, body: VideoPatch) -> SourceVideoRead:
    v = ctx.get_owned(SourceVideo, video_id)
    for k, val in body.model_dump(exclude_none=True).items():
        setattr(v, k, val)
    ctx.session.add(v)
    ctx.session.commit()
    ctx.session.refresh(v)
    return video_read(ctx.session, v)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove vídeo e arquivos")
def delete_video(ctx: CtxDep, video_id: int) -> None:
    require_role(ctx, "owner")
    v = ctx.get_owned(SourceVideo, video_id)
    s = ctx.session
    clip_ids = [c.id for c in s.exec(select(EditedClip).where(EditedClip.video_id == v.id))]
    if clip_ids and s.exec(select(ScheduledPost).where(ScheduledPost.edited_clip_id.in_(clip_ids))).first():
        raise HTTPException(409, "há publicações ligadas a este vídeo; cancele-as antes")
    for cid in clip_ids:
        shutil.rmtree(get_settings().data_dir / "clips" / str(cid), ignore_errors=True)
    shutil.rmtree(get_settings().data_dir / "media" / str(v.id), ignore_errors=True)
    for model, col in ((EditedClip, EditedClip.video_id), (ClipCandidate, ClipCandidate.video_id),
                       (Transcript, Transcript.video_id), (RightsGrant, RightsGrant.video_id)):
        s.exec(delete(model).where(col == v.id))
    s.delete(v)
    ctx.audit("video_delete", f"video:{video_id}")
    s.commit()


@router.post("/{video_id}/rights", response_model=RightsGrantRead, status_code=status.HTTP_201_CREATED,
             summary="Registra autorização de uso")
def add_rights(ctx: CtxDep, video_id: int, body: RightsIn) -> RightsGrantRead:
    v = ctx.get_owned(SourceVideo, video_id)
    if not body.confirm:
        raise HTTPException(422, "confirme que você tem direito de uso deste material")
    g = RightsGrant(workspace_id=ctx.ws.id, video_id=v.id, declared_by=ctx.user.id,
                    **body.model_dump(exclude={"confirm"}))
    ctx.session.add(g)
    ctx.audit("rights_grant", f"video:{v.id}", rights=g.rights_type)
    ctx.session.commit()
    ctx.session.refresh(g)
    return RightsGrantRead.model_validate(g.model_dump())


@router.post("/{video_id}/process", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED,
             summary="Enfileira transcrição + seleção de cortes")
def process(ctx: CtxDep, video_id: int, body: ProcessIn | None = None) -> JobRead:
    require_role(ctx, "owner", "editor")
    v = ctx.get_owned(SourceVideo, video_id)
    if not v.file_path:
        raise HTTPException(409, "sem arquivo: referência do YouTube não é autorização. Envie o original.")
    if not rights_ok(ctx.session, v):
        raise HTTPException(403, "registre uma autorização de uso válida antes de processar")
    payload: dict = {"mode": body.mode} if body and body.mode else {}
    if body and body.auto_render:
        box = ctx.settings["inbox"]  # mesmo jeito da pasta de entrada
        payload.update(auto_render=True, layout=box.get("layout") or "auto", credit=box.get("credit") or "")
    job = enqueue(ctx.session, ctx.ws.id, "analyze", v.id, payload)
    v.status = "queued"
    ctx.session.add(v)
    ctx.audit("process_queued", f"video:{v.id}", job=job.id)
    ctx.session.commit()
    return JobRead.model_validate(job.model_dump())


@router.get("/{video_id}/media", summary="Stream do original (suporta Range)")
def video_media(ctx: CtxDep, video_id: int) -> FileResponse:
    v = ctx.get_owned(SourceVideo, video_id)
    p = data_file(v.file_path)
    if not p:
        raise HTTPException(404, "sem arquivo")
    return FileResponse(p, media_type="video/mp4")


@router.get("/{video_id}/thumb", summary="Miniatura")
def video_thumb(ctx: CtxDep, video_id: int) -> FileResponse:
    v = ctx.get_owned(SourceVideo, video_id)
    p = get_settings().data_dir / "media" / str(v.id) / "thumb.jpg"
    if not p.exists():
        raise HTTPException(404, "sem miniatura")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/{video_id}/transcript", summary="Palavras com timestamps")
def transcript(ctx: CtxDep, video_id: int) -> dict:
    v = ctx.get_owned(SourceVideo, video_id)
    return {"words": get_words(ctx.session, v)}


def analyzer_for(session: Session, v: SourceVideo, mode: str = "short") -> ClipAnalyzer:
    words = get_words(session, v)
    if not words:
        raise HTTPException(409, "processe o vídeo antes (sem transcrição)")
    vdir = video_dir(v)
    wav, sc = vdir / "audio16k.wav", vdir / "scenes.json"
    energy = media.audio_energy(wav) if wav.exists() else None
    scenes = json.loads(sc.read_text()) if sc.exists() else []
    return ClipAnalyzer(words, v.duration_s, energy, scenes, mode)


@router.get("/{video_id}/analysis-request", response_class=PlainTextResponse,
            summary="Modo Operador: prompt p/ Claude Code/Gemini CLI/Codex")
def analysis_request(ctx: CtxDep, video_id: int, mode: str = "short") -> str:
    v = ctx.get_owned(SourceVideo, video_id)
    an = analyzer_for(ctx.session, v, mode)
    hints = sorted(an.candidates(), key=lambda w: w.score, reverse=True)
    return operator_request(an, hints, int(ws_settings(ctx.ws)["clips"]["target"]), v.id)


@router.post("/{video_id}/cuts/import", response_model=list[ClipCandidateRead], status_code=status.HTTP_201_CREATED,
             summary="Modo Operador: importa cortes JSON validados")
def import_cuts(ctx: CtxDep, video_id: int, body: CutsImport, mode: str = "short") -> list[ClipCandidateRead]:
    v = ctx.get_owned(SourceVideo, video_id)
    if not rights_ok(ctx.session, v):
        raise HTTPException(403, "sem autorização de uso válida")
    an = analyzer_for(ctx.session, v, mode)
    picks = apply_cuts(an, body.cuts, int(ws_settings(ctx.ws)["clips"]["target"]), "operator")
    if not picks:
        raise HTTPException(422, "nenhum corte válido (índices/duração/sobreposição)")
    out = []
    for rank, (w, meta) in enumerate(picks, 1):
        d = an.describe(w)
        st, en = pad_bounds(w, v.duration_s)
        c = ClipCandidate(video_id=v.id, rank=100 + rank, start_s=round(st, 2), end_s=round(en, 2),
                          title=meta["title"] or d["title"], summary=meta["summary"] or d["summary"],
                          justification=meta["justification"] or d["justification"], hook=d["hook"], score=w.score,
                          score_breakdown=w.features, keywords=w.keywords, transcript_text=d["transcript_text"],
                          source="operator")
        ctx.session.add(c)
        out.append(c)
    ctx.audit("operator_cuts_import", f"video:{v.id}", n=len(out))
    ctx.session.commit()
    return [cand_read(c) for c in out]


# ------------------------------------------------------------------ candidatos
@cand_router.patch("/{cand_id}", response_model=ClipCandidateRead, summary="Aprova/rejeita/ajusta corte")
def patch_candidate(ctx: CtxDep, cand_id: int, body: CandidatePatch) -> ClipCandidateRead:
    c = ctx.session.get(ClipCandidate, cand_id)
    v = ctx.get_owned(SourceVideo, c.video_id) if c else None
    if not c or not v:
        raise HTTPException(404, "corte não encontrado")
    data = body.model_dump(exclude_none=True)
    for k, val in data.items():
        setattr(c, k, val)
    if c.end_s <= c.start_s or c.end_s > v.duration_s + 0.5:
        raise HTTPException(422, "intervalo inválido")
    ctx.session.add(c)
    ctx.audit("candidate_update", f"cand:{c.id}", **data)
    ctx.session.commit()
    ctx.session.refresh(c)
    return cand_read(c)


@cand_router.post("/{cand_id}/expand", response_model=ClipCandidateRead, status_code=status.HTTP_201_CREATED,
                  summary="Cria versão longa (>60s) do corte, mantendo frases inteiras")
def expand_candidate(ctx: CtxDep, cand_id: int) -> ClipCandidateRead:
    c = ctx.session.get(ClipCandidate, cand_id)
    v = ctx.get_owned(SourceVideo, c.video_id) if c else None
    if not c or not v:
        raise HTTPException(404, "corte não encontrado")
    an = analyzer_for(ctx.session, v, "long")
    try:
        w = an.expand(c.start_s, c.end_s)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if w.duration < 55:
        raise HTTPException(422, "vídeo sem contexto suficiente para versão longa")
    d = an.describe(w)
    st, en = pad_bounds(w, v.duration_s)
    n = ClipCandidate(video_id=v.id, rank=c.rank + 50, start_s=round(st, 2), end_s=round(en, 2),
                      title=c.title, summary=d["summary"], justification="Versão longa: " + d["justification"],
                      hook=d["hook"], score=w.score, score_breakdown=w.features, keywords=w.keywords,
                      transcript_text=d["transcript_text"], source=c.source + "+long")
    ctx.session.add(n)
    ctx.session.commit()
    ctx.session.refresh(n)
    return cand_read(n)


@cand_router.post("/{cand_id}/edit", response_model=EditedClipRead, status_code=status.HTTP_201_CREATED,
                  summary="Abre corte no estúdio (cria edição)")
def edit_candidate(ctx: CtxDep, cand_id: int) -> EditedClipRead:
    c = ctx.session.get(ClipCandidate, cand_id)
    v = ctx.get_owned(SourceVideo, c.video_id) if c else None
    if not c or not v:
        raise HTTPException(404, "corte não encontrado")
    ec = ctx.session.exec(select(EditedClip).where(EditedClip.candidate_id == c.id)).first() or new_edit(ctx.session, v, c)
    if c.status == "candidate":
        c.status = "approved"
        ctx.session.add(c)
        ctx.session.commit()
    return clip_read(ec)
