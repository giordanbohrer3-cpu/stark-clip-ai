"""Unidade: motor de cortes, legendas e enquadramento."""
import numpy as np

from stark_engine import captions as cap
from stark_engine.clipper import ClipAnalyzer, build_sentences, duration_bounds
from stark_engine.reframe import Plan, crop_commands, plan_layout

from .conftest import words_from

TOPIC_A = ("Você sabia que o maior erro de quem investe é não ter reserva? Muita gente aplica tudo em ações. "
           "Quando aparece uma conta precisa vender no prejuízo. A reserva protege do pânico financeiro. "
           "Guarde seis meses do custo de vida em aplicação segura. Então a lição é simples: primeiro a reserva.")
TOPIC_B = ("Por que você não termina o que começa? O problema não é preguiça. É excesso de tarefas abertas. "
           "O cérebro paga caro cada troca de contexto. Escolha uma tarefa importante por manhã. "
           "Resultado: você termina mais trabalhando menos!")
TOPIC_C = ("Qual é o segredo para dormir melhor? Não é remédio, é luz. A luz da manhã regula o relógio biológico. "
           "A tela do celular à noite atrasa o sono. Tome sol cedo e desligue telas antes de deitar. "
           "Parece simples demais, mas funciona de verdade.")
INTRO = "Fala galera sejam bem-vindos ao canal hoje tem três assuntos."
OUTRO = "Se inscreva no canal e deixa o like ativa o sininho até a próxima."


def _video():
    return words_from([(0, INTRO), (6, TOPIC_A), (45, TOPIC_B), (78, TOPIC_C), (112, OUTRO)])


def test_sentences_split_on_punctuation():
    s = build_sentences(words_from([(0, "Olá mundo. Tudo bem? Sim!")]))
    assert [x.text for x in s] == ["Olá mundo.", "Tudo bem?", "Sim!"]


def test_duration_bounds_adaptive():
    lo, hi, ideal = duration_bounds(600)
    assert 10 <= lo < ideal < hi <= 90
    assert duration_bounds(3600)[2] == 55
    assert duration_bounds(300, "long")[:2] == (61.0, 180.0)
    lo, hi, _ = duration_bounds(20)
    assert hi <= 18


def test_select_three_distinct_non_overlapping():
    an = ClipAnalyzer(_video(), 120, np.zeros(240), [])
    chosen, note = an.select(3, 30)
    assert 1 <= len(chosen) <= 3
    for a in chosen:
        assert an.lo <= a.duration <= an.hi
        for b in chosen:
            if a is not b:
                assert not (a.start < b.end and b.start < a.end)
    assert all(0 <= c.score <= 100 for c in chosen)
    d = an.describe(chosen[0])
    assert d["title"] and d["justification"]


def test_cta_and_intro_penalized():
    an = ClipAnalyzer(_video(), 120, None, [])
    outro_idx = len(an.sents) - 1
    w_outro = an.window(max(0, outro_idx - 1), outro_idx)
    assert w_outro.features["cta_pen"] == 1.0
    best, _ = an.select(3, 0)
    assert all(b.features["cta_pen"] == 0 for b in best)


def test_no_artificial_cuts_when_content_short():
    an = ClipAnalyzer(words_from([(0, "Oi tudo bem.")]), 3, None, [])
    chosen, note = an.select(3, 35)
    assert len(chosen) < 3 and note


def test_expand_long_version():
    an = ClipAnalyzer(_video(), 120, None, [], mode="long")
    w = an.expand(10, 30)
    assert w.duration >= 61 or w.i == 0


def test_keep_segments_and_remap():
    words = [[0.0, 0.5, "a", 1], [0.6, 1.0, "b", 1], [3.0, 3.5, "c", 1]]
    segs = cap.keep_segments(words, 0, 4, remove_pauses=True)
    assert len(segs) == 2
    cw = cap.clip_words(words, segs)
    assert cw[2][0] < 2.0  # pausa de 2s removida
    assert cap.keep_segments(words, 0, 4, remove_pauses=False) == [(0, 4)]


def test_ass_karaoke_and_srt():
    words = [[0.0, 0.4, "olá", 1], [0.4, 0.8, "mundo", 1], [0.8, 1.2, "lindo.", 1], [1.5, 2.0, "fim", 1]]
    chunks = cap.build_chunks(words, per_line=3)
    ass = cap.to_ass(chunks, {"highlight": "#22D3EE"})
    assert ass.count("Dialogue:") == 4
    assert "\\c&H00EED322" in ass and "PlayResY: 1920" in ass
    srt = cap.to_srt(chunks)
    assert "00:00:00,000 --> 00:00:01,200" in srt
    assert cap.ass_color("bad") == "&H00FFFFFF"


def test_reframe_layouts():
    moving = [(t / 3, [(0.3 + 0.01 * t, 0.4, 0.1, 0.18)]) for t in range(30)]
    p = plan_layout(moving, 1920, 1080)
    assert p.layout == "face" and p.crop_w == 606 and p.crop_h == 1080
    assert all(p.crop_w / 2 <= x <= 1920 - p.crop_w / 2 for _, x in p.keys)
    two = [(t / 3, [(0.25, 0.4, 0.1, 0.2), (0.75, 0.4, 0.1, 0.2)]) for t in range(20)]
    assert plan_layout(two, 1920, 1080).layout == "split"
    assert plan_layout([(0, [])] * 10, 1920, 1080).layout == "center"
    assert plan_layout([], 1080, 1920).layout == "fit"
    cmds = crop_commands(p, lambda t: t, 10)
    xs = [int(line.split()[-1].rstrip(";")) for line in cmds.strip().splitlines()]
    assert xs and all(x % 2 == 0 and 0 <= x <= 1920 - 606 for x in xs)
    assert crop_commands(Plan("split", 1920, 1080), lambda t: t, 5) == ""
