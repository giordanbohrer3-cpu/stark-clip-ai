"""Fila persistente no próprio banco (sem Redis): claim otimista, lease, retry com backoff,
cancelamento cooperativo e recuperação de jobs órfãos. Seguro com N workers (SQLite WAL ou Postgres)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from sqlalchemy import or_, update
from sqlmodel import Session, select

from .config import get_settings
from .db import session_scope
from .models import Job, Workspace, utcnow
from .security import ws_settings

log = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


def enqueue(session: Session, ws_id: int, kind: str, ref_id: int, payload: dict | None = None,
            max_attempts: int = 3) -> Job:
    payload = payload or {}
    for j in session.exec(select(Job).where(Job.kind == kind, Job.ref_id == ref_id, Job.status.in_(ACTIVE))):
        if j.payload == payload:
            return j  # dedupe: mesmo trabalho já na fila
    job = Job(workspace_id=ws_id, kind=kind, ref_id=ref_id, payload=payload, max_attempts=max_attempts)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def paused_workspaces(session: Session) -> set[int]:
    return {w.id for w in session.exec(select(Workspace)) if ws_settings(w).get("paused")}


def claim(session: Session) -> Job | None:
    now = utcnow()
    paused = paused_workspaces(session)
    cands = session.exec(
        select(Job).where(Job.status == "queued", or_(Job.run_after.is_(None), Job.run_after <= now))
        .order_by(Job.created_at).limit(10)
    ).all()
    for job in cands:
        if job.workspace_id in paused:
            continue
        res = session.exec(
            update(Job).where(Job.id == job.id, Job.status == "queued").values(
                status="running", attempts=Job.attempts + 1, started_at=now, stage="iniciando",
                lease_until=now + timedelta(seconds=get_settings().lease_s))
        )
        session.commit()
        if res.rowcount == 1:
            session.refresh(job)
            return job
    return None


def recover_stale(session: Session) -> int:
    now, n = utcnow(), 0
    for job in session.exec(select(Job).where(Job.status == "running", Job.lease_until < now)):
        n += 1
        if job.attempts < job.max_attempts:
            job.status, job.stage = "queued", "recuperado após falha do worker"
        else:
            job.status, job.error, job.finished_at = "error", "worker caiu repetidamente", now
        session.add(job)
    session.commit()
    return n


class JobCtl:
    """Progresso + lease + cancelamento, com escrita limitada (~2/s)."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self._last = 0.0
        self._cancel = False

    def progress(self, frac: float, stage: str = "") -> None:
        now = time.monotonic()
        if now - self._last < 0.5 and frac < 1.0:
            return
        self._last = now
        with session_scope() as s:
            job = s.get(Job, self.job_id)
            if not job:
                return
            job.progress = round(max(job.progress, min(1.0, frac)), 3)
            job.stage = stage or job.stage
            job.lease_until = utcnow() + timedelta(seconds=get_settings().lease_s)
            self._cancel = job.cancel_requested
            s.add(job)
            s.commit()

    def should_cancel(self) -> bool:
        return self._cancel


def finish(job_id: int, result: dict) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        job.status, job.progress, job.stage, job.result, job.finished_at = "done", 1.0, "concluído", result, utcnow()
        s.add(job)
        s.commit()


def fail(job_id: int, error: str, retryable: bool = True) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        job.error = error[:2000]
        if retryable and job.attempts < job.max_attempts and not job.cancel_requested:
            job.status = "queued"
            job.run_after = utcnow() + timedelta(seconds=10 * 2 ** job.attempts)
            job.stage = f"retentativa {job.attempts}/{job.max_attempts}"
        else:
            job.status, job.finished_at = ("canceled" if job.cancel_requested else "error"), utcnow()
        s.add(job)
        s.commit()


def request_cancel(session: Session, job: Job) -> Job:
    if job.status == "queued":
        job.status, job.finished_at, job.stage = "canceled", utcnow(), "cancelado"
    elif job.status == "running":
        job.cancel_requested = True
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def retry(session: Session, job: Job) -> Job:
    if job.status in ("error", "canceled"):
        job.status, job.error, job.cancel_requested, job.run_after = "queued", None, False, None
        job.max_attempts = job.attempts + 1
        job.progress, job.stage = 0, "reenfileirado"
        session.add(job)
        session.commit()
        session.refresh(job)
    return job
