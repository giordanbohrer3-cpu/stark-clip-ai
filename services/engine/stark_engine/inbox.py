"""Pasta de entrada: vídeos jogados numa pasta viram cortes prontos no feed, sozinhos.

Só importa depois da declaração única de direitos (POST /inbox/confirm). Cada vídeo importado ganha o
próprio registro de autorização (RightsGrant) com essa declaração como prova. Nunca apaga seus arquivos:
usa link físico (sem gastar disco) ou cópia.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, select

from . import media
from .config import get_settings
from .db import session_scope
from .jobqueue import enqueue
from .live.jobs import _owner, register_file
from .models import AuditLog, SourceVideo, Workspace
from .pipeline import video_dir
from .security import ws_settings

log = logging.getLogger("stark.inbox")
DEFAULT_PATH = "~/Clipzou/Entrada"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
SETTLE_S = 15  # arquivo parado há 15 s = cópia terminou
MAX_PER_SCAN = 10
RIGHTS = ("own", "licensed", "creator_permission", "public_domain", "cc_by")


def folder(cfg: dict) -> Path:
    return Path(str(cfg.get("path") or DEFAULT_PATH)).expanduser()


def _key(f: Path, size: int) -> str:
    return f"inbox:{f.name}:{size}"


def _files(d: Path) -> list[tuple[Path, os.stat_result]]:
    out = []
    try:
        for f in d.iterdir():
            if f.suffix.lower() not in VIDEO_EXT or f.name.startswith((".", "~")):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if f.is_file():
                out.append((f, st))
    except OSError:
        return []
    return sorted(out, key=lambda x: x[1].st_mtime)


def _known(session: Session, ws_id: int) -> set[str]:
    return set(session.exec(select(SourceVideo.url).where(SourceVideo.workspace_id == ws_id,
                                                          SourceVideo.origin == "inbox")))


def pending(session: Session, ws: Workspace) -> list[dict]:
    """Arquivos na pasta que ainda não viraram cortes."""
    d, known, now = folder(ws_settings(ws)["inbox"]), _known(session, ws.id), time.time()
    return [{"name": f.name, "size_mb": round(st.st_size / 1e6, 1), "copying": now - st.st_mtime < SETTLE_S}
            for f, st in _files(d) if _key(f, st.st_size) not in known]


@contextmanager
def _lock():
    """Trava entre processos (radar + API) para não importar o mesmo arquivo duas vezes."""
    p = get_settings().data_dir / "inbox.lock"
    try:
        if p.exists() and time.time() - p.stat().st_mtime > 600:
            p.unlink(missing_ok=True)  # trava esquecida por processo que morreu
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield False
        return
    os.close(fd)
    try:
        yield True
    finally:
        p.unlink(missing_ok=True)


def _title(f: Path) -> str:
    return " ".join(f.stem.replace("_", " ").replace(".", " ").split())[:200] or f.name[:200]


def scan(session: Session, ws: Workspace) -> dict:
    """Importa vídeos novos da pasta e manda gerar os cortes (3 por vídeo, renderizados)."""
    cfg = ws_settings(ws)["inbox"]
    d = folder(cfg)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"imported": 0, "status": "erro", "error": f"pasta inacessível: {e}"}
    if not cfg.get("enabled", True):
        return {"imported": 0, "status": "desligada"}
    if not cfg.get("confirmed"):
        return {"imported": 0, "status": "aguardando declaração"}
    imported, errors = 0, []
    with _lock() as got:
        if not got:
            return {"imported": 0, "status": "já buscando"}
        known, now = _known(session, ws.id), time.time()
        limit_bytes = get_settings().max_upload_mb * 1024 * 1024
        grant = {"rights_type": cfg.get("rights_type") if cfg.get("rights_type") in RIGHTS else "own",
                 "holder": cfg.get("holder") or "dono da pasta de entrada",
                 "evidence": f"declaração da pasta de entrada ({cfg.get('confirmed_at') or 'sem data'})",
                 "allows_commercial": bool(cfg.get("allows_commercial", True))}
        for f, st in _files(d):
            key = _key(f, st.st_size)
            if key in known or now - st.st_mtime < SETTLE_S:
                continue
            v = SourceVideo(workspace_id=ws.id, title=_title(f), origin="inbox", url=key, status="queued",
                            niche=ws_settings(ws)["radar"].get("game") or "")
            session.add(v)
            session.commit()
            session.refresh(v)
            try:
                if st.st_size > limit_bytes:
                    raise media.MediaError(f"arquivo maior que {get_settings().max_upload_mb} MB")
                dst = video_dir(v) / f"original{f.suffix.lower()}"
                try:
                    os.link(f, dst)  # mesmo disco: não ocupa espaço extra
                except OSError:
                    shutil.copy2(f, dst)
                register_file(session, v, dst, grant, _owner(session, ws.id))
            except (OSError, media.MediaError) as e:
                v.status, v.error = "error", str(e)[:300]
                session.add(v)
                session.commit()
                errors.append(f"{f.name}: {v.error}")
                continue
            enqueue(session, ws.id, "analyze", v.id, {"auto_render": True, "layout": cfg.get("layout") or "auto",
                                                       "credit": cfg.get("credit") or ""})
            session.add(AuditLog(workspace_id=ws.id, actor="agent", action="inbox_import", target=f"video:{v.id}",
                                 detail={"file": f.name, "size": st.st_size}))
            session.commit()
            imported += 1
            log.info("pasta de entrada: %s → vídeo %s", f.name, v.id)
            if imported >= MAX_PER_SCAN:
                break
    return {"imported": imported, "status": "ok", "errors": errors}


def scan_all() -> dict | None:
    with session_scope() as s:
        ws = s.exec(select(Workspace)).first()
        return scan(s, ws) if ws else None


def open_folder(d: Path) -> None:
    """Abre a pasta no gerenciador de arquivos do PC."""
    d.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(d)  # type: ignore[attr-defined]
        return
    exe = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
    if not exe:
        raise OSError("gerenciador de arquivos não encontrado")
    subprocess.Popen([exe, str(d)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
