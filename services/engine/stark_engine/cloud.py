"""Ponte PC → nuvem para o app online (Vercel) funcionar no celular sem Tailscale.

    python -m stark_engine.cloud

- A cada 20 s: lê radar, feed e fila do motor local e grava no Supabase só o que mudou (área separada `clipzou`).
- Cortes prontos: sobe o MP4 + miniatura para a pasta privada `clipzou` (limite de espaço; apaga os mais antigos).
- Pedidos do celular (buscar na pasta, cortar agora, atualizar…): executa no motor local, só da lista permitida.
Sem chave configurada fica parado (não gasta nada). A chave fica criptografada em data/cloud.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from cryptography.fernet import InvalidToken
from sqlmodel import select

from .config import get_settings
from .db import init_db, session_scope
from .models import EditedClip
from .security import data_file, decrypt, encrypt

log = logging.getLogger("stark.cloud")
BUCKET = "clipzou"
CONFIG_FILE, STATE_FILE, STATUS_FILE = "cloud.json", "cloud_state.json", "cloud_status.json"
MAX_STORAGE_MB = 500  # o projeto grátis tem 1 GB, dividido com seus outros apps
MAX_FILE_MB = 48  # limite por arquivo do plano grátis = 50 MB
MAX_UPLOADS_PER_ROUND = 3
SNAP_S, CMD_S, CLIPS_S, EGRESS_S = 20, 3, 30, 300
SNAP = {"status": "/live/status", "streams": "/live/streams?limit=60", "moments": "/live/moments?limit=40",
        "videos": "/live/videos?limit=40", "channels": "/live/channels", "inbox": "/inbox", "queue": "/feed/queue",
        "version": "/system/version", "health": "/health", "settings": "/settings"}
# o que o celular pode pedir ao PC (o resto só no PC)
ALLOWED = [("POST", r"/inbox/scan"), ("POST", r"/inbox/confirm"), ("DELETE", r"/inbox/confirm"),
           ("POST", r"/live/channels"), ("DELETE", r"/live/channels/\d+"), ("POST", r"/live/channels/\d+/clip"),
           ("POST", r"/live/campaigns"), ("POST", r"/system/update"), ("PATCH", r"/settings"),
           ("POST", r"/agent/(pause|resume)")]
KEY_RE = re.compile(r"^(sb_secret_[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$")
URL_RE = re.compile(r"^https://[a-z0-9-]+\.supabase\.co$")


class CloudError(RuntimeError):
    pass


def allowed(method: str, path: str) -> bool:
    return any(m == method.upper() and re.fullmatch(p, path) for m, p in ALLOWED)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _data(name: str) -> Path:
    return get_settings().data_dir / name


def _read(name: str, default: dict) -> dict:
    try:
        return json.loads(_data(name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, data: dict, private: bool = False) -> None:
    p = _data(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    if private:
        tmp.chmod(0o600)
    tmp.replace(p)


# ------------------------------------------------------------------ configuração (chave criptografada)
def load_config() -> dict:
    s = get_settings()
    raw = _read(CONFIG_FILE, {})
    key = s.cloud_key
    if raw.get("key_enc"):
        try:
            key = decrypt(raw["key_enc"])
        except (InvalidToken, ValueError):
            key = ""
    return {"url": (raw.get("url") or s.cloud_url).rstrip("/"), "key": key, "app_url": raw.get("app_url") or "",
            "enabled": bool(raw.get("enabled", True))}


def save_config(*, url: str | None = None, key: str | None = None, app_url: str | None = None,
                enabled: bool | None = None, clear_key: bool = False) -> None:
    raw = _read(CONFIG_FILE, {})
    if url is not None:
        raw["url"] = url.rstrip("/")
    if key:
        raw["key_enc"] = encrypt(key)
    if clear_key:
        raw.pop("key_enc", None)
    if app_url is not None:
        raw["app_url"] = app_url.rstrip("/")
    if enabled is not None:
        raw["enabled"] = enabled
    _write(CONFIG_FILE, raw, private=True)


def read_status() -> dict:
    st = _read(STATUS_FILE, {})
    try:
        fresh = time.time() - datetime.fromisoformat(st.get("beat", "")).timestamp() < 60
    except ValueError:
        fresh = False
    return {**st, "running": fresh}


# ------------------------------------------------------------------ cliente Supabase (REST + Storage)
class Supa:
    def __init__(self, url: str, key: str, transport: httpx.BaseTransport | None = None):
        headers = {"apikey": key}
        if not key.startswith("sb_"):  # chave antiga (JWT service_role)
            headers["Authorization"] = f"Bearer {key}"
        self.http = httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=120, transport=transport)

    def _check(self, r: httpx.Response) -> httpx.Response:
        if r.status_code in (401, 403):
            raise CloudError("o Supabase recusou a chave: use a chave SECRETA (sb_secret_…)")
        if r.status_code == 404 and "/rpc/" in str(r.request.url):
            raise CloudError("área clipzou não encontrada nesse projeto do Supabase")
        if r.status_code >= 400:
            raise CloudError(f"nuvem respondeu {r.status_code}: {r.text[:160]}")
        return r

    def rpc(self, fn: str, **args):
        try:
            r = self._check(self.http.post(f"/rest/v1/rpc/{fn}", json=args))
        except httpx.HTTPError as e:
            raise CloudError(f"sem conexão com a nuvem ({type(e).__name__})") from e
        return r.json() if r.content else None

    def upload(self, path: str, file: Path, ctype: str, upsert: bool = True) -> None:
        headers = {"content-type": ctype, "cache-control": "max-age=31536000", "content-length": str(file.stat().st_size)}
        if upsert:
            headers["x-upsert"] = "true"
        try:
            with file.open("rb") as f:
                self._check(self.http.post(f"/storage/v1/object/{BUCKET}/{path}", content=f, headers=headers))
        except httpx.HTTPError as e:
            raise CloudError(f"envio do corte falhou ({type(e).__name__})") from e

    def sign(self, path: str, expires_s: int) -> str:
        """Link temporário para baixar um arquivo da pasta (o Metricool usa para pegar o vídeo)."""
        try:
            r = self._check(self.http.post(f"/storage/v1/object/sign/{BUCKET}/{path}", json={"expiresIn": expires_s}))
        except httpx.HTTPError as e:
            raise CloudError(f"link do corte falhou ({type(e).__name__})") from e
        return f"{str(self.http.base_url).rstrip('/')}/storage/v1/{r.json()['signedURL'].lstrip('/')}"

    def remove(self, paths: list[str]) -> None:
        if not paths:
            return
        try:
            self._check(self.http.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": paths}))
        except httpx.HTTPError as e:
            raise CloudError(f"limpeza falhou ({type(e).__name__})") from e


def check_key(url: str, key: str, transport: httpx.BaseTransport | None = None) -> int:
    """Testa a chave chamando uma função da área clipzou. Retorna o download do mês (bytes)."""
    if not URL_RE.match(url.rstrip("/")):
        raise CloudError("endereço do Supabase inválido (https://xxxx.supabase.co)")
    if not KEY_RE.match(key.strip()):
        raise CloudError("cole a chave SECRETA do Supabase (começa com sb_secret_)")
    return int(Supa(url, key.strip(), transport).rpc("clipzou_egress") or 0)


def _thumb(src: Path, dst: Path) -> Path | None:
    """Miniatura leve (~20 KB) para o feed online gastar pouco da cota grátis."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    args = [exe, "-v", "error", "-y"] + (["-ss", "1"] if src.suffix == ".mp4" else []) + [
        "-i", str(src), "-frames:v", "1", "-vf", "scale=270:-2", "-q:v", "6", str(dst)]
    try:
        subprocess.run(args, check=True, timeout=60, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        return None
    return dst if dst.exists() else None


def _hash(v) -> str:
    return hashlib.sha1(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()


def _slim(item: dict) -> dict:
    """Só o que o feed online usa (menos dados = menos cota)."""
    c = item.get("clip") or {}
    caps = ((c.get("copy_text") or {}).get("captions") or {})
    return {"clip": {"id": c.get("id"), "status": c.get("status"), "duration_s": c.get("duration_s", 0),
                     "updated_at": c.get("updated_at"), "files": c.get("files") or [],
                     "copy_text": {"captions": {k: caps[k] for k in ("tiktok", "instagram", "youtube") if k in caps}}},
            "video_id": item.get("video_id"), "title": item.get("title"), "origin": item.get("origin"),
            "channel": item.get("channel"), "source_url": item.get("source_url")}


# ------------------------------------------------------------------ sincronizador
class Syncer:
    def __init__(self, local: httpx.Client, cloud: Supa, max_storage_mb: int = MAX_STORAGE_MB):
        self.local, self.cloud, self.max_bytes = local, cloud, max_storage_mb * 1024 * 1024
        self.state = _read(STATE_FILE, {"hashes": {}, "clips": {}})
        self.state.setdefault("hashes", {})
        self.state.setdefault("clips", {})
        self.force = True
        self.feed: list[dict] | None = None

    def _save(self) -> None:
        _write(STATE_FILE, self.state)

    def _get(self, path: str):
        r = self.local.get(path)
        return r.json() if r.status_code == 200 else None

    # celular → PC
    def commands(self) -> int:
        cmds = self.cloud.rpc("clipzou_cmd_take", p_limit=10) or []
        for c in cmds:
            method, path, body = str(c.get("method", "")).upper(), str(c.get("path", "")), c.get("body")
            if not allowed(method, path):
                self.cloud.rpc("clipzou_cmd_done", p_id=c["id"], p_http=403,
                               p_result={"detail": "isso só pode ser feito no PC"})
                continue
            try:
                r = self.local.request(method, path, json=body if method != "DELETE" else None)
                try:
                    result = r.json()
                except ValueError:
                    result = {"detail": r.text[:500]}
                code = r.status_code
            except httpx.HTTPError as e:
                code, result = 502, {"detail": f"motor do PC não respondeu ({type(e).__name__})"}
            self.cloud.rpc("clipzou_cmd_done", p_id=c["id"], p_http=code,
                           p_result=result if isinstance(result, dict) else {"data": result})
            log.info("pedido do celular: %s %s → %s", method, path, code)
        if cmds:
            self.force = True
        return len(cmds)

    # cortes prontos → pasta privada na nuvem
    def clips(self) -> dict:
        feed = self._get("/feed?limit=60") or []
        ids = {int(it["clip"]["id"]) for it in feed}
        with session_scope() as s:
            rows = {ec.id: ec for ec in s.exec(select(EditedClip).where(EditedClip.id.in_(ids or {-1})))}
        done = self.state["clips"]
        uploaded = 0
        for it in feed:
            cid = int(it["clip"]["id"])
            ec, rev = rows.get(cid), str(it["clip"].get("updated_at"))
            if not ec or (done.get(str(cid), {}).get("rev") == rev) or uploaded >= MAX_UPLOADS_PER_ROUND:
                continue
            out, cover = data_file(ec.output_path), data_file(ec.cover_path)
            if not out:
                continue
            size = out.stat().st_size
            old = done.get(str(cid), {})
            if size > MAX_FILE_MB * 1024 * 1024:
                done[str(cid)] = {"rev": rev, "skip": "grande demais para a nuvem grátis", "size": size}
                continue
            base = f"clips/{cid}/{secrets.token_hex(12)}"
            with tempfile.TemporaryDirectory() as tmp:
                thumb = _thumb(cover or out, Path(tmp) / "t.jpg")
                self.cloud.upload(f"{base}.mp4", out, "video/mp4")
                if thumb:
                    self.cloud.upload(f"{base}.jpg", thumb, "image/jpeg")
            slim = _slim(it)
            self.cloud.rpc("clipzou_clip_upsert", p={
                "id": cid, "video_id": it.get("video_id"), "title": it.get("title") or "", "origin": it.get("origin"),
                "channel": it.get("channel"), "source_url": it.get("source_url"), "duration_s": ec.duration_s,
                "clip": slim["clip"], "output_path": f"{base}.mp4", "cover_path": f"{base}.jpg" if thumb else None,
                "size_bytes": size})
            self.cloud.remove([p for p in (old.get("output"), old.get("cover")) if p])
            done[str(cid)] = {"rev": rev, "output": f"{base}.mp4", "cover": f"{base}.jpg" if thumb else None,
                              "size": size, "at": rev}
            uploaded += 1
            self._save()
            log.info("corte %s na nuvem (%.1f MB)", cid, size / 1e6)
        # some do PC (apagado ou fora dos 60 mais novos) → some da nuvem; espaço acima do limite → apaga os velhos
        gone = [k for k in done if int(k) not in ids]
        live = sorted(((k, v) for k, v in done.items() if v.get("output") and k not in gone),
                      key=lambda x: str(x[1].get("at")))  # mais antigo primeiro (data do corte)
        total = sum(v["size"] for _, v in live)
        while live and total > self.max_bytes:
            k, v = live.pop(0)
            total -= v["size"]
            gone.append(k)
        if gone:
            paths = self.cloud.rpc("clipzou_clip_delete", p_ids=[int(k) for k in gone]) or []
            self.cloud.remove([p for p in paths if p])
            for k in gone:
                if int(k) in ids and done.get(k, {}).get("output"):
                    done[k] = {"rev": done[k]["rev"], "skip": "espaço da nuvem cheio: só no PC", "size": done[k]["size"]}
                else:
                    done.pop(k, None)
            self._save()
        items = []
        for it in feed:
            info = done.get(str(it["clip"]["id"]), {})
            items.append({**_slim(it), "cloud": {"output": info["output"], "cover": info.get("cover"),
                                                 "size": info["size"]} if info.get("output") else None,
                          "only_pc": info.get("skip")})
        self.feed = items
        if uploaded or gone:
            self.force = True
        return {"uploaded": uploaded, "removed": len(gone), "bytes": total}

    # radar + feed + fila → nuvem (só o que mudou)
    def snapshot(self) -> int:
        data = {k: v for k, path in SNAP.items() if (v := self._get(path)) is not None}
        if self.feed is not None:
            data["feed"] = self.feed
        hashes = {k: _hash(v) for k, v in data.items()}
        changed = {k: v for k, v in data.items() if self.state["hashes"].get(k) != hashes[k]}
        all_hashes = {**self.state["hashes"], **hashes}
        self.cloud.rpc("clipzou_push", p={**changed, "rev": {"beat": _now(), "hashes": all_hashes}})
        self.state["hashes"] = all_hashes
        self._save()
        self.force = False
        return len(changed)


def local_client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(base_url=f"{s.engine_url.rstrip('/')}/api/v1", timeout=60,
                        headers={"Authorization": f"Bearer {s.resolved_api_token()}"})


def main() -> None:  # pragma: no cover - laço de serviço
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    init_db()
    from . import autopilot  # piloto automático: roda mesmo sem a chave secreta (usa a chave pública)

    syncer, sig, last = None, None, {"cmd": 0.0, "clips": 0.0, "snap": 0.0, "egress": 0.0, "auto": 0.0}
    status: dict = {}
    while True:
        if time.time() - last["auto"] >= autopilot.EVERY_S:
            last["auto"] = time.time()
            try:
                autopilot.tick()
            except Exception:  # piloto nunca derruba a ponte
                log.exception("piloto automático falhou")
        cfg = load_config()
        status["beat"] = _now()
        if not cfg["key"] or not cfg["enabled"]:
            status.update(configured=False, error="")
            _write(STATUS_FILE, status)
            time.sleep(10)
            continue
        if (cfg["url"], cfg["key"]) != sig:
            syncer, sig = Syncer(local_client(), Supa(cfg["url"], cfg["key"])), (cfg["url"], cfg["key"])
        now = time.time()
        try:
            if now - last["cmd"] >= CMD_S:
                last["cmd"] = now
                syncer.commands()
            if now - last["clips"] >= CLIPS_S:
                last["clips"] = now
                status.update(syncer.clips())
            if syncer.force or now - last["snap"] >= SNAP_S:
                last["snap"] = now
                syncer.snapshot()
                status["last_sync_at"] = _now()
            if now - last["egress"] >= EGRESS_S:
                last["egress"] = now
                status["egress_bytes"] = int(syncer.cloud.rpc("clipzou_egress") or 0)
            status.update(configured=True, error="")
        except CloudError as e:
            status.update(configured=True, error=str(e))
            log.warning("nuvem: %s", e)
            time.sleep(15)
        except httpx.HTTPError as e:
            status.update(configured=True, error=f"motor local offline ({type(e).__name__})")
            time.sleep(5)
        status["beat"] = _now()
        _write(STATUS_FILE, status)
        time.sleep(1)


if __name__ == "__main__":
    main()
