"""Twitch Helix (oficial): lives por jogo, usuários, criar clipe e baixar clipe (editor do canal).

App token (client credentials) para o radar; token de usuário (OAuth) para criar/baixar clipes.
Download só funciona em canais onde você é EDITOR (o streamer autoriza em Painel → Funções).
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..models import Integration, utcnow
from ..security import decrypt, encrypt

HELIX = "https://api.twitch.tv/helix"
ID = "https://id.twitch.tv/oauth2"
SCOPES = "clips:edit editor:manage:clips"
_app: dict = {"token": "", "exp": 0.0}


class TwitchError(RuntimeError):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.twitch_client_id and s.twitch_client_secret)


def _creds() -> tuple[str, str]:
    s = get_settings()
    if not configured():
        raise TwitchError("defina STARK_TWITCH_CLIENT_ID e STARK_TWITCH_CLIENT_SECRET (app grátis em dev.twitch.tv)")
    return s.twitch_client_id, s.twitch_client_secret


def app_token() -> str:
    if _app["token"] and time.time() < _app["exp"] - 60:
        return _app["token"]
    cid, secret = _creds()
    r = httpx.post(f"{ID}/token", timeout=20, data={"client_id": cid, "client_secret": secret,
                                                     "grant_type": "client_credentials"})
    if r.status_code != 200:
        raise TwitchError(f"token do app recusado ({r.status_code}): confira client id/secret")
    d = r.json()
    _app.update(token=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)))
    return _app["token"]


def helix(method: str, path: str, params: dict | list | None = None, token: str | None = None) -> dict:
    cid, _ = _creds()
    r = httpx.request(method, f"{HELIX}{path}", params=params, timeout=20,
                      headers={"Client-Id": cid, "Authorization": f"Bearer {token or app_token()}"})
    if r.status_code == 401 and token is None:
        _app["token"] = ""
        r = httpx.request(method, f"{HELIX}{path}", params=params, timeout=20,
                          headers={"Client-Id": cid, "Authorization": f"Bearer {app_token()}"})
    if r.status_code >= 400:
        raise TwitchError(f"Twitch {path} → HTTP {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}


def game_id(name: str) -> str | None:
    data = helix("GET", "/games", {"name": name}).get("data", [])
    return data[0]["id"] if data else None


def top_streams(gid: str | None, languages: list[str] | None = None, limit: int = 80) -> list[dict]:
    """Lives com mais espectadores (gid=None: todas as categorias = streamers mais famosos agora)."""
    out, cursor = [], None
    while len(out) < limit:
        params: list = [("first", min(100, limit - len(out)))] + ([("game_id", gid)] if gid else [])
        params += [("language", lang) for lang in (languages or [])]
        if cursor:
            params.append(("after", cursor))
        d = helix("GET", "/streams", params)
        out += d.get("data", [])
        cursor = (d.get("pagination") or {}).get("cursor")
        if not cursor or not d.get("data"):
            break
    return [_fmt(s) for s in out[:limit]]


def _fmt(s: dict) -> dict:
    return {
        "platform": "twitch", "channel": s["user_login"].lower(), "display_name": s["user_name"],
        "broadcaster_id": s["user_id"], "title": s.get("title", ""), "viewers": int(s.get("viewer_count", 0)),
        "game": s.get("game_name", ""), "language": s.get("language", ""),
        "thumbnail_url": s.get("thumbnail_url", "").replace("{width}", "440").replace("{height}", "248"),
        "started_at": s.get("started_at"), "url": f"https://twitch.tv/{s['user_login']}",
    }


def streams_by_login(logins: list[str]) -> list[dict]:
    """Quem da lista de famosos está ao vivo agora (API oficial)."""
    if not logins:
        return []
    d = helix("GET", "/streams", [("user_login", x) for x in logins[:100]] + [("first", 100)])
    return [_fmt(s) for s in d.get("data", [])]


def user_ids(logins: list[str]) -> dict[str, str]:
    if not logins:
        return {}
    d = helix("GET", "/users", [("login", x) for x in logins[:100]])
    return {u["login"].lower(): u["id"] for u in d.get("data", [])}


# ------------------------------------------------------------------ OAuth do usuário
def authorize_url(state: str) -> str:
    cid, _ = _creds()
    return f"{ID}/authorize?" + urlencode({"response_type": "code", "client_id": cid, "state": state,
                                           "redirect_uri": get_settings().twitch_redirect_uri, "scope": SCOPES})


def _save_tokens(session: Session, ws_id: int, d: dict) -> Integration:
    v = httpx.get(f"{ID}/validate", timeout=15, headers={"Authorization": f"OAuth {d['access_token']}"}).json()
    it = session.exec(select(Integration).where(Integration.workspace_id == ws_id,
                                                Integration.provider == "twitch")).first()
    it = it or Integration(workspace_id=ws_id, provider="twitch")
    it.account_id, it.account_login = v.get("user_id", ""), v.get("login", "")
    it.token_encrypted = encrypt(d["access_token"])
    if d.get("refresh_token"):
        it.refresh_encrypted = encrypt(d["refresh_token"])
    it.expires_at = utcnow() + timedelta(seconds=int(d.get("expires_in", 3600)))
    it.scopes = v.get("scopes", d.get("scope", []))
    it.updated_at = utcnow()
    session.add(it)
    session.commit()
    session.refresh(it)
    return it


def exchange_code(session: Session, ws_id: int, code: str) -> Integration:
    cid, secret = _creds()
    r = httpx.post(f"{ID}/token", timeout=20, data={
        "client_id": cid, "client_secret": secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": get_settings().twitch_redirect_uri})
    if r.status_code != 200:
        raise TwitchError(f"login Twitch recusado ({r.status_code})")
    return _save_tokens(session, ws_id, r.json())


def user_token(session: Session, ws_id: int) -> tuple[str, str]:
    """(token, user_id) do usuário conectado; renova se estiver vencendo."""
    it = session.exec(select(Integration).where(Integration.workspace_id == ws_id,
                                                Integration.provider == "twitch")).first()
    if not it or not it.token_encrypted:
        raise TwitchError("conecte sua conta Twitch em Config")
    exp = it.expires_at.replace(tzinfo=UTC) if it.expires_at and it.expires_at.tzinfo is None else it.expires_at
    if exp and exp - datetime.now(UTC) < timedelta(minutes=5) and it.refresh_encrypted:
        cid, secret = _creds()
        r = httpx.post(f"{ID}/token", timeout=20, data={
            "client_id": cid, "client_secret": secret, "grant_type": "refresh_token",
            "refresh_token": decrypt(it.refresh_encrypted)})
        if r.status_code != 200:
            raise TwitchError("sessão Twitch expirou: conecte de novo em Config")
        it = _save_tokens(session, ws_id, r.json())
    return decrypt(it.token_encrypted), it.account_id


def create_clip(token: str, broadcaster_id: str) -> str:
    """Clipe dos últimos ~30 s da live (API oficial; o canal precisa permitir clipes)."""
    d = helix("POST", "/clips", {"broadcaster_id": broadcaster_id}, token=token)
    data = d.get("data") or []
    if not data:
        raise TwitchError("Twitch não criou o clipe (canal offline ou clipes desativados)")
    return data[0]["id"]


def clip_download_url(token: str, editor_id: str, broadcaster_id: str, clip_id: str) -> str | None:
    """URL temporária do MP4 (horizontal). Exige ser editor do canal (403 se não for)."""
    d = helix("GET", "/clips/downloads", {"editor_id": editor_id, "broadcaster_id": broadcaster_id,
                                          "clip_id": clip_id}, token=token)
    for item in d.get("data", []):
        for key, val in item.items():
            if "landscape" in key and val:
                return val
        for key, val in item.items():
            if key.endswith("url") and val:
                return val
    return None
