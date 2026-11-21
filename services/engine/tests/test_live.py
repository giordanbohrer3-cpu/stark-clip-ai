"""Máquina de clipes: detector de pico, chat, importador seguro, campanha, layout streamer, clipe inteiro."""
import functools
import http.server
import shutil
import subprocess
import threading

import pytest

from stark_engine import importer, media
from stark_engine.captions import build_chunks, to_ass
from stark_engine.live import twitch
from stark_engine.live.chat import parse_privmsg
from stark_engine.live.spikes import SpikeDetector
from stark_engine.render import RenderSpec, render_clip
from stark_engine.worker import run_once

from .conftest import AUTH


def drain(n: int = 20) -> None:
    for _ in range(n):
        if not run_once():
            return


def test_spike_detector_finds_burst_once():
    det = SpikeDetector(window=10, min_rate=12, cooldown=90, warmup=12)
    t = 0.0
    det.tick(t)
    for _ in range(15):  # 2,5 min de chat calmo: 3 msgs/janela
        for _ in range(3):
            det.add("canal", "boa noite")
        t += 10
        assert det.tick(t) == []
    for _ in range(45):
        det.add("canal", "KEKW KEKW kkkkk")
    t += 10
    spikes = det.tick(t)
    assert len(spikes) == 1 and spikes[0].channel == "canal"
    assert spikes[0].rate == 45 and 0 < spikes[0].score <= 100 and "kekw" in spikes[0].tokens
    for _ in range(45):
        det.add("canal", "KEKW")
    assert det.tick(t + 10) == []  # cooldown: sem pico duplicado


def test_parse_privmsg():
    assert parse_privmsg(":a!a@a.tmi.twitch.tv PRIVMSG #Gaules :olha isso KEKW") == ("gaules", "olha isso KEKW")
    tagged = "@badge-info=;color=#FF0000 :b!b@b.tmi.twitch.tv PRIVMSG #casimiro :kkkkk"
    assert parse_privmsg(tagged) == ("casimiro", "kkkkk")
    assert parse_privmsg("PING :tmi.twitch.tv") is None


def test_twitch_top_streams_parsing(monkeypatch):
    monkeypatch.setattr(twitch, "configured", lambda: True)
    monkeypatch.setattr(twitch, "_creds", lambda: ("id", "secret"))
    fake = {"data": [{"user_login": "Speed", "user_name": "IShowSpeed", "user_id": "9", "title": "GTA 6!",
                      "viewer_count": 69000, "game_name": "Grand Theft Auto VI", "language": "en",
                      "thumbnail_url": "https://x/{width}x{height}.jpg", "started_at": "2026-11-21T10:00:00Z"}],
            "pagination": {}}
    monkeypatch.setattr(twitch, "helix", lambda *a, **k: fake)
    rows = twitch.top_streams(None, [], 10)
    assert rows[0]["channel"] == "speed" and rows[0]["viewers"] == 69000
    assert rows[0]["thumbnail_url"] == "https://x/440x248.jpg" and rows[0]["url"] == "https://twitch.tv/Speed"


@pytest.mark.parametrize("url", ["http://exemplo.com/a.mp4", "https://localhost/a.mp4", "https://127.0.0.1/a.mp4",
                                 "https://10.0.0.5/a.mp4", "https://169.254.169.254/latest",
                                 "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ"])
def test_importer_guard_blocks(url):
    with pytest.raises(importer.ImportError_):
        importer.check_public(url)


def test_importer_normalizes_share_links():
    d = importer.normalize("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing")
    assert d == "https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t"
    assert "dl=1" in importer.normalize("https://www.dropbox.com/s/abc/video.mp4?dl=0")


@pytest.fixture
def tiny_mp4(data_dir):
    if not shutil.which("ffmpeg"):
        pytest.skip("requer ffmpeg")
    out = data_dir / "serve" / "camp.mp4"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15", "-f", "lavfi",
                    "-i", "sine=frequency=330", "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(out)], check=True)
    return out


def test_campaign_import_end_to_end(client, monkeypatch, tiny_mp4):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tiny_mp4.parent))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/camp.mp4"
    from stark_engine.routers import live as live_router
    monkeypatch.setattr(live_router, "check_public", lambda u: None)
    monkeypatch.setattr(importer, "check_public", lambda u: None)
    body = {"url": url, "campaign": "Campanha GTA", "evidence": "https://whop.com/x", "confirm": True,
            "credit": "twitch.tv/exemplo", "layout": "stream"}
    assert client.post("/api/v1/live/campaigns", headers=AUTH, json={**body, "confirm": False}).status_code == 422
    r = client.post("/api/v1/live/campaigns", headers=AUTH, json=body)
    assert r.status_code == 202, r.text
    drain()
    srv.shutdown()
    v = client.get(f"/api/v1/videos/{r.json()['video_id']}", headers=AUTH).json()
    assert v["video"]["origin"] == "campaign" and v["video"]["rights_ok"]
    assert v["rights"][0]["rights_type"] == "licensed" and v["rights"][0]["holder"] == "Campanha GTA"


def test_campaign_rejects_youtube(client):
    r = client.post("/api/v1/live/campaigns", headers=AUTH, json={
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "campaign": "x y", "confirm": True})
    assert r.status_code == 422 and "YouTube" in r.json()["detail"]


def test_whole_clip_auto_render_and_feed(client, data_dir, tiny_mp4):
    with tiny_mp4.open("rb") as f:
        v = client.post("/api/v1/videos/upload", headers=AUTH, files={"file": ("clip.mp4", f, "video/mp4")},
                        data={"rights_type": "creator_permission", "holder": "canal_teste", "confirm": "true"}).json()
    from stark_engine.db import session_scope
    from stark_engine.jobqueue import enqueue
    with session_scope() as s:
        enqueue(s, 1, "analyze", v["id"], {"whole": True, "auto_render": True, "layout": "stream",
                                           "credit": "twitch.tv/canal_teste", "hint": "MOMENTO INSANO", "score": 80})
    drain()
    feed = client.get("/api/v1/feed", headers=AUTH).json()
    item = next(x for x in feed if x["video_id"] == v["id"])
    assert item["clip"]["status"] == "ready" and "output" in item["clip"]["files"]
    assert item["clip"]["caption_style"]["credit"] == "twitch.tv/canal_teste"
    ass = client.get(f"/api/v1/clips/{item['clip']['id']}/file/ass", headers=AUTH).text
    assert "twitch.tv/canal_teste" in ass and ",Title,," in ass


def test_stream_layout_output_size(data_dir, tiny_mp4):
    info = media.probe(tiny_mp4)
    spec = RenderSpec(start=0, end=3.5, layout="stream", style={"title": "Teste do título", "credit": "twitch.tv/x"})
    res = render_clip(tiny_mp4, info, [], spec, data_dir / "stream_test", preview=True)
    out = media.probe(res["video"])
    assert (out["width"], out["height"]) == (540, 960)
    assert res["layout"] in ("stream", "fit")  # sem facecam no vídeo sintético → encaixa com fundo desfocado


def test_title_and_credit_in_ass():
    chunks = build_chunks([[0.0, 0.5, "oi", 1], [0.5, 1.0, "galera", 1]])
    ass = to_ass(chunks, {"title": "O pior salto da história do GTA 6", "credit": "twitch.tv/speed"}, title_y=600)
    assert "\\an5\\pos(540,600)" in ass and "\\N" in ass and "twitch.tv/speed" in ass


def test_live_status_and_channels(client):
    st = client.get("/api/v1/live/status", headers=AUTH).json()
    assert st["radar_running"] is False and st["twitch_configured"] is False and st["game"] == "Grand Theft Auto VI"
    assert client.post("/api/v1/live/channels", headers=AUTH, json={"channel": "gaules"}).status_code == 422
    r = client.post("/api/v1/live/channels", headers=AUTH, json={
        "channel": "https://twitch.tv/Gaules", "evidence": "programa de cortes", "confirm": True})
    assert r.status_code == 201 and r.json()["channel"] == "gaules"
    assert [c["channel"] for c in client.get("/api/v1/live/channels", headers=AUTH).json()] == ["gaules"]
    assert client.get("/api/v1/live/twitch/connect", headers=AUTH).status_code == 424  # sem app Twitch configurado
