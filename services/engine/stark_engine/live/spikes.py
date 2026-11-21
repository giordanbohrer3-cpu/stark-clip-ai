"""Detector de pico de chat: mensagens por janela vs. linha de base (média/desvio exponenciais).

Um "momento" = chat acima de k desvios E 2.5x a média, com mínimo absoluto e intervalo entre picos.
Emotes de reação (KEKW, LUL, kkk, ???) aumentam o score.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

REACTION = {"kekw", "lul", "lmao", "omegalul", "pog", "pogchamp", "poggers", "pogu", "w", "l", "clip", "clipped",
            "monkas", "pepelaugh", "lol", "kkk", "kkkk", "kkkkk", "aaaa", "ratio", "sheesh", "wtf", "omg", "????"}
WORD = re.compile(r"[\wÀ-ÿ?!]+", re.UNICODE)


@dataclass
class Spike:
    channel: str
    at: float  # epoch (fim da janela)
    rate: float  # msgs por janela
    baseline: float
    score: float  # 0-100
    tokens: list[str] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)


@dataclass
class _Chan:
    mean: float = 0.0
    var: float = 0.0
    n: int = 0
    last_spike: float = -1e9
    count: int = 0
    tokens: Counter = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)


def _norm_token(t: str) -> str:
    t = t.lower()
    if re.fullmatch(r"k{3,}", t):
        return "kkk"
    if re.fullmatch(r"\?{2,}", t):
        return "????"
    return t


class SpikeDetector:
    def __init__(self, window: float = 10.0, alpha: float = 0.08, k: float = 3.0, min_rate: int = 12,
                 cooldown: float = 90.0, warmup: int = 12):
        self.window, self.alpha, self.k = window, alpha, k
        self.min_rate, self.cooldown, self.warmup = min_rate, cooldown, warmup
        self.chans: dict[str, _Chan] = defaultdict(_Chan)
        self.window_start: float | None = None

    def add(self, channel: str, text: str) -> None:
        c = self.chans[channel]
        c.count += 1
        for t in WORD.findall(text)[:8]:
            c.tokens[_norm_token(t)] += 1
        if len(c.samples) < 6 and 3 <= len(text) <= 120:
            c.samples.append(text)

    def tick(self, now: float) -> list[Spike]:
        """Fecha a janela se passou `window` segundos. Retorna picos detectados."""
        if self.window_start is None:
            self.window_start = now
            return []
        if now - self.window_start < self.window:
            return []
        self.window_start = now
        out = []
        for name, c in self.chans.items():
            rate = float(c.count)
            std = math.sqrt(c.var) if c.var > 0 else 1.0
            is_spike = (c.n >= self.warmup and rate >= self.min_rate and rate >= c.mean + self.k * std
                        and rate >= 2.5 * max(c.mean, 1.0) and now - c.last_spike >= self.cooldown)
            if is_spike:
                react = sum(v for t, v in c.tokens.items() if t in REACTION)
                z = (rate - c.mean) / std
                score = min(100.0, 40 + z * 8 + min(20.0, react / max(rate, 1) * 30))
                top = [t for t, _ in c.tokens.most_common(12) if len(t) > 1 or t in ("w", "l")][:6]
                out.append(Spike(name, now, rate, round(c.mean, 2), round(score, 1), top, list(c.samples)))
                c.last_spike = now
            else:  # pico não contamina a linha de base
                d = rate - c.mean
                c.mean += self.alpha * d if c.n else d
                c.var = (1 - self.alpha) * (c.var + self.alpha * d * d)
                c.n += 1
            c.count, c.tokens, c.samples = 0, Counter(), []
        return out

    def activity(self) -> dict[str, int]:
        """Mensagens por minuto (média móvel) de cada canal ouvido. Chat ativo ≈ live no ar."""
        return {name: round(c.mean * 60 / self.window) for name, c in self.chans.items() if c.n}

    def forget(self, channel: str) -> None:
        self.chans.pop(channel, None)
