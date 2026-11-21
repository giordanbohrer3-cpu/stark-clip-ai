"""Versão do Clipzou e botão "Atualizar agora" (o serviço em segundo plano baixa e reinicia sozinho)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import cloud
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


_ts_cache: dict = {"at": 0.0, "data": {}}


def _tailscale() -> dict:
    """Endereço HTTPS do Tailscale deste PC (para o QR do celular). Vazio se não houver Tailscale ligado."""
    if time.time() - _ts_cache["at"] < 60:
        return _ts_cache["data"]
    data: dict = {}
    exe = shutil.which("tailscale")
    if exe:
        try:
            st = json.loads(subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=5,
                                           check=False).stdout or "{}")
            dns = str((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
            if dns and st.get("BackendState") == "Running":
                data = {"url": f"https://{dns}", "serving": None}
                sv = subprocess.run([exe, "serve", "status", "--json"], capture_output=True, text=True, timeout=5,
                                    check=False)
                if sv.returncode == 0:  # o link do Tailscale aponta para o Clipzou (porta 3000)?
                    raw = sv.stdout or "{}"
                    data["serving"] = "127.0.0.1:3000" in raw or "localhost:3000" in raw
                    data["other"] = bool(json.loads(raw)) and not data["serving"]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            data = {}
    _ts_cache.update(at=time.time(), data=data)
    return data


@router.get("/phone", response_model=dict, summary="Link para abrir no celular (app online ou Tailscale do PC)")
def phone(ctx: CtxDep) -> dict:
    app_url, ts = cloud.load_config()["app_url"], _tailscale()
    return {"url": app_url or ts.get("url") or "", "app_url": app_url, "tailscale_url": ts.get("url"),
            "tailscale_serving": ts.get("serving"), "tailscale_other": bool(ts.get("other"))}


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
