"""Worker: python -m stark_engine.worker  (rode N processos para escalar; claim é atômico)."""
from __future__ import annotations

import logging
import signal
import time

from . import jobqueue
from .db import init_db, session_scope
from .media import Canceled, MediaError
from .models import EditedClip, Job, SourceVideo
from .pipeline import PermissionDenied, run_analyze, run_render
from .publishing import run_publish, scheduler_tick
from .config import get_settings

log = logging.getLogger("stark.worker")
HANDLERS = {"analyze": run_analyze, "render": run_render, "publish": run_publish}
_stop = False


def _mark_failed(job: Job, msg: str) -> None:
    with session_scope() as s:
        if job.kind == "analyze" and (v := s.get(SourceVideo, job.ref_id)):
            v.status, v.error = "error", msg[:500]
            s.add(v)
        elif job.kind == "render" and (c := s.get(EditedClip, job.ref_id)):
            c.status, c.error = "error", msg[:500]
            s.add(c)
        s.commit()


def run_job(job: Job) -> None:
    ctl = jobqueue.JobCtl(job.id)
    try:
        with session_scope() as s:
            result = HANDLERS[job.kind](s, s.get(Job, job.id), ctl)
        jobqueue.finish(job.id, result or {})
        log.info("job %s %s ok", job.id, job.kind)
    except Canceled:
        jobqueue.fail(job.id, "cancelado pelo usuário", retryable=False)
        _mark_failed(job, "cancelado")
    except (PermissionDenied, FileNotFoundError, MediaError, KeyError, ValueError) as e:
        jobqueue.fail(job.id, f"{type(e).__name__}: {e}", retryable=False)
        _mark_failed(job, str(e))
        log.warning("job %s falhou: %s", job.id, e)
    except Exception as e:  # noqa: BLE001 - fronteira do worker: registra e agenda retentativa
        log.exception("job %s erro inesperado", job.id)
        jobqueue.fail(job.id, f"{type(e).__name__}: {e}", retryable=True)
        with session_scope() as s:
            if s.get(Job, job.id).status == "error":
                _mark_failed(job, str(e))


def run_once() -> bool:
    with session_scope() as s:
        jobqueue.recover_stale(s)
        scheduler_tick(s)
        job = jobqueue.claim(s)
    if job:
        run_job(job)
        return True
    return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    init_db()

    def _sig(*_):  # noqa: ANN002
        global _stop
        _stop = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    log.info("worker iniciado (poll %.1fs)", get_settings().worker_poll_s)
    while not _stop:
        if not run_once():
            time.sleep(get_settings().worker_poll_s)
    log.info("worker encerrado")


if __name__ == "__main__":
    main()
