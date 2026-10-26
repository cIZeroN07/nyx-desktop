"""Crea <pose>_blink.png: el sprite original con los ojos cerrados que dibujó ChatGPT.

ChatGPT mueve un poco el pelo al redibujar, así que no se puede cambiar la imagen entera
(el parpadeo daría saltos). En su lugar:
  1. Se busca dónde encaja mejor la cara de la versión con ojos cerrados sobre la original.
  2. Se pega SOLO la franja de los ojos, con los bordes difuminados.

Antes hay que recortar la hoja de parpadeo con cut_sprites.py en assets/sprites/<pose>_blink_src.png.
Uso:  .venv\\Scripts\\python.exe tools\\make_blink.py [pose ...]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SPRITES = ROOT / "assets" / "sprites"


def gray(img):
    return np.asarray(img.convert("L"), dtype=float)


def find_eyes(rgba):
    """Caja (x0, y0, x1, y1) que contiene los dos ojos azules brillantes."""
    arr = np.asarray(rgba)
    h, w = arr.shape[:2]
    y_lo, y_hi, x_lo, x_hi = int(h * 0.04), int(h * 0.16), int(w * 0.2), int(w * 0.85)
    sub = arr[y_lo:y_hi, x_lo:x_hi].astype(int)
    r, g, b, a = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
    eye = (b > 150) & (b > r + 15) & (g > 110) & (a > 200)
    labels, n = ndimage.label(ndimage.binary_dilation(eye))
    if n == 0:
        return None
    sizes = ndimage.sum(eye, labels, range(1, n + 1))
    centers = ndimage.center_of_mass(eye, labels, range(1, n + 1))
    first = int(np.argmax(sizes))
    keep = [first + 1]
    # El otro ojo: el trozo azul más grande que esté a la misma altura que el primero
    for i in np.argsort(-sizes):
        if i != first and sizes[i] >= 6 and abs(centers[i][0] - centers[first][0]) < 14:
            keep.append(i + 1)
            break
    ys, xs = np.nonzero(np.isin(labels, keep))
    return (xs.min() + x_lo, ys.min() + y_lo, xs.max() + x_lo, ys.max() + y_lo)


def align(orig, src, box):
    """Escala y desplazamiento de `src` que mejor encajan con `orig` alrededor de los ojos."""
    x0, y0, x1, y1 = box
    m = 40
    region = (max(0, x0 - m), max(0, y0 - m), min(orig.width, x1 + m), min(orig.height, y1 + m))
    target = gray(orig.crop(region))
    best = (None, 1e18)
    for s in np.linspace(0.94, 1.06, 13):
        size = (int(orig.width * s), int(orig.height * s))
        scaled = src.resize(size, Image.LANCZOS)
        g = gray(scaled)
        for dy in range(-14, 15, 2):
            for dx in range(-14, 15, 2):
                l, t = region[0] + dx, region[1] + dy
                if l < 0 or t < 0 or l + target.shape[1] > g.shape[1] or t + target.shape[0] > g.shape[0]:
                    continue
                patch = g[t:t + target.shape[0], l:l + target.shape[1]]
                err = np.mean((patch - target) ** 2)
                if err < best[1]:
                    best = ((s, dx, dy), err)
    # Afinar de píxel en píxel alrededor del mejor
    (s, bdx, bdy), _ = best
    scaled = src.resize((int(orig.width * s), int(orig.height * s)), Image.LANCZOS)
    g = gray(scaled)
    for dy in range(bdy - 2, bdy + 3):
        for dx in range(bdx - 2, bdx + 3):
            l, t = region[0] + dx, region[1] + dy
            if l < 0 or t < 0 or l + target.shape[1] > g.shape[1] or t + target.shape[0] > g.shape[0]:
                continue
            err = np.mean((g[t:t + target.shape[0], l:l + target.shape[1]] - target) ** 2)
            if err < best[1]:
                best = ((s, dx, dy), err)
    return best[0], scaled


def blink(pose):
    orig = Image.open(SPRITES / f"{pose}.png").convert("RGBA")
    src_path = SPRITES / f"{pose}_blink_src.png"
    if not src_path.exists():
        print(f"{pose}: falta {src_path.name}")
        return
    src = Image.open(src_path).convert("RGBA").resize(orig.size, Image.LANCZOS)
    box = find_eyes(orig)
    if box is None:
        print(f"{pose}: no encuentro los ojos")
        return
    (s, dx, dy), scaled = align(orig, src, box)

    # Colocar la versión de ojos cerrados encima, ya encajada
    placed = Image.new("RGBA", orig.size, (0, 0, 0, 0))
    placed.paste(scaled, (-dx, -dy))

    # Máscara: una elipse que cubre los dos ojos y los párpados, con borde difuminado
    x0, y0, x1, y1 = box
    eh = y1 - y0
    mask = Image.new("L", orig.size, 0)
    ImageDraw.Draw(mask).ellipse((x0 - 10, y0 - eh * 0.6 - 4, x1 + 10, y1 + eh * 0.5 + 4), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(4))

    result = Image.composite(placed, orig, mask)
    result.putalpha(orig.getchannel("A"))
    result.save(SPRITES / f"{pose}_blink.png")
    print(f"{pose}_blink.png  ojos {box}  encaje: escala {s:.2f}, desplazamiento ({dx}, {dy})")


if __name__ == "__main__":
    for pose in sys.argv[1:] or ["idle", "wave", "sit"]:
        blink(pose)
