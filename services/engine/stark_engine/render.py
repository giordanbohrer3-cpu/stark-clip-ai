"""Render final/prévia: corte (com jump cuts), reframe 9:16, cor, legendas ASS, logo e loudness -14 LUFS."""
from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import captions as cap
from .config import ASSETS_DIR
from .media import grab_frame, run_ffmpeg, video_encoder
from .reframe import crop_commands, initial_x, plan_layout, sample_faces

log = logging.getLogger(__name__)


@dataclass
class RenderSpec:
    start: float
    end: float
    layout: str = "auto"
    remove_pauses: bool = False
    denoise: bool = False
    logo_path: Path | None = None
    logo_opacity: float = 0.9
    logo_scale: float = 0.14
    style: dict = field(default_factory=dict)
    color: dict = field(default_factory=lambda: {"contrast": 1.03, "saturation": 1.08, "brightness": 0.0})


def _link_fonts(job_dir: Path) -> None:
    dst = job_dir / "fonts"
    if dst.exists():
        return
    try:
        os.symlink(ASSETS_DIR / "fonts", dst, target_is_directory=True)
    except OSError:
        shutil.copytree(ASSETS_DIR / "fonts", dst)


def render_clip(src: Path, info: dict, words: list, spec: RenderSpec, out_dir: Path, preview: bool = False,
                on_progress: Callable[[float, str], None] | None = None,
                should_cancel: Callable[[], bool] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    _link_fonts(out_dir)
    prog = on_progress or (lambda p, s: None)
    W, H = (540, 960) if preview else (1080, 1920)

    segs = cap.keep_segments(words, spec.start, spec.end, spec.remove_pauses)
    out_dur = sum(e - s for s, e in segs)
    cwords = cap.clip_words(words, segs)

    prog(0.02, "enquadramento")
    samples = sample_faces(src, spec.start, spec.end, fps=2.0 if preview else 3.0)
    plan = plan_layout(samples, info["width"], info["height"], spec.layout)

    # legendas (posição central no layout dividido)
    chunks = cap.build_chunks(cwords, per_line=int(spec.style.get("words_per_line", 3)))
    pos = {"split": 0.5, "stream": 0.79}.get(plan.layout)
    title_y = 600 if plan.layout == "stream" else None
    dur_hint = max(out_dur, 0.1)
    style = {**spec.style}
    if style.get("title") and not chunks:  # sem fala: título fica o clipe todo
        chunks = [[[0.0, dur_hint, " "]]]
    (out_dir / "clip.ass").write_text(cap.to_ass(chunks, style, 1080, 1920, pos, title_y), encoding="utf-8")
    (out_dir / "clip.srt").write_text(cap.to_srt(chunks), encoding="utf-8")

    ss = segs[0][0]
    fc: list[str] = []
    for k, (s, e) in enumerate(segs):
        fc.append(f"[0:v]trim=start={s - ss:.3f}:end={e - ss:.3f},setpts=PTS-STARTPTS[v{k}]")
        if info.get("has_audio"):
            fc.append(f"[0:a]atrim=start={s - ss:.3f}:end={e - ss:.3f},asetpts=PTS-STARTPTS[a{k}]")
    n = len(segs)
    if info.get("has_audio"):
        fc.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    else:
        fc.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]")

    if plan.layout == "split":
        (x1, y1, w1, h1), (x2, y2, w2, h2) = plan.split
        fc.append(f"[vc]split=2[s0][s1];[s0]crop={w1}:{h1}:{x1}:{y1},scale={W}:{H // 2}:flags=lanczos[top];"
                  f"[s1]crop={w2}:{h2}:{x2}:{y2},scale={W}:{H // 2}:flags=lanczos[bot];[top][bot]vstack[vr]")
    elif plan.layout == "stream":
        (cx, cy, cw, ch), (gx, gy, gw, gh) = plan.split
        top_h = int(H * 600 / 1920) // 2 * 2
        fc.append(f"[vc]split=2[s0][s1];[s0]crop={cw}:{ch}:{cx}:{cy},scale={W}:{top_h}:flags=lanczos[top];"
                  f"[s1]crop={gw}:{gh}:{gx}:{gy},scale={W}:{H - top_h}:flags=lanczos[bot];[top][bot]vstack[vr]")
    elif plan.layout == "fit":
        fc.append(f"[vc]split=2[s0][s1];[s0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"boxblur=luma_radius=30:luma_power=2[bg];[s1]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2[vr]")
    else:
        cmds = crop_commands(plan, lambda t: cap.remap(t, segs), out_dur)
        send = ""
        if cmds.count("\n") > 1:
            (out_dir / "cam.txt").write_text(cmds)
            send = "sendcmd=f=cam.txt,"
        fc.append(f"[vc]{send}crop@cam=w={plan.crop_w}:h={plan.crop_h}:x={initial_x(plan)}:y=0,"
                  f"scale={W}:{H}:flags=lanczos[vr]")

    c = spec.color
    fc.append(f"[vr]setsar=1,eq=contrast={c.get('contrast', 1)}:saturation={c.get('saturation', 1)}:"
              f"brightness={c.get('brightness', 0)},subtitles=clip.ass:fontsdir=fonts[vs]")
    inputs = ["-ss", f"{ss:.3f}", "-t", f"{segs[-1][1] - ss + 0.1:.3f}", "-i", str(src)]
    vout = "[vo]"
    if spec.logo_path and spec.logo_path.exists():
        inputs += ["-i", str(spec.logo_path)]
        fc.append(f"[1:v]scale={int(W * spec.logo_scale)}:-1,format=rgba,colorchannelmixer=aa={spec.logo_opacity}[lg];"
                  f"[vs][lg]overlay=W-w-{int(W * 0.045)}:{int(H * 0.035)}[vo]")
    else:
        fc.append("[vs]null[vo]")
    if info.get("has_audio"):
        af = ("afftdn=nf=-25," if spec.denoise else "") + "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
        fc.append(f"[ac]{af}[ao]")
        amap = ["-map", "[ao]"]
    else:
        silent_idx = inputs.count("-i")
        inputs += ["-f", "lavfi", "-t", f"{out_dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        amap = ["-map", f"{silent_idx}:a"]

    enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"] if preview else video_encoder()
    name = "preview.mp4" if preview else "clip.mp4"
    args = [*inputs, "-filter_complex", ";".join(fc), "-map", vout, *amap, *enc, "-pix_fmt", "yuv420p",
            "-r", "30", "-c:a", "aac", "-b:a", "96k" if preview else "160k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", name]
    (out_dir / "ffmpeg_args.json").write_text(json.dumps(args, ensure_ascii=False, indent=1))
    prog(0.08, "renderizando")
    run_ffmpeg(args, out_dur, lambda f: prog(0.08 + 0.88 * f, "renderizando"), should_cancel, cwd=out_dir)

    result = {"video": out_dir / name, "srt": out_dir / "clip.srt", "ass": out_dir / "clip.ass",
              "duration": round(out_dur, 2), "layout": plan.layout, "plan": plan.as_dict()}
    if not preview:
        prog(0.97, "capa")
        result["cover"] = grab_frame(out_dir / name, min(out_dur * 0.15, 3.0), out_dir / "cover.jpg")
    prog(1.0, "pronto")
    return result
