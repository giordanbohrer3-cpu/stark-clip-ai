"""Piloto automático: escolhe os cortes mais em alta, monta legenda e # por rede e deixa a fila pronta para o
agendador postar sozinho no TikTok, Instagram e Facebook (Metricool grátis: 20 posts por mês somando as redes).

Sem chave secreta: usa a chave PÚBLICA do Supabase + um segredo só deste PC (data/.autopilot_secret), numa pasta
secreta com limite de arquivos. Só entram cortes de vídeos com autorização válida que permite uso comercial.
"""
from __future__ import annotations

import logging
import math
import re
import secrets
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from .clipper import content_words
from .cloud import CloudError, Supa, _read, _thumb, _write
from .config import get_settings
from .copywriter import RULES, heuristic_copy, to_tag
from .db import session_scope
from .models import ClipCandidate, EditedClip, SourceVideo, Trend, Workspace
from .pipeline import rights_ok
from .security import data_file, ws_settings

log = logging.getLogger("stark.autopilot")
NETWORKS = ("tiktok", "instagram", "facebook")
STATE_FILE, STATUS_FILE, SECRET_FILE = "autopilot_state.json", "autopilot_status.json", ".autopilot_secret"
QUEUE_SIZE = 3  # próximos posts prontos na nuvem (cada um um corte diferente)
SIGN_S = 7 * 24 * 3600  # link do vídeo para o Metricool baixar
RESIGN_S = 5 * 24 * 3600
EVERY_S = 600
MAX_FILE = 48 * 1024 * 1024
METRICOOL_URL = "https://app.metricool.com/brands/connections?blogId=8262686"


@dataclass
class Pick:
    clip_id: int
    score: float
    base: float
    title: str
    duration_s: float
    trend_tags: list[str]
    ec: EditedClip
    cand: ClipCandidate | None
    video: SourceVideo


def secret() -> str:
    return get_settings()._file_secret(SECRET_FILE, 40)


def trend_words(session: Session, ws_id: int) -> Counter:
    """Palavras dos vídeos bombando no radar, pesadas por views/hora (log)."""
    out: Counter = Counter()
    rows = session.exec(select(Trend).where(Trend.workspace_id == ws_id,
                                            Trend.source.in_(("youtube_rss", "youtube_api")))).all()
    now = time.time()
    for t in rows:
        m = t.metric or {}
        try:
            hours = max(1.0, (now - datetime.fromisoformat(str(m["published_at"])).timestamp()) / 3600)
        except (KeyError, ValueError, TypeError):
            hours = 24.0
        weight = math.log10(1 + int(m.get("views") or 0) / hours)
        for w in set(content_words(t.label or "")):
            out[w] += weight
    return out


def score_clip(base: float, words: set[str], trend: Counter, age_h: float) -> tuple[float, list[str]]:
    """Nota 0–100: qualidade do corte (60%) + assunto em alta agora (até 30) + novidade (até 10)."""
    top = trend.most_common(1)
    strongest = top[0][1] if top else 1.0
    hits = sorted((w for w in words if trend.get(w)), key=lambda w: trend[w], reverse=True)
    boost = min(30.0, sum(trend[w] for w in hits) / strongest * 12) if hits else 0.0
    fresh = max(0.0, 10.0 - age_h / 12)
    return round(min(100.0, base * 0.6 + boost + fresh), 1), [to_tag(w) for w in hits[:2]]


def eligible(session: Session, ws: Workspace) -> list[Pick]:
    trend = trend_words(session, ws.id)
    now = time.time()
    out: list[Pick] = []
    rows = session.exec(select(EditedClip).where(EditedClip.workspace_id == ws.id, EditedClip.status == "ready")
                        .order_by(EditedClip.updated_at.desc()).limit(80)).all()
    for ec in rows:
        f = data_file(ec.output_path)
        video = session.get(SourceVideo, ec.video_id)
        if not f or not video or f.stat().st_size > MAX_FILE:
            continue
        grant = rights_ok(session, video)
        if not grant or not grant.allows_commercial:  # posta no seu perfil (pode ser monetizado)
            continue
        cand = session.get(ClipCandidate, ec.candidate_id)
        title = (ec.copy_text or {}).get("title") or (cand.title if cand else video.title)
        words = set(content_words(f"{title} {' '.join(cand.keywords if cand else [])} "
                                  f"{(cand.transcript_text if cand else '')[:600]}"))
        age_h = max(0.0, (now - ec.updated_at.timestamp()) / 3600)
        base = float(cand.score if cand else 50)
        score, tags = score_clip(base, words, trend, age_h)
        out.append(Pick(ec.id, score, base, title, ec.duration_s, tags, ec, cand, video))
    return sorted(out, key=lambda p: p.score, reverse=True)


def caption(p: Pick, network: str) -> str:
    """Legenda da rede (já gerada no render) + as # do assunto em alta, no limite de cada rede."""
    copy = p.ec.copy_text or {}
    cap = str((copy.get("captions") or {}).get(network) or "")
    if not cap:
        cand = p.cand
        cap = heuristic_copy(p.title, cand.transcript_text if cand else "", cand.keywords if cand else [],
                             [p.video.niche] if p.video.niche else [])["captions"][network]
    have = {t.lower() for t in re.findall(r"#\w+", cap)}
    room = max(0, RULES[network]["tags"] + 1 - len(have))
    add = [t for t in p.trend_tags if t.lower() not in have][:room]
    if add:
        cap = f"{cap.rstrip()} {' '.join(add)}"
    return cap[: RULES[network]["max"]]


def _rotate(nets: list[str], last: str | None) -> list[str]:
    if last in nets:
        i = nets.index(last) + 1
        return nets[i:] + nets[:i]
    return nets


def plan(session: Session, ws: Workspace, posted: list[dict], connected: list[str] | None = None) -> dict:
    """Próximos posts: um corte diferente por post, redes em rodízio, dentro do limite do mês.

    connected = redes ligadas no Metricool (o agendador avisa); fora delas não entra na fila.
    """
    cfg = ws_settings(ws)["autopilot"]
    nets = [n for n in cfg.get("networks") or [] if n in NETWORKS and (connected is None or n in connected)]
    month = datetime.now(UTC).strftime("%Y-%m")
    used = sum(1 for p in posted if str(p.get("month")) == month)
    limit = int(cfg.get("monthly_limit", 18))
    base = {"enabled": bool(cfg.get("enabled", True)) and bool(nets), "networks": nets, "monthly_limit": limit,
            "used_this_month": used, "month": month, "timezone": str(cfg.get("timezone") or "America/Sao_Paulo"),
            "per_day": int(cfg.get("per_day", 1)), "items": []}
    if not base["enabled"]:
        return base
    done = {(int(p["clip_id"]), str(p.get("network"))) for p in posted if p.get("clip_id") is not None}
    clips_done = {c for c, _ in done}
    min_score = float(cfg.get("min_score", 30))  # régua só da qualidade do corte; o "em alta" só ordena
    picks = [p for p in eligible(session, ws) if p.base >= min_score]
    order = _rotate(nets, str(posted[-1].get("network")) if posted else None)
    taken: set[int] = set()
    for i in range(min(QUEUE_SIZE, max(0, limit - used))):
        net = order[i % len(order)]
        pick = next((p for p in picks if p.clip_id not in clips_done and p.clip_id not in taken), None) or next(
            (p for p in picks if (p.clip_id, net) not in done and p.clip_id not in taken), None)
        if not pick:
            break
        taken.add(pick.clip_id)
        base["items"].append({"key": f"{pick.clip_id}:{net}", "clip_id": pick.clip_id, "network": net,
                              "title": pick.title[:100], "caption": caption(pick, net), "score": pick.score,
                              "duration_s": round(pick.duration_s, 1)})
    base["_picks"] = {p.clip_id: p for p in picks if p.clip_id in taken}
    return base


def _waiting(posted: list[dict], margin_s: int = 6 * 3600) -> set[str]:
    """Cortes agendados que ainda não saíram: o vídeo fica na nuvem até 6 h depois do horário do post."""
    out = set()
    for p in posted:
        try:
            when = datetime.fromisoformat(str(p.get("scheduled_for"))).timestamp()
        except ValueError:
            continue
        if when + margin_s > time.time() and p.get("clip_id") is not None:
            out.add(str(p["clip_id"]))
    return out


def _posted_list(raw) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("posts") or []
    return [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []


def sync(session: Session, ws: Workspace, client: Supa) -> dict:
    """Atualiza a fila na nuvem: sobe só os vídeos da fila, com link de 7 dias; apaga o que já saiu."""
    sec = secret()
    folder = str(client.rpc("clipzou_pc_hello", p_secret=sec))
    state = _read(STATE_FILE, {"files": {}, "queue": {}})
    files: dict = state.setdefault("files", {})
    back = client.rpc("clipzou_pc_push", p_secret=sec, p_queue=state.get("queue") or {})
    posted = _posted_list(back)
    connected = back.get("connected") if isinstance(back, dict) and isinstance(back.get("connected"), list) else None
    q = plan(session, ws, posted, connected)
    picks: dict[int, Pick] = q.pop("_picks", {})
    now = time.time()
    for item in q["items"]:
        p = picks[item["clip_id"]]
        k, rev = str(p.clip_id), p.ec.updated_at.isoformat()
        info = files.get(k)
        if not info or info.get("rev") != rev:
            if info:
                client.remove([x for x in (info.get("mp4"), info.get("jpg")) if x])
            base = f"pc/{folder}/{p.clip_id}-{secrets.token_hex(8)}"
            out = data_file(p.ec.output_path)
            with tempfile.TemporaryDirectory() as tmp:
                thumb = _thumb(data_file(p.ec.cover_path) or out, Path(tmp) / "t.jpg")
                client.upload(f"{base}.mp4", out, "video/mp4", upsert=False)
                if thumb:
                    client.upload(f"{base}.jpg", thumb, "image/jpeg", upsert=False)
            info = files[k] = {"rev": rev, "mp4": f"{base}.mp4", "jpg": f"{base}.jpg" if thumb else None, "signed": 0}
            log.info("piloto: corte %s pronto na nuvem para %s", p.clip_id, item["network"])
        if now - float(info.get("signed") or 0) > RESIGN_S:
            info["media_url"] = client.sign(info["mp4"], SIGN_S)
            info["cover_url"] = client.sign(info["jpg"], SIGN_S) if info.get("jpg") else None
            info["signed"] = now
        item["media_url"], item["cover_url"] = info["media_url"], info.get("cover_url")
    keep = {str(i["clip_id"]) for i in q["items"]} | _waiting(posted)
    for k in [k for k in files if k not in keep]:
        info = files.pop(k)
        client.remove([x for x in (info.get("mp4"), info.get("jpg")) if x])
    q["updated_at"] = datetime.now(UTC).isoformat()
    client.rpc("clipzou_pc_push", p_secret=sec, p_queue=q)
    state["queue"] = q
    _write(STATE_FILE, state)
    return {"items": q["items"], "used_this_month": q["used_this_month"], "monthly_limit": q["monthly_limit"],
            "enabled": q["enabled"], "posted_recent": posted[-6:]}


def tick() -> dict:
    s = get_settings()
    status: dict = {"at": datetime.now(UTC).isoformat()}
    try:
        with session_scope() as session:
            ws = session.exec(select(Workspace)).first()
            if not ws:
                return {}
            status.update(sync(session, ws, Supa(s.cloud_url, s.cloud_publishable)), error="")
    except CloudError as e:
        status["error"] = str(e)
        log.warning("piloto: %s", e)
    _write(STATUS_FILE, status)
    return status


def read_status() -> dict:
    return _read(STATUS_FILE, {})
