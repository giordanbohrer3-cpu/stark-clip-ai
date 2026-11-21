"""Versão do Clipzou e botão "Atualizar agora" (o serviço em segundo plano baixa e reinicia sozinho)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import ENGINE_ROOT
from ..security import CtxDep, require_role

router = APIRouter(prefix="/system", tags=["sistema"])
REPO = ENGINE_ROOT.parent.parent
FLAG = ENGINE_ROOT / "data" / "update_now"  # lido pelo scripts/start.sh a cada 20 s


def _git(*args: str, timeout: int = 20) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False)
    if r.returncode:
        raise RuntimeError((r.stderr or "git falhou").strip()[:200])
    return r.stdout.strip()


def _service_on() -> bool:
    return os.environ.get("STARK_SERVICE") == "1" or any(p.exists() for p in (
        Path.home() / ".config/systemd/user/clipzou.service", Path.home() / "Library/LaunchAgents/ai.clipzou.plist"))


@router.get("/version", response_model=dict, summary="Versão instalada e modo segundo plano")
def version(ctx: CtxDep) -> dict:
    try:
        sha, date, subject = _git("log", "-1", "--format=%h|%cI|%s").split("|", 2)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError):
        sha = date = subject = None
    return {"commit": sha, "date": date, "subject": subject, "service": _service_on(), "auto_update_min": 15}


@router.post("/update", response_model=dict, summary="Procura versão nova no GitHub e reinicia atualizado")
def update(ctx: CtxDep) -> dict:
    require_role(ctx, "owner")
    try:
        _git("fetch", "-q", timeout=40)
        head, up = _git("rev-parse", "HEAD"), _git("rev-parse", "@{u}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise HTTPException(424, f"sem acesso ao GitHub agora: {e}") from e
    if head == up:
        return {"update": False, "message": "Você já está na versão mais nova."}
    FLAG.parent.mkdir(parents=True, exist_ok=True)
    FLAG.touch()
    ctx.audit("system_update", "app", to=up[:12])
    ctx.session.commit()
    return {"update": True, "message": "Versão nova encontrada. O Clipzou reinicia atualizado em 1–3 min."}
