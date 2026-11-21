"""API STARK CLIP AI (FastAPI). Rodar: uvicorn stark_engine.main:app --host 127.0.0.1 --port 8787"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import __version__, media
from .config import get_settings
from .db import get_engine, init_db, session_scope
from .routers import clips, ops, publish, videos
from .schemas import Health
from .security import bootstrap

log = logging.getLogger("stark.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    init_db()
    with session_scope() as s:
        bootstrap(s)
    if os.getenv("STARK_EMBEDDED_WORKER") == "1":  # dev: worker no mesmo processo
        from .worker import main as worker_main

        threading.Thread(target=worker_main, daemon=True, name="stark-worker").start()
    yield


app = FastAPI(
    title="STARK CLIP AI Engine", version=__version__, lifespan=lifespan,
    description="Cortes com IA, legendas, render 9:16 e publicação assistida. Somente material autorizado.",
    contact={"name": "STARK LAB"},
)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("erro não tratado")
    return JSONResponse(status_code=500, content={"detail": f"erro interno: {type(exc).__name__}"})


api = APIRouter(prefix="/api/v1")


@api.get("/health", response_model=Health, tags=["sistema"], summary="Estado dos serviços (sem auth)")
def health() -> Health:
    db_ok = True
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    s = get_settings()
    ff = media.tool_ok("ffmpeg") and media.tool_ok("ffprobe")
    return Health(ok=db_ok and ff, version=__version__, ffmpeg=ff, db=db_ok, whisper_model=s.whisper_model,
                  youtube_api=bool(s.youtube_api_key))


for r in (videos.router, videos.cand_router, clips.router, publish.router, ops.router):
    api.include_router(r)
app.include_router(api)
