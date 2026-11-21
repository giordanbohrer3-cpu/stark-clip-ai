"""Utilitários FFmpeg/FFprobe. Sempre lista de args (sem shell) -> sem injeção de comando."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import wave
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import get_settings

log = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


class Canceled(RuntimeError):
    pass


def tool_ok(name: str) -> bool:
    return shutil.which(name) is not None


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def probe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise MediaError("arquivo não é mídia válida") from e
    data = json.loads(out or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    if not video:
        raise MediaError("sem trilha de vídeo")
    num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    w, h = int(video.get("width", 0)), int(video.get("height", 0))
    rot = int((video.get("tags") or {}).get("rotate", 0) or 0)
    for sd in video.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) in (90, 270):
        w, h = h, w
    return {
        "duration": duration, "width": w, "height": h, "fps": round(fps, 3),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "vcodec": video.get("codec_name"),
    }


def extract_audio(src: Path, dst: Path) -> Path:
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(dst)], check=True, timeout=3600)
    return dst


def audio_energy(wav_path: Path, win_s: float = 0.5) -> np.ndarray:
    """RMS em dB por janela. Proxy de intensidade/emoção da fala."""
    with wave.open(str(wav_path), "rb") as w:
        sr, n = w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = max(1, int(sr * win_s))
    frames = len(x) // hop
    if frames == 0:
        return np.zeros(0)
    rms = np.sqrt(np.mean(x[: frames * hop].reshape(frames, hop) ** 2, axis=1) + 1e-10)
    return 20 * np.log10(rms + 1e-9)


def detect_scenes(src: Path, threshold: float = 0.35, timeout: int = 1800) -> list[float]:
    """Cortes de cena via filtro 'scene' do FFmpeg (sem dependência extra)."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "info", "-i", str(src), "-an", "-vf",
         f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=timeout,
    )
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]


def grab_frame(src: Path, t: float, dst: Path, width: int | None = None) -> Path:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(src),
                    "-frames:v", "1", *vf, "-q:v", "3", str(dst)], check=True, timeout=120)
    return dst


@lru_cache
def video_encoder() -> list[str]:
    """libx264 por padrão; NVENC se disponível e permitido (STARK_HWACCEL)."""
    mode = get_settings().hwaccel
    if mode in ("auto", "nvenc"):
        try:
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                            "-c:v", "h264_nvenc", "-f", "null", "-"], check=True, timeout=30, capture_output=True)
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-b:v", "0"]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            if mode == "nvenc":
                log.warning("NVENC pedido mas indisponível; usando libx264")
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def run_ffmpeg(args: list[str], duration: float, on_progress: Callable[[float], None] | None = None,
               should_cancel: Callable[[], bool] | None = None, cwd: Path | None = None) -> None:
    """Executa ffmpeg com progresso (-progress pipe:1) e cancelamento cooperativo."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    assert proc.stdout is not None
    last = 0.0
    for line in proc.stdout:
        if line.startswith("out_time_us=") and duration > 0:
            try:
                frac = min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration)
            except ValueError:
                continue
            if on_progress and frac - last >= 0.02:
                last = frac
                on_progress(frac)
            if should_cancel and should_cancel():
                proc.kill()
                proc.wait()
                raise Canceled("cancelado")
    err = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise MediaError(f"ffmpeg falhou: {err.strip()[-800:]}")
