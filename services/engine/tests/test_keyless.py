"""Radar sem chave (feed público do YouTube + famosos da Twitch pelo chat) e pasta de entrada."""
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from stark_engine import youtube
from stark_engine.db import session_scope
from stark_engine.live import radar, twitch
from stark_engine.live.spikes import SpikeDetector
from stark_engine.models import Job, LiveStream, RightsGrant, SourceVideo
from stark_engine.security import DEFAULT_SETTINGS

from .conftest import AUTH

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <title>alanzoka</title>
 <entry>
  <yt:videoId>pI5sCwoJluc</yt:videoId>
  <yt:channelId>UCIwspRtKNszHhIhl36gREjQ</yt:channelId>
  <title>TRETA NO ACAMPAMENTO - GTA 6 - Parte 5</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=pI5sCwoJluc"/>
  <author><name>alanzoka</name></author>
  <published>2026-11-20T21:23:45+00:00</published>
  <media:group>
   <media:thumbnail url="https://i1.ytimg.com/vi/pI5sCwoJluc/hqdefault.jpg" width="480" height="360"/>
   <media:community>
    <media:starRating count="7508" average="5.00" min="1" max="5"/>
    <media:statistics views="211675"/>
   </media:community>
  </media:group>
 </entry>
 <entry>
  <yt:videoId>abcdefghijk</yt:videoId>
  <title>short</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/abcdefghijk"/>
  <author><name>alanzoka</name></author>
  <published>2026-11-21T01:00:00+00:00</published>
 </entry>
 <entry><yt:videoId>invalido</yt:videoId><title>x</title></entry>
</feed>"""


def test_parse_feed_reads_views_likes_and_shorts():
    vids = youtube.parse_feed(FEED)
    assert len(vids) == 2
    v = vids[0]
    assert v["youtube_id"] == "pI5sCwoJluc" and v["channel"] == "alanzoka" and v["views"] == 211675
    assert v["likes"] == 7508 and not v["short"] and v["url"] == "https://www.youtube.com/watch?v=pI5sCwoJluc"
    assert vids[1]["short"] and vids[1]["views"] == 0 and "hqdefault" in vids[1]["thumbnail_url"]


def test_parse_feed_rejects_entities():
    with pytest.raises(youtube.YouTubeError):
        youtube.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><feed>&a;</feed>')


def test_channel_id_accepts_id_and_link():
    cid = "UCIwspRtKNszHhIhl36gREjQ"
    assert youtube.channel_id(cid) == cid
    assert youtube.channel_id(f"https://www.youtube.com/channel/{cid}/videos") == cid
    for bad in ("@alanzoka", "UCcurto", cid + "XX"):
        with pytest.raises(youtube.YouTubeError):
            youtube.channel_id(bad)


def test_chat_activity_per_minute():
    det = SpikeDetector(window=10)
    det.tick(0)
    for _ in range(20):
        det.add("gaules", "boa")
    det.tick(10)
    assert det.activity() == {"gaules": 120}


def test_radar_keyless_shows_live_famous_and_hot_videos(client, monkeypatch):
    fresh = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    vids = [{"youtube_id": "aaaaaaaaaaa", "title": "GTA 6 insano", "channel": "alanzoka", "channel_id": "UCx",
             "published_at": fresh, "thumbnail_url": "https://i.ytimg.com/vi/a/hq.jpg", "views": 200000, "likes": 10,
             "short": False, "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},
            {"youtube_id": "bbbbbbbbbbb", "title": "vídeo velho", "channel": "x", "channel_id": "UCy",
             "published_at": "2020-01-01T00:00:00+00:00", "thumbnail_url": "", "views": 9_000_000, "likes": 1,
             "short": False, "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"}]
    monkeypatch.setattr(youtube, "channel_feeds", lambda ids: (vids, len(ids)))
    monkeypatch.setattr(twitch, "configured", lambda: False)
    st = {"running": True, "activity": {"gaules": 150, "xqc": 3}}
    try:
        channels = radar.refresh(st)
        radar._write_state(st)
        assert {"gaules", "xqc", "alanzoka"} <= channels  # ouve o chat da lista de famosos
        with session_scope() as s:
            live = {r.channel for r in s.exec(select(LiveStream).where(LiveStream.live.is_(True)))}
        assert "gaules" in live and "xqc" not in live  # chat ativo = ao vivo
        rows = client.get("/api/v1/live/streams", headers=AUTH).json()
        g = next(r for r in rows if r["channel"] == "gaules")
        assert g["chat_rate"] == 150 and "previews-ttv/live_user_gaules" in g["thumbnail_url"]
        hot = client.get("/api/v1/live/videos", headers=AUTH).json()
        assert [h["title"] for h in hot] == ["GTA 6 insano"]  # velho (>14 dias) fica de fora
        assert hot[0]["views_per_hour"] > 50000 and hot[0]["source"] == "youtube_rss"
        stt = client.get("/api/v1/live/status", headers=AUTH).json()
        assert stt["keyless"] and stt["youtube_rss"] == "16/16 canais"
        assert stt["chat_rate"] == 153 and stt["lives"] >= 1
    finally:
        radar.state_path().unlink(missing_ok=True)
        with session_scope() as s:
            for r in s.exec(select(LiveStream)):
                s.delete(r)
            s.commit()


def test_settings_normalize_radar_lists(client):
    r = client.patch("/api/v1/settings", headers=AUTH, json={"data": {"radar": {
        "watch_twitch": ["https://www.twitch.tv/Gaules", "@xQc", "gaules"],
        "youtube_channels": ["https://www.youtube.com/channel/UCIwspRtKNszHhIhl36gREjQ"]}}})
    assert r.status_code == 200, r.text
    radar_cfg = r.json()["settings"]["radar"]
    assert radar_cfg["watch_twitch"] == ["gaules", "xqc"]
    assert radar_cfg["youtube_channels"] == ["UCIwspRtKNszHhIhl36gREjQ"]
    bad = client.patch("/api/v1/settings", headers=AUTH, json={"data": {"radar": {"youtube_channels": ["@alanzoka"]}}})
    assert bad.status_code == 422
    sneaky = client.patch("/api/v1/settings", headers=AUTH, json={"data": {"inbox": {"confirmed": True}}})
    assert sneaky.status_code == 422  # declaração só pela rota própria (auditada)
    full = client.get("/api/v1/settings", headers=AUTH).json()["settings"]  # tela salva tudo: sem mudança, ok
    assert client.patch("/api/v1/settings", headers=AUTH, json={"data": full}).status_code == 200
    d = DEFAULT_SETTINGS["radar"]
    client.patch("/api/v1/settings", headers=AUTH, json={"data": {"radar": {
        "watch_twitch": d["watch_twitch"], "youtube_channels": d["youtube_channels"]}}})


@pytest.fixture
def inbox_dir(client, data_dir):
    if not shutil.which("ffmpeg"):
        pytest.skip("requer ffmpeg")
    d = data_dir / "Entrada"
    d.mkdir(exist_ok=True)
    f = d / "meu_video_gta.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10", "-f", "lavfi",
                    "-i", "sine=frequency=330", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(f)], check=True)
    (d / "anotacao.txt").write_text("ignorar")
    old = time.time() - 60
    os.utime(f, (old, old))  # já terminou de copiar
    assert client.patch("/api/v1/settings", headers=AUTH, json={"data": {"inbox": {"path": str(d)}}}).status_code == 200
    yield d
    client.delete("/api/v1/inbox/confirm", headers=AUTH)
    client.patch("/api/v1/settings", headers=AUTH, json={"data": {"inbox": {"path": ""}}})


def test_inbox_needs_declaration_then_imports_once(client, inbox_dir):
    st = client.get("/api/v1/inbox", headers=AUTH).json()
    assert st["path"] == str(inbox_dir) and not st["confirmed"]
    assert [p["name"] for p in st["pending"]] == ["meu_video_gta.mp4"]
    assert client.post("/api/v1/inbox/scan", headers=AUTH).json()["status"] == "aguardando declaração"
    assert client.post("/api/v1/inbox/confirm", headers=AUTH, json={"confirm": False}).status_code == 422
    r = client.post("/api/v1/inbox/confirm", headers=AUTH, json={"confirm": True, "rights_type": "licensed",
                                                                 "holder": "Campanha GTA"})
    assert r.status_code == 200 and r.json()["imported"] == 1, r.text
    assert client.post("/api/v1/inbox/scan", headers=AUTH).json()["imported"] == 0  # não duplica
    st = client.get("/api/v1/inbox", headers=AUTH).json()
    assert st["confirmed"] and st["pending"] == [] and st["imported"] == 1
    assert (inbox_dir / "meu_video_gta.mp4").exists()  # nunca apaga o arquivo do usuário
    with session_scope() as s:
        v = s.exec(select(SourceVideo).where(SourceVideo.origin == "inbox")).one()
        g = s.exec(select(RightsGrant).where(RightsGrant.video_id == v.id)).one()
        job = s.exec(select(Job).where(Job.kind == "analyze", Job.ref_id == v.id)).one()
        assert v.title == "meu video gta" and v.has_audio and g.rights_type == "licensed"
        assert g.holder == "Campanha GTA" and "pasta de entrada" in g.evidence
        assert job.payload["auto_render"] is True
    queue = client.get("/api/v1/feed/queue", headers=AUTH).json()
    assert any(q["kind"] == "analyze" and q["title"] == "meu video gta" for q in queue)
    with session_scope() as s:  # não deixa o job para os outros testes
        job = s.get(Job, job.id)
        job.status = "canceled"
        s.add(job)
        s.commit()


def test_system_version_and_update(client, monkeypatch):
    from stark_engine.routers import system
    v = client.get("/api/v1/system/version", headers=AUTH).json()
    assert v["auto_update_min"] == 15 and "service" in v
    calls = []

    def fake_git(*args, timeout=20):
        calls.append(args)
        return {"rev-parse": "abc" if args[-1] == "HEAD" else "def"}.get(args[0], "")

    monkeypatch.setattr(system, "_git", fake_git)
    monkeypatch.setattr(system, "FLAG", system.FLAG.parent / "update_now_test")
    r = client.post("/api/v1/system/update", headers=AUTH).json()
    assert r["update"] is True and system.FLAG.exists() and ("fetch", "-q") in calls
    system.FLAG.unlink()
    monkeypatch.setattr(system, "_git", lambda *a, timeout=20: "same" if a[0] == "rev-parse" else "")
    assert client.post("/api/v1/system/update", headers=AUTH).json()["update"] is False


def test_phone_link_uses_tailscale_when_no_online_app(client, monkeypatch):
    from stark_engine.routers import system
    monkeypatch.setattr(system, "_tailscale", lambda: {"url": "https://meu-pc.tail.ts.net", "serving": True})
    monkeypatch.setattr(system.cloud, "load_config", lambda: {"app_url": ""})  # sem app online configurado
    r = client.get("/api/v1/system/phone", headers=AUTH).json()
    assert r["url"] == "https://meu-pc.tail.ts.net" and r["tailscale_serving"] is True
