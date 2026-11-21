"""Transcrição local (faster-whisper) com timestamps por palavra. Custo zero de API."""
from __future__ import annotations

import logging
import threading
import wave
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import get_settings

log = logging.getLogger(__name__)
_lock = threading.Lock()


def _load_wav16k(path: Path) -> np.ndarray:
    """WAV mono 16 kHz (gerado por media.extract_audio) -> float32. Evita dependência do PyAV."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("áudio deve ser WAV mono 16 kHz")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


@lru_cache(maxsize=2)
def _model(name: str, device: str, compute: str):
    from faster_whisper import WhisperModel

    log.info("carregando whisper %s (%s/%s)", name, device, compute)
    return WhisperModel(name, device=device, compute_type=compute)


def transcribe(audio: Path, duration: float, model_name: str | None = None, language: str | None = None,
               on_progress: Callable[[float], None] | None = None) -> dict:
    s = get_settings()
    name = model_name or s.whisper_model
    with _lock:  # 1 transcrição por processo: controla RAM/CPU
        model = _model(name, s.whisper_device, s.whisper_compute)
        segments, info = model.transcribe(
            _load_wav16k(audio), language=language or s.language, word_timestamps=True, vad_filter=True,
            beam_size=5, condition_on_previous_text=False,
        )
        words, segs = [], []
        for seg in segments:
            segs.append([round(seg.start, 2), round(seg.end, 2), seg.text.strip()])
            for w in seg.words or []:
                token = w.word.strip()
                if token:
                    words.append([round(w.start, 2), round(w.end, 2), token, round(w.probability, 3)])
            if on_progress and duration:
                on_progress(min(1.0, seg.end / duration))
    return {
        "model": name, "language": info.language, "words": words, "segments": segs,
        "text": " ".join(w[2] for w in words),
    }
