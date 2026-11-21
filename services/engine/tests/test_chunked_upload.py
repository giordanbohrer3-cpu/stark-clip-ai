"""Upload em partes (necessário atrás do Cloudflare: limite de 100 MB por requisição)."""
import shutil
import subprocess

import pytest

from stark_engine.routers import videos

from .conftest import AUTH


@pytest.fixture
def tiny_video(data_dir):
    if not shutil.which("ffmpeg"):
        pytest.skip("requer ffmpeg")
    out = data_dir / "tiny.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(out)], check=True)
    return out.read_bytes()


def test_chunked_upload_roundtrip(client, monkeypatch, tiny_video):
    monkeypatch.setattr(videos, "CHUNK", 16 * 1024)
    body = {"filename": "celular.mp4", "size": len(tiny_video), "rights_type": "own", "holder": "Eu mesmo",
            "confirm": True, "title": "Gravado no celular"}
    r = client.post("/api/v1/videos/uploads", headers=AUTH, json=body)
    assert r.status_code == 201, r.text
    sess = r.json()
    assert sess["chunks"] == -(-len(tiny_video) // (16 * 1024)) and sess["chunks"] > 1
    uid, size = sess["upload_id"], sess["chunk_size"]
    early = client.post(f"/api/v1/videos/uploads/{uid}/complete", headers=AUTH)
    assert early.status_code == 409  # faltam partes
    for i in reversed(range(sess["chunks"])):  # ordem qualquer (retentativas no celular)
        part = tiny_video[i * size:(i + 1) * size]
        assert client.put(f"/api/v1/videos/uploads/{uid}/{i}", headers=AUTH, content=part).status_code == 204
    done = client.post(f"/api/v1/videos/uploads/{uid}/complete", headers=AUTH)
    assert done.status_code == 201, done.text
    v = done.json()
    assert v["rights_ok"] and v["has_file"] and v["size_bytes"] == len(tiny_video) and v["duration_s"] > 1


def test_chunked_upload_guards(client, monkeypatch):
    monkeypatch.setattr(videos, "CHUNK", 1024)
    base = {"filename": "a.mp4", "size": 3000, "rights_type": "own", "holder": "Eu", "confirm": True}
    assert client.post("/api/v1/videos/uploads", headers=AUTH, json={**base, "confirm": False}).status_code == 422
    assert client.post("/api/v1/videos/uploads", headers=AUTH, json={**base, "filename": "a.exe"}).status_code == 415
    uid = client.post("/api/v1/videos/uploads", headers=AUTH, json=base).json()["upload_id"]
    assert client.put(f"/api/v1/videos/uploads/{uid}/9", headers=AUTH, content=b"x").status_code == 422
    assert client.put(f"/api/v1/videos/uploads/{uid}/0", headers=AUTH, content=b"x" * 2048).status_code == 413
    assert client.put("/api/v1/videos/uploads/..%2F..%2Fetc/0", headers=AUTH, content=b"x").status_code == 404
    junk = client.post(f"/api/v1/videos/uploads/{uid}/complete", headers=AUTH)
    assert junk.status_code == 409
