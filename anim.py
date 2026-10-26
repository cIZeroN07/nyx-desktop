"""Apariencias animadas: tiras de fotogramas (una imagen por animación, fotogramas en fila).

skin.json describe cada animación: archivo, ancho de fotograma, fotogramas por segundo, si se repite
y si es una capa encima de otra (la boca al hablar).
"""
import io

import numpy as np
from PIL import Image
from PySide6.QtGui import QPainter, QPixmap


def _pixmap(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    pix = QPixmap()
    pix.loadFromData(buf.getvalue(), "PNG")
    return pix


class SpriteAnimations:
    def __init__(self, skin_dir, meta, height):
        self.meta = meta
        self.specs = meta.get("anims", {})
        strips = {}
        for name, spec in self.specs.items():
            img = Image.open(skin_dir / spec["file"]).convert("RGBA")
            w = int(spec["w"])
            strips[name] = [img.crop((i * w, 0, (i + 1) * w, img.height)) for i in range(img.width // w)]

        # Todas las animaciones del mismo ancho se recortan igual, para que encajen al cambiar de una a otra
        boxes = {}
        for name, frames in strips.items():
            if self.specs[name].get("overlay"):
                continue
            w = frames[0].width
            alpha = np.any([np.asarray(f)[..., 3] > 20 for f in frames], axis=0)
            ys, xs = np.nonzero(alpha)
            box = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]
            if w in boxes:
                b = boxes[w]
                box = [min(b[0], box[0]), min(b[1], box[1]), max(b[2], box[2]), max(b[3], box[3])]
            boxes[w] = box

        # La altura de referencia es la de las animaciones de pie (las más estrechas)
        stand_w = min(boxes)
        scale = height / (boxes[stand_w][3] - boxes[stand_w][1])
        self.frames = {}
        for name, frames in strips.items():
            box = boxes.get(frames[0].width, boxes[stand_w])
            out = []
            for f in frames:
                c = f.crop(tuple(int(v) for v in box))
                c = c.resize((max(1, int(c.width * scale)), max(1, int(c.height * scale))), Image.LANCZOS)
                out.append(_pixmap(c))
            self.frames[name] = out

    def has(self, name):
        return name in self.frames

    def first(self, name):
        return self.frames[name][0]

    def fps(self, name):
        return float(self.specs[name].get("fps", 10))

    def loops(self, name):
        return bool(self.specs[name].get("loop", False))

    def pose_anim(self, pose):
        return self.meta.get("poses", {}).get(pose)

    def with_overlay(self, base, overlay_name, i):
        """El fotograma `base` con la capa `overlay_name` (p. ej. la boca) encima."""
        frames = self.frames.get(overlay_name)
        if not frames or frames[0].size() != base.size():
            return base
        out = QPixmap(base)
        p = QPainter(out)
        p.drawPixmap(0, 0, frames[i % len(frames)])
        p.end()
        return out
