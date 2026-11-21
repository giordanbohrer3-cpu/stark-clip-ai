"""Motor heurístico de cortes: local, custo zero, explicável.

Fluxo: palavras -> frases -> janelas candidatas (limites de frase) -> features -> score 0-100
-> seleção gulosa sem sobreposição e sem redundância temática. Nunca força 3 cortes ruins.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

STOP = set(
    """a o os as um uma uns umas de do da dos das em no na nos nas por para pra pro pros com sem que e é ou se
    mas mais muito muita já não sim eu tu ele ela nós eles elas você vocês voce me te lhe meu minha seu sua
    isso isto aquilo esse essa este esta aquele aquela aí lá aqui então tipo né tá ta foi ser ter tem tinha
    vai vou era são está estava estão como quando onde porque qual quais quem ao aos à às pelo pela pelos
    pelas num numa entre até sobre também só ainda bem coisa coisas gente fazer faz fez pode podia vamos
    agora hoje depois antes sempre nunca tudo todo toda todos todas cara assim aqui ali vez vezes acho
    the an and or of to in on for is are was were be it this that you we they have has had with what""".split()
)
HOOK = ("segredo", "ninguém", "ninguem", "erro", "verdade", "nunca", "pare", "cuidado", "descobri", "maior",
        "pior", "melhor", "dinheiro", "imagina", "olha", "atenção", "atencao", "proibido", "mentira",
        "ninguém te conta", "por que", "porque você", "o que acontece", "como eu", "o motivo", "sabia",
        "chocante", "polêmic", "polemic", "revelou", "real", "fato", "dica", "truque", "jeito")
EMO = ("absurdo", "incrível", "incrivel", "inacreditável", "louco", "loucura", "chocante", "demais", "surreal",
       "sensacional", "impressionante", "bizarro", "medo", "raiva", "amo", "odeio", "perfeito", "horrível",
       "kkk", "haha", "risos", "nossa", "caramba", "meu deus", "putz", "uau")
CONCLUSION = ("então", "portanto", "resumindo", "conclusão", "ou seja", "por isso", "no fim", "resultado",
              "finalmente", "a lição", "moral")
FILLER_START = {"e", "é", "então", "tipo", "aí", "né", "mas", "porque", "que", "ah", "eh", "hum", "bom", "and", "so"}
DANGLING_END = {"e", "mas", "porque", "que", "de", "do", "da", "o", "a", "um", "uma", "com", "pra", "para", "se",
                "então", "tipo", "the", "and", "to", "of"}
CTA = ("se inscrev", "deixa o like", "deixe o like", "deixa seu like", "ativa o sino", "sininho",
       "link na descri", "fala galera", "fala pessoal", "bem-vindo", "bem vindo", "patrocin", "cupom",
       "compartilha esse", "subscribe")
WEIGHTS = {"hook": 0.24, "closure": 0.14, "energy": 0.14, "density": 0.08, "emotion": 0.10,
           "cohesion": 0.12, "dur_fit": 0.12, "scenes": 0.06}


def norm(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def content_words(text: str) -> list[str]:
    return [w for w in norm(text).split() if len(w) >= 4 and w not in STOP and not w.isdigit()]


@dataclass
class Sentence:
    idx: int
    start: float
    end: float
    words: list  # [[s, e, w, p], ...]
    text: str = ""

    def __post_init__(self) -> None:
        self.text = " ".join(w[2] for w in self.words)


@dataclass
class Window:
    i: int
    j: int
    start: float
    end: float
    score: float = 0
    features: dict = field(default_factory=dict)
    keywords: list = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


def build_sentences(words: list, max_gap: float = 1.2, max_len: float = 14.0) -> list[Sentence]:
    out: list[Sentence] = []
    cur: list = []

    def flush() -> None:
        if cur:
            out.append(Sentence(len(out), cur[0][0], cur[-1][1], list(cur)))
            cur.clear()

    for w in words:
        if cur and (w[0] - cur[-1][1] > max_gap or cur[-1][1] - cur[0][0] > max_len):
            flush()
        cur.append(w)
        if re.search(r"[.!?…]['\"]?$", w[2]):
            flush()
    flush()
    return out


def duration_bounds(total: float, mode: str = "short") -> tuple[float, float, float]:
    """Faixa adaptativa (min, max, ideal) segundo duração do vídeo e objetivo."""
    if mode == "long":  # monetização: >60s (ex.: requisitos de programas de criador)
        lo, hi, ideal = 61.0, 180.0, 95.0
    else:
        ideal = min(55.0, max(22.0, total * 0.06))
        lo = min(30.0, max(10.0, ideal * 0.45))
        hi = min(90.0, max(35.0, ideal * 2.0))
    if total < hi * 1.2:  # vídeo curto: faixa cabe no vídeo
        lo, hi = min(lo, max(5.0, total * 0.25)), min(hi, total * 0.9)
        ideal = min(max(ideal, lo), hi)
    return lo, hi, ideal


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class ClipAnalyzer:
    def __init__(self, words: list, total: float, energy_db: np.ndarray | None = None,
                 scenes: list[float] | None = None, mode: str = "short", energy_win: float = 0.5):
        self.total = total
        self.mode = mode
        self.sents = build_sentences(words)
        self.scenes = sorted(scenes or [])
        self.lo, self.hi, self.ideal = duration_bounds(total, mode)
        e = np.asarray(energy_db if energy_db is not None else [], dtype=float)
        self.energy_win = energy_win
        if e.size:
            voiced = e[e > np.percentile(e, 20)] if e.size > 10 else e
            voiced = voiced if voiced.size else e
            self.e_mu, self.e_sd = float(voiced.mean()), float(voiced.std() or 1.0)
        else:
            self.e_mu, self.e_sd = 0.0, 1.0
        self.energy = e
        rates = [len(s.words) / max(0.3, s.end - s.start) for s in self.sents]
        self.median_wps = float(np.median(rates)) if rates else 2.5

    # ------------------------------------------------------------------ features
    def _energy_feat(self, start: float, end: float) -> float:
        if not self.energy.size:
            return 0.5
        a, b = int(start / self.energy_win), max(int(start / self.energy_win) + 1, int(end / self.energy_win))
        seg = self.energy[a:b]
        if not seg.size:
            return 0.5
        z = (seg - self.e_mu) / self.e_sd
        return 0.6 * _sigmoid(float(z.mean()) * 1.5) + 0.4 * min(1.0, float((z > 1.0).mean()) * 3)

    def features(self, i: int, j: int) -> dict:
        ss = self.sents[i: j + 1]
        start, end = ss[0].start, ss[-1].end
        dur = max(0.1, end - start)
        words = [w for s in ss for w in s.words]
        text = " ".join(s.text for s in ss)
        low = text.lower()
        first, last = ss[0], ss[-1]
        f_low = first.text.lower()

        hook = 0.0
        if "?" in first.text:
            hook += 0.35
        hook += min(0.35, 0.18 * sum(h in f_low for h in HOOK))
        hook += 0.15 if re.search(r"\d", f_low) else 0
        hook += 0.10 if re.search(r"\b(você|voce|vc|tu)\b", f_low) else 0
        hook += 0.10 if len(first.words) <= 14 else 0
        if norm(first.words[0][2]) in FILLER_START:
            hook -= 0.25

        last_tok = norm(last.words[-1][2])
        closure = (0.5 if re.search(r"[.!?…]['\"]?$", last.text) else 0) + (0.3 if last_tok not in DANGLING_END else 0)
        tail = " ".join(s.text for s in ss[-2:]).lower()
        closure += 0.2 if any(c in tail for c in CONCLUSION) else 0

        speech = sum(w[1] - w[0] for w in words) or dur
        rel = (len(words) / speech) / max(0.5, self.median_wps)
        density = math.exp(-(((rel - 1.15) / 0.35) ** 2))

        emo_hits = low.count("!") + sum(low.count(e) for e in EMO)
        emotion = 1 - math.exp(-(emo_hits / (dur / 60)) / 3)

        cw = content_words(text)
        cnt = Counter(cw)
        cohesion = min(1.0, (sum(c for _, c in cnt.most_common(3)) / max(1, len(cw))) * 2.5) if cw else 0.0

        gaps = sum(max(0.0, words[k + 1][0] - words[k][1]) for k in range(len(words) - 1)
                   if words[k + 1][0] - words[k][1] > 0.7)
        silence = min(1.0, gaps / dur)
        cta = 1.0 if any(c in low for c in CTA) else 0.0
        cuts = sum(1 for t in self.scenes if start <= t <= end)
        scenes = 1 - math.exp(-(cuts / (dur / 60)) / 4) if self.scenes else 0.3
        dur_fit = math.exp(-(((dur - self.ideal) / (self.ideal * 0.45)) ** 2))

        f = {"hook": hook, "closure": closure, "energy": self._energy_feat(start, end), "density": density,
             "emotion": emotion, "cohesion": cohesion, "dur_fit": dur_fit, "scenes": scenes}
        f = {k: round(max(0.0, min(1.0, v)), 3) for k, v in f.items()}
        f["silence_pen"] = round(silence, 3)
        f["cta_pen"] = cta
        f["_kw"] = [w for w, _ in cnt.most_common(6)]
        return f

    @staticmethod
    def combine(f: dict) -> float:
        base = sum(WEIGHTS[k] * f[k] for k in WEIGHTS)
        base *= 1 - 0.5 * f["silence_pen"]
        return round(max(0.0, min(100.0, base * 100 - 15 * f["cta_pen"])), 1)

    def window(self, i: int, j: int) -> Window:
        f = self.features(i, j)
        kw = f.pop("_kw")
        w = Window(i, j, self.sents[i].start, self.sents[j].end, features=f, keywords=kw)
        w.score = self.combine(f)
        return w

    # ------------------------------------------------------------------ busca
    def candidates(self) -> list[Window]:
        out = []
        n = len(self.sents)
        for i in range(n):
            for j in range(i, n):
                dur = self.sents[j].end - self.sents[i].start
                if dur > self.hi:
                    break
                if dur >= self.lo:
                    out.append(self.window(i, j))
        return out

    def select(self, target: int = 3, min_score: float = 35) -> tuple[list[Window], str]:
        if not self.sents:
            return [], "sem fala detectada"
        cands = sorted(self.candidates(), key=lambda w: w.score, reverse=True)
        if not cands:
            return [], f"conteúdo insuficiente para cortes de {self.lo:.0f}-{self.hi:.0f}s"
        chosen: list[Window] = []
        for c in cands:
            if c.score < min_score:
                break
            if any(c.start < d.end and d.start < c.end for d in chosen):
                continue
            if any(_jaccard(c.keywords, d.keywords) > 0.5 for d in chosen):
                continue
            chosen.append(c)
            if len(chosen) == target:
                break
        note = "" if len(chosen) == target else (
            f"{len(chosen)} corte(s) com qualidade mínima (score≥{min_score:.0f}); não criamos cortes artificiais")
        return chosen, note

    def locate(self, start: float, end: float) -> tuple[int, int]:
        idx = [s.idx for s in self.sents if s.end > start and s.start < end]
        if not idx:
            raise ValueError("intervalo sem fala")
        return idx[0], idx[-1]

    def expand(self, start: float, end: float, lo: float = 61.0, hi: float = 180.0) -> Window:
        """Versão longa: estende por frases inteiras escolhendo o lado com melhor score."""
        i, j = self.locate(start, end)
        best = self.window(i, j)
        while best.duration < lo:
            opts = []
            if j + 1 < len(self.sents) and self.sents[j + 1].end - self.sents[i].start <= hi:
                opts.append(self.window(i, j + 1))
            if i > 0 and self.sents[j].end - self.sents[i - 1].start <= hi:
                opts.append(self.window(i - 1, j))
            if not opts:
                break
            best = max(opts, key=lambda w: w.score)
            i, j = best.i, best.j
        return best

    # ------------------------------------------------------------------ texto
    def describe(self, w: Window) -> dict:
        ss = self.sents[w.i: w.j + 1]
        f = w.features
        hook_sent = ss[0] if f["hook"] >= 0.3 or len(ss) == 1 else max(
            ss[:3], key=lambda s: s.text.count("?") + s.text.count("!") + len(content_words(s.text)) / 10)
        title = _trim(hook_sent.text, 70)
        reasons = []
        if f["hook"] >= 0.5:
            reasons.append("abertura forte" + (" com pergunta" if "?" in ss[0].text else ""))
        if f["energy"] >= 0.6:
            reasons.append("pico de energia na fala")
        if f["emotion"] >= 0.4:
            reasons.append("carga emocional")
        if f["closure"] >= 0.7:
            reasons.append("conclusão clara")
        if f["cohesion"] >= 0.6:
            reasons.append("tema coeso" + (f" ({', '.join(w.keywords[:2])})" if w.keywords else ""))
        if f["dur_fit"] >= 0.7:
            reasons.append(f"duração {w.duration:.0f}s na faixa ideal ({self.lo:.0f}-{self.hi:.0f}s)")
        warns = []
        if f["silence_pen"] > 0.15:
            warns.append("pausas longas (use remover pausas)")
        if f["cta_pen"]:
            warns.append("contém CTA/intro")
        if f["hook"] < 0.3:
            warns.append("início fraco: considere novo gancho em texto")
        just = "; ".join(reasons) or "melhor equilíbrio disponível entre gancho, ritmo e duração"
        if warns:
            just += ". Atenção: " + "; ".join(warns)
        kw = ", ".join(w.keywords[:3])
        return {
            "title": title,
            "hook": _trim(ss[0].text, 120),
            "summary": (f"Sobre {kw}. " if kw else "") + _trim(" ".join(s.text for s in ss[:2]), 180),
            "justification": just,
            "transcript_text": " ".join(s.text for s in ss),
        }


def _trim(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _jaccard(a: list, b: list) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def pad_bounds(w: Window, total: float) -> tuple[float, float]:
    return max(0.0, w.start - 0.12), min(total, w.end + 0.4)
