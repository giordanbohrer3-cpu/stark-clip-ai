"""Serviço do radar ao vivo:  python -m stark_engine.live.radar

- A cada 90 s: top lives da Twitch (geral + jogos escolhidos) e lives/vídeos em alta do YouTube (APIs oficiais).
- Lê o chat público dos canais da Twitch no radar e detecta picos (momentos).
- Pico em canal AUTORIZADO (você é editor) → job twitch_clip → corte pronto no feed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlmodel import delete, select

from .. import youtube
from ..config import get_settings
from ..db import init_db, session_scope
from ..jobqueue import enqueue
from ..models import ChannelGrant, Integration, LiveMoment, LiveStream, Trend, Workspace, utcnow
from ..security import ws_settings
from . import twitch
from .chat import ChatMonitor
from .spikes import SpikeDetector

log = logging.getLogger("stark.radar")
REFRESH_S = 90
STATE_FILE = "radar_state.json"
_games: dict[str, str | None] = {}


def state_path():
    return get_settings().data_dir / STATE_FILE


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text())
    except (OSError, ValueError):
        return {"running": False}


def _write_state(st: dict) -> None:
    st["updated_at"] = datetime.now(UTC).isoformat()
    state_path().write_text(json.dumps(st))


def _parse_dt(v: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
    except ValueError:
        return None


def refresh(st: dict) -> set[str]:
    """Atualiza snapshot das lives. Retorna canais Twitch para ouvir o chat."""
    with session_scope() as s:
        ws = s.exec(select(Workspace)).first()
        if not ws:
            return set()
        cfg = ws_settings(ws)["radar"]
        found: list[dict] = []
        st["twitch"] = st["youtube"] = "sem chave"
        if twitch.configured():
            try:
                langs = list(cfg.get("languages") or [])
                found += twitch.top_streams(None, langs, 40)  # famosos ao vivo agora (todas as categorias)
                for game in [cfg.get("game")] if cfg.get("game") else []:
                    if game not in _games:
                        _games[game] = twitch.game_id(game)
                    if _games[game]:
                        found += twitch.top_streams(_games[game], langs, int(cfg.get("max_channels", 80)))
                st["twitch"] = "ok"
            except (twitch.TwitchError, OSError) as e:
                st["twitch"] = f"erro: {e}"[:200]
        if get_settings().youtube_api_key:
            try:
                found += youtube.live_search(cfg.get("youtube_query") or "GTA 6 ao vivo", 15)
                if time.time() - st.get("yt_trend_at", 0) > 1800:  # vídeos em alta: a cada 30 min (cota)
                    s.exec(delete(Trend).where(Trend.workspace_id == ws.id, Trend.source == "youtube_api"))
                    for it in youtube.trending("BR", None, 30):
                        s.add(Trend(workspace_id=ws.id, source="youtube_api", region="BR", kind="video",
                                    label=it["title"][:200], url=it["url"], confidence=0.9,
                                    metric={k: it[k] for k in ("views", "likes", "comments", "channel", "duration_s",
                                                               "published_at", "thumbnail_url")},
                                    license_note="referência: só corte com autorização do dono"))
                    st["yt_trend_at"] = time.time()
                st["youtube"] = "ok"
            except (youtube.YouTubeError, OSError, ValueError) as e:
                st["youtube"] = f"erro: {e}"[:200]
        seen: dict[tuple[str, str], dict] = {}
        for f in found:
            key = (f["platform"], f["channel"])
            if key not in seen or f["viewers"] > seen[key]["viewers"]:
                seen[key] = f
        for row in s.exec(select(LiveStream).where(LiveStream.workspace_id == ws.id, LiveStream.live.is_(True))):
            if (row.platform, row.channel) not in seen:
                row.live = False
                s.add(row)
        for (plat, chan), f in seen.items():
            row = s.exec(select(LiveStream).where(LiveStream.workspace_id == ws.id, LiveStream.platform == plat,
                                                  LiveStream.channel == chan)).first() or LiveStream(
                workspace_id=ws.id, platform=plat, channel=chan)
            for k in ("display_name", "title", "viewers", "game", "language", "thumbnail_url", "url"):
                setattr(row, k, f.get(k) or getattr(row, k))
            row.broadcaster_id = f.get("broadcaster_id") or row.broadcaster_id
            row.started_at = _parse_dt(f.get("started_at")) or row.started_at
            row.live, row.seen_at = True, utcnow()
            s.add(row)
        s.commit()
        grants = {g.channel for g in s.exec(select(ChannelGrant).where(ChannelGrant.workspace_id == ws.id,
                                                                        ChannelGrant.active.is_(True),
                                                                        ChannelGrant.platform == "twitch"))}
        st["lives"] = len(seen)
        st["viewers"] = sum(f["viewers"] for f in seen.values())
        return {c for (p, c) in seen if p == "twitch"} | grants


def save_spike(sp) -> None:
    with session_scope() as s:
        ws = s.exec(select(Workspace)).first()
        live = s.exec(select(LiveStream).where(LiveStream.platform == "twitch", LiveStream.channel == sp.channel)).first()
        m = LiveMoment(workspace_id=ws.id, platform="twitch", channel=sp.channel, rate=sp.rate, baseline=sp.baseline,
                       score=sp.score, viewers=live.viewers if live else 0, tokens=sp.tokens, samples=sp.samples)
        s.add(m)
        s.commit()
        s.refresh(m)
        grant = s.exec(select(ChannelGrant).where(ChannelGrant.workspace_id == ws.id, ChannelGrant.channel == sp.channel,
                                                  ChannelGrant.active.is_(True), ChannelGrant.auto_clip.is_(True))).first()
        connected = s.exec(select(Integration).where(Integration.workspace_id == ws.id,
                                                     Integration.provider == "twitch")).first()
        if grant and connected:
            enqueue(s, ws.id, "twitch_clip", m.id)
        cutoff = utcnow() - timedelta(days=7)
        s.exec(delete(LiveMoment).where(LiveMoment.at < cutoff, LiveMoment.status == "detected"))
        s.commit()
    log.info("pico em %s: %.0f msgs (base %.1f) score %.0f", sp.channel, sp.rate, sp.baseline, sp.score)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    init_db()
    with session_scope() as s:
        ws = s.exec(select(Workspace)).first()
        cfg = ws_settings(ws)["radar"] if ws else {}
    det = SpikeDetector(k=float(cfg.get("sensitivity", 3.0)), min_rate=int(cfg.get("min_rate", 12)))
    chat = ChatMonitor(det.add)
    asyncio.create_task(chat.run())
    st: dict = {"running": True}
    last = 0.0
    while True:
        now = time.time()
        if now - last >= REFRESH_S:
            last = now
            try:
                channels = await asyncio.to_thread(refresh, st)
                chat.set_channels(channels)
            except Exception as e:
                log.exception("refresh falhou")
                st["error"] = str(e)[:200]
        for sp in det.tick(now):
            await asyncio.to_thread(save_spike, sp)
        st.update(chat="conectado" if chat.connected else (chat.error or "conectando"),
                  channels=len(chat.joined), running=True)
        _write_state(st)
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
