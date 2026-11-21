"""Legendas: blocos curtos, SRT e ASS com destaque animado da palavra ativa (estilo karaokê)."""
from __future__ import annotations

import re
from itertools import pairwise


def keep_segments(words: list, start: float, end: float, remove_pauses: bool,
                  min_gap: float = 0.6, pad: float = 0.15) -> list[tuple[float, float]]:
    """Trechos mantidos do intervalo. Com remove_pauses, corta silêncios > min_gap (jump cut)."""
    if not remove_pauses:
        return [(start, end)]
    ws = [w for w in words if w[1] > start and w[0] < end]
    segs, cur = [], start
    for a, b in pairwise(ws):
        if b[0] - a[1] > min_gap:
            segs.append((cur, a[1] + pad))
            cur = b[0] - pad
    segs.append((cur, end))
    return [(round(s, 3), round(e, 3)) for s, e in segs if e - s > 0.05]


def remap(t: float, segs: list[tuple[float, float]]) -> float:
    """Tempo da fonte -> tempo do corte final (considera trechos removidos)."""
    off = 0.0
    for s, e in segs:
        if t < s:
            return off
        if t <= e:
            return off + (t - s)
        off += e - s
    return off


def clip_words(words: list, segs: list[tuple[float, float]]) -> list:
    out = []
    for w in words:
        if any(w[0] >= s - 0.05 and w[1] <= e + 0.05 for s, e in segs):
            a, b = remap(w[0], segs), remap(w[1], segs)
            if b > a:
                out.append([round(a, 3), round(b, 3), w[2]])
    return out


def build_chunks(words: list, per_line: int = 3, max_chars: int = 22, max_gap: float = 0.6) -> list[list]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= per_line or w[0] - cur[-1][1] > max_gap
                    or len(" ".join(x[2] for x in [*cur, w])) > max_chars or re.search(r"[.!?…]$", cur[-1][2])):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def _srt_time(t: float) -> str:
    ms = round(max(0, t) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(t: float) -> str:
    cs = round(max(0, t) * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hexcolor: str, alpha: int = 0) -> str:
    h = hexcolor.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        h = "FFFFFF"
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _esc(t: str) -> str:
    return t.replace("\\", "/").replace("{", "(").replace("}", ")")


def to_srt(chunks: list[list]) -> str:
    out = []
    for n, ch in enumerate(chunks, 1):
        out.append(f"{n}\n{_srt_time(ch[0][0])} --> {_srt_time(ch[-1][1])}\n{' '.join(w[2] for w in ch)}\n")
    return "\n".join(out)


def to_ass(chunks: list[list], style: dict, width: int = 1080, height: int = 1920, position: float | None = None) -> str:
    size = int(style.get("size", 84))
    pos = position if position is not None else float(style.get("position", 0.68))
    margin_v = max(40, int((1 - pos) * height - size / 2))
    upper = bool(style.get("uppercase", True))
    hl = ass_color(style.get("highlight", "#22D3EE"))
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{style.get('font', 'Montserrat ExtraBold')},{size},{ass_color(style.get('primary', '#FFFFFF'))},"
        f"{hl},{ass_color(style.get('outline', '#000000'))},&H96000000,-1,0,0,0,100,100,0,0,1,"
        f"{int(style.get('outline_w', 7))},3,2,130,130,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for c, ch in enumerate(chunks):
        nxt = chunks[c + 1][0][0] if c + 1 < len(chunks) else ch[-1][1] + 0.6
        chunk_end = min(nxt, ch[-1][1] + 0.35)
        tokens = [_esc(w[2].upper() if upper else w[2]) for w in ch]
        for k, w in enumerate(ch):
            s = w[0]
            e = ch[k + 1][0] if k + 1 < len(ch) else chunk_end
            if e <= s:
                continue
            parts = [
                f"{{\\c{hl}\\fscx112\\fscy112}}{t}{{\\r}}" if idx == k else t for idx, t in enumerate(tokens)
            ]
            fx = "{\\fad(70,0)}" if k == 0 else ""
            lines.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Default,,0,0,0,,{fx}{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"
