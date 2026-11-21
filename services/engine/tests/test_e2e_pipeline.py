"""E2E real: vídeo autorizado -> whisper -> 3 cortes -> render 9:16 com legendas -> agenda -> exporta."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stark_engine import media
from stark_engine.worker import run_once

from .conftest import AUTH

ENGINE = Path(__file__).resolve().parent.parent
needs_tools = pytest.mark.skipif(not (shutil.which("espeak-ng") and shutil.which("ffmpeg")),
                                 reason="requer espeak-ng e ffmpeg para gerar vídeo de teste")


def drain(max_jobs: int = 20) -> None:
    for _ in range(max_jobs):
        if not run_once():
            return


@pytest.mark.e2e
@needs_tools
def test_full_pipeline(client, data_dir):
    src = data_dir / "fixture.mp4"
    subprocess.run([sys.executable, str(ENGINE / "scripts" / "make_test_video.py"), str(src)], check=True)
    with src.open("rb") as f:
        r = client.post("/api/v1/videos/upload", headers=AUTH, files={"file": ("aula.mp4", f, "video/mp4")},
                        data={"rights_type": "own", "holder": "STARK LAB (sintético)", "confirm": "true",
                              "title": "Vídeo teste", "niche": "finanças"})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert r.json()["rights_ok"] is True

    rng = client.get(f"/api/v1/videos/{vid}/media", headers={**AUTH, "Range": "bytes=0-99"})
    assert rng.status_code == 206 and len(rng.content) == 100  # seek no player

    assert client.post(f"/api/v1/videos/{vid}/process", headers=AUTH, json={}).status_code == 202
    drain()
    d = client.get(f"/api/v1/videos/{vid}", headers=AUTH).json()
    assert d["video"]["status"] == "ready", d["jobs"]
    assert d["transcript"]["words"] > 100
    cands = d["candidates"]
    assert 1 <= len(cands) <= 3
    for a in cands:
        assert a["title"] and a["justification"] and 0 <= a["score"] <= 100
        for b in cands:
            if a["id"] != b["id"]:
                assert a["end_s"] <= b["start_s"] or b["end_s"] <= a["start_s"]

    ec = client.post(f"/api/v1/candidates/{cands[0]['id']}/edit", headers=AUTH).json()
    client.patch(f"/api/v1/clips/{ec['id']}", headers=AUTH, json={"remove_pauses": True})
    assert client.post(f"/api/v1/clips/{ec['id']}/render", headers=AUTH, json={"preview": False}).status_code == 202
    drain()
    clip = client.get(f"/api/v1/clips/{ec['id']}", headers=AUTH).json()
    assert clip["status"] == "ready", clip
    assert {"output", "srt", "ass", "cover"} <= set(clip["files"])
    out = data_dir / "clips" / str(ec["id"]) / "clip.mp4"
    info = media.probe(out)
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
    assert "-->" in client.get(f"/api/v1/clips/{ec['id']}/file/srt", headers=AUTH).text
    assert clip["copy_text"]["captions"]["tiktok"]

    acc = client.post("/api/v1/accounts", headers=AUTH, json={"platform": "tiktok", "handle": "@stark.cortes",
                                                               "niche": "finanças", "daily_cap": 5}).json()
    post = client.post("/api/v1/posts", headers=AUTH, json={"edited_clip_id": ec["id"], "account_id": acc["id"],
                                                             "mode": "export"})
    assert post.status_code == 201, post.text
    dup = client.post("/api/v1/posts", headers=AUTH, json={"edited_clip_id": ec["id"], "account_id": acc["id"]})
    assert dup.status_code == 409  # anti-duplicado
    pid = post.json()["id"]
    from stark_engine.db import session_scope
    from stark_engine.models import ScheduledPost, utcnow
    with session_scope() as s:  # força vencimento
        p = s.get(ScheduledPost, pid)
        p.scheduled_at = utcnow()
        s.add(p)
        s.commit()
    drain()
    assert client.get("/api/v1/posts", headers=AUTH).json()[0]["status"] == "scheduled"  # sem aprovação não sai
    client.patch(f"/api/v1/posts/{pid}", headers=AUTH, json={"approved": True})
    drain()
    row = next(p for p in client.get("/api/v1/posts", headers=AUTH).json() if p["id"] == pid)
    assert row["status"] == "exported"
    assert (data_dir / row["export_dir"] / "video.mp4").exists()
    assert (data_dir / row["export_dir"] / "caption.txt").read_text()

    st = client.get("/api/v1/stats", headers=AUTH).json()
    assert st["videos"]["analyzed"] >= 1 and st["clips"]["ready"] >= 1
