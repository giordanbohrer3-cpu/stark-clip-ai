"""Auth por token (Bearer), escopo por workspace, criptografia de tokens e caminhos seguros."""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import logging
from pathlib import Path
from typing import Annotated, Any

from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from .config import get_settings
from .db import get_session
from .models import AuditLog, User, Workspace

log = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "autonomy": "assisted",  # assisted|semi|autonomous
    "paused": False,
    "clips": {"target": 3, "mode": "short", "min_score": 35},
    "ai": {
        "monthly_budget_usd": 0.0,  # 0 = nenhuma cobrança permitida
        "hard_limit": True,
        "alert_pct": 80,
        "routing": {"cut_planning": "heuristic", "copywriting": "heuristic"},
        "providers": {
            "anthropic": {"enabled": False, "model": "claude-haiku-5-5", "price_in": 1.0, "price_out": 5.0},
            "openai": {"enabled": False, "model": "gpt-5-mini", "price_in": 0.25, "price_out": 2.0},
            "gemini": {"enabled": False, "model": "gemini-2.5-flash", "price_in": 0.3, "price_out": 2.5},
            "ollama": {"enabled": False, "model": "qwen2.5:7b", "price_in": 0.0, "price_out": 0.0},
        },
    },
    "captions": {
        "font": "Montserrat ExtraBold", "size": 84, "primary": "#FFFFFF", "highlight": "#22D3EE",
        "outline": "#000000", "outline_w": 7, "position": 0.68, "words_per_line": 3, "uppercase": True,
    },
    "branding": {"logo_path": None, "logo_opacity": 0.9, "logo_scale": 0.14},
    "cadence": {"min_gap_minutes": 90, "quiet_start": 0, "quiet_end": 7, "tz_offset_h": -3},
    "radar": {"enabled": True, "game": "Grand Theft Auto VI", "languages": [], "max_channels": 80,
              "sensitivity": 3.0, "min_rate": 12, "youtube_query": "GTA 6 ao vivo",
              # sem chave: streamers famosos vigiados pelo chat público da Twitch
              "watch_twitch": ["gaules", "casimiro", "alanzoka", "loud_coringa", "cellbit", "baiano", "jukes",
                               "piuzinho", "paulinholoko", "xqc", "kaicenat", "summit1g", "caseoh_", "jynxzi",
                               "ibai"],
              # sem chave: feed RSS público dos YouTubers famosos (IDs UC…)
              "youtube_channels": [
                  "UCIwspRtKNszHhIhl36gREjQ",  # alanzoka
                  "UCWKtHaeXVzUscYGcm0hEunw",  # BRKsEDU
                  "UCC43JmOyrcWNUtwki8Jml2Q",  # Cellbit
                  "UCIPA6iWNaoetaa1T46RkzXw",  # AuthenticGames
                  "UCIXguhHCl8eDTkXpEuiGPUA",  # Jazzghost
                  "UC5mZsx_OVnc4XmG9rWU2p3A",  # T3ddy
                  "UCbTVTephX30ZhQF5zwFppBg",  # RezendeEvil
                  "UCBykxRXc4bMrdhE_CSwWxQg",  # igaoplay
                  "UC0aP2AAWHtF2_hHWZyxrWSw",  # DavyJonesGTA
                  "UCyU4tSZFzaGmio-K_8WYWIg",  # flowgamesbr
                  "UCrTKytJZ5ed8JiRB-qS37vQ",  # Enaldinho
                  "UCIvBHgnnLSVr9enuPvBuwyw",  # Piuzinho
                  "UCYALxwppPJjYyTMEwwEcNCQ",  # LubaTV
                  "UCjBO43ykxlSs3j7F7EXcBUQ",  # Tazercraft
                  "UCV306eHqgo0LvBf3Mh36AHg",  # Felipe Neto
                  "UCIPPMRA040LQr5QPyJEbmXA",  # MrBeast Gaming
              ]},
    # pasta de entrada: vídeos autorizados jogados aqui viram cortes no feed (declaração única em /inbox/confirm)
    "inbox": {"enabled": True, "path": "", "confirmed": False, "confirmed_at": None, "rights_type": "own",
              "holder": "", "allows_commercial": True, "layout": "auto", "credit": ""},
}


def deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def ws_settings(ws: Workspace) -> dict:
    return deep_merge(DEFAULT_SETTINGS, ws.settings or {})


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bootstrap(session: Session) -> User:
    """Cria workspace + usuário dono na 1ª execução. Token fica em STARK_API_TOKEN ou data/.api_token."""
    token_hash = hash_token(get_settings().resolved_api_token())
    user = session.exec(select(User).where(User.token_hash == token_hash)).first()
    if user:
        return user
    ws = session.exec(select(Workspace)).first()
    if not ws:
        ws = Workspace(name="STARK LAB", settings={})
        session.add(ws)
        session.flush()
    user = User(workspace_id=ws.id, name="owner", role="owner", token_hash=token_hash)
    session.add(user)
    session.commit()
    session.refresh(user)
    log.info("bootstrap: workspace %s / user %s", ws.id, user.id)
    return user


class Ctx:
    """Contexto autenticado: usuário + workspace (escopo de todas as queries)."""

    def __init__(self, user: User, ws: Workspace, session: Session):
        self.user, self.ws, self.session = user, ws, session

    @property
    def settings(self) -> dict:
        return ws_settings(self.ws)

    def audit(self, action: str, target: str = "", **detail: Any) -> None:
        self.session.add(AuditLog(workspace_id=self.ws.id, actor=f"user:{self.user.id}", action=action,
                                  target=target, detail=detail))

    def get_owned(self, model: type, obj_id: int):
        obj = self.session.get(model, obj_id)
        if not obj or getattr(obj, "workspace_id", None) != self.ws.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} não encontrado")
        return obj


def get_ctx(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Ctx:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token ausente")
    token_hash = hash_token(authorization.removeprefix("Bearer ").strip())
    user = session.exec(select(User).where(User.token_hash == token_hash)).first()
    if not user or not hmac.compare_digest(user.token_hash, token_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")
    ws = session.get(Workspace, user.workspace_id)
    return Ctx(user, ws, session)


CtxDep = Annotated[Ctx, Depends(get_ctx)]


def require_role(ctx: Ctx, *roles: str) -> None:
    if ctx.user.role not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permissão insuficiente")


# ---------------------------------------------------------------- cripto de tokens OAuth
def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().resolved_secret_key().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


# ---------------------------------------------------------------- caminhos
def safe_path(base: Path, *parts: str) -> Path:
    """Junta caminho e garante que fica dentro de base (anti path traversal)."""
    root = base.resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "caminho inválido")
    return target


def data_file(rel: str | None) -> Path | None:
    """Resolve caminho salvo no banco (relativo a data_dir) com verificação."""
    if not rel:
        return None
    p = safe_path(get_settings().data_dir, rel)
    return p if p.exists() else None


def rel_data(path: Path) -> str:
    return path.resolve().relative_to(get_settings().data_dir).as_posix()
