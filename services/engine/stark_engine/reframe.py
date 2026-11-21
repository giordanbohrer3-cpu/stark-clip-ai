"""Enquadramento 9:16: detecção de rosto (OpenCV Haar, sem download), escolha de layout e câmera suave."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)
OUT_AR = 9 / 16


@dataclass
class Plan:
    layout: str  # face|center|split|fit
    src_w: int
    src_h: int
    crop_w: int = 0
    crop_h: int = 0
    keys: list[tuple[float, float]] = field(default_factory=list)  # (t_fonte, x_centro_px)
    split: list[tuple[int, int, int, int]] = field(default_factory=list)  # [(x, y, w, h) topo, base]
    face_ratio: float = 0.0

    def as_dict(self) -> dict:
        return {"layout": self.layout, "crop": [self.crop_w, self.crop_h], "face_ratio": round(self.face_ratio, 2),
                "keys": len(self.keys)}


def sample_faces(path: Path, start: float, end: float, fps: float = 3.0, det_w: int = 480) -> list:
    """[(t, [(cx, cy, w, h) normalizados])]."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(src_fps / fps)))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    front = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    out, n = [], 0
    while cap.grab():
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end:
            break
        if n % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                h, w = frame.shape[:2]
                sh = int(h * det_w / w)
                gray = cv2.equalizeHist(cv2.cvtColor(cv2.resize(frame, (det_w, sh)), cv2.COLOR_BGR2GRAY))
                mn = max(20, int(det_w * 0.05))
                faces = front.detectMultiScale(gray, 1.1, 6, minSize=(mn, mn))
                if len(faces) == 0:
                    faces = prof.detectMultiScale(gray, 1.1, 6, minSize=(mn, mn))
                out.append((t, [((x + fw / 2) / det_w, (y + fh / 2) / sh, fw / det_w, fh / sh) for x, y, fw, fh in faces]))
        n += 1
    cap.release()
    return out


def _even(v: float) -> int:
    return int(v) // 2 * 2


def plan_layout(samples: list, src_w: int, src_h: int, layout: str = "auto") -> Plan:
    if src_w / max(1, src_h) <= OUT_AR * 1.08 or layout == "fit":
        return Plan("fit", src_w, src_h)
    crop_h, crop_w = _even(src_h), _even(src_h * OUT_AR)
    with_face = [s for s in samples if s[1]]
    ratio = len(with_face) / len(samples) if samples else 0.0

    # dois participantes estáveis -> tela dividida
    pairs = []
    for _, fs in samples:
        if len(fs) >= 2:
            fs = sorted(fs, key=lambda f: -f[2] * f[3])[:2]
            a, b = sorted(fs, key=lambda f: f[0])
            if b[0] - a[0] > (crop_w / src_w) * 0.8:
                pairs.append((a, b))
    if layout == "split" or (layout == "auto" and samples and len(pairs) / len(samples) >= 0.5):
        if pairs:
            regions = []
            for side in (0, 1):
                cx = float(np.median([p[side][0] for p in pairs])) * src_w
                cy = float(np.median([p[side][1] for p in pairs])) * src_h
                fh = float(np.median([p[side][3] for p in pairs])) * src_h
                h = _even(min(src_h, max(src_h * 0.5, fh * 3.2)))
                w = _even(min(src_w, h * 1.125))  # metade 1080x960
                x = int(min(max(0, cx - w / 2), src_w - w))
                y = int(min(max(0, cy - h * 0.42), src_h - h))
                regions.append((x - x % 2, y - y % 2, w, h))
            return Plan("split", src_w, src_h, crop_w, crop_h, split=regions, face_ratio=ratio)
        layout = "auto"

    if layout == "center" or ratio < 0.2:
        return Plan("center", src_w, src_h, crop_w, crop_h, keys=[(0.0, src_w / 2)], face_ratio=ratio)

    # rastreia sujeito principal (maior rosto, depois o mais próximo do anterior)
    targets: list[float | None] = []
    prev = None
    for _, fs in samples:
        if fs:
            f = max(fs, key=lambda f: f[2] * f[3]) if prev is None else min(fs, key=lambda f: abs(f[0] - prev) - f[2] * 0.5)
            prev = f[0]
            targets.append(f[0] * src_w)
        else:
            targets.append(None)
    first = next((x for x in targets if x is not None), src_w / 2)
    filled, last = [], first
    for x in targets:
        last = x if x is not None else last
        filled.append(last)
    arr = np.array(filled)
    if arr.size >= 5:  # mediana móvel remove falsos positivos
        pad = np.pad(arr, 2, mode="edge")
        arr = np.array([np.median(pad[k:k + 5]) for k in range(arr.size)])
    half, dz = crop_w / 2, 0.06 * src_w
    cam, keys = float(arr[0]), []
    for (t, _), x in zip(samples, arr, strict=False):
        if abs(x - cam) > dz:  # zona morta: câmera só anda se sujeito sair do centro
            cam += (x - cam) * 0.35
        keys.append((t, float(min(max(cam, half), src_w - half))))
    return Plan("face", src_w, src_h, crop_w, crop_h, keys=keys, face_ratio=ratio)


def crop_commands(plan: Plan, to_out, out_duration: float, fps: int = 30) -> str:
    """Arquivo sendcmd com x do crop por frame (interpolado). to_out: tempo fonte -> tempo saída."""
    if plan.layout not in ("face", "center") or not plan.keys:
        return ""
    ts = np.array([to_out(t) for t, _ in plan.keys])
    xs = np.array([x for _, x in plan.keys])
    order = np.argsort(ts, kind="stable")
    ts, xs = ts[order], xs[order]
    lines, last = [], None
    for k in range(int(out_duration * fps) + 1):
        t = k / fps
        x = _even(float(np.interp(t, ts, xs)) - plan.crop_w / 2)
        x = max(0, min(x, plan.src_w - plan.crop_w))
        if x != last:
            lines.append(f"{t:.3f} crop@cam x {x};")
            last = x
    return "\n".join(lines) + "\n"


def initial_x(plan: Plan) -> int:
    x = plan.keys[0][1] if plan.keys else plan.src_w / 2
    return max(0, min(_even(x - plan.crop_w / 2), plan.src_w - plan.crop_w))
