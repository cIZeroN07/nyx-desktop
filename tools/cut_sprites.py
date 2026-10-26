"""Quita el fondo blanco de la hoja de personaje y la separa en una imagen por pose.

Uso:  .venv\\Scripts\\python.exe tools\\cut_sprites.py
Lee assets/source/nyx_sheet.png y escribe assets/sprites/<pose>.png
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "source" / "nyx_sheet.png"
OUT = ROOT / "assets" / "sprites"
POSES = ["idle", "wave", "sleep", "sit"]   # orden de izquierda a derecha

WHITE = 228          # a partir de aquí un píxel cuenta como "casi blanco"
BIG_HOLE = 600       # huecos blancos encerrados más grandes que esto también son fondo
SMALL_HOLE = 6       # huecos más pequeños que esto se dejan (brillos de ojos, etc.)
MIN_GAP = 3          # columnas vacías seguidas para separar dos poses
PAD = 6              # margen transparente alrededor de cada pose


def remove_background(rgb: np.ndarray) -> np.ndarray:
    lo = rgb.min(axis=2).astype(int)
    sat = rgb.max(axis=2).astype(int) - lo
    # Casi blanco y sin color (así el rosa claro del pelo no cuenta como fondo)
    whiteish = (lo >= WHITE) | ((lo >= 212) & (sat <= 14))
    labels, n = ndimage.label(whiteish)

    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    idx = np.arange(n + 1)
    sizes = ndimage.sum(whiteish, labels, index=idx)
    mean_lo = ndimage.mean(lo, labels, index=idx)
    mean_sat = ndimage.mean(sat, labels, index=idx)
    # Huecos encerrados entre mechones: pequeños, pero muy blancos y grises
    holes = (sizes >= SMALL_HOLE) & (mean_lo >= 236) & (mean_sat <= 10)
    bg_ids = set(border.tolist()) | set(np.nonzero(sizes > BIG_HOLE)[0].tolist()) | set(np.nonzero(holes)[0].tolist())
    bg_ids.discard(0)
    background = np.isin(labels, list(bg_ids))

    alpha = np.where(background, 0.0, 1.0)

    # Borde suave: los píxeles pegados al fondo se vuelven semitransparentes según lo blancos que sean
    edge = ndimage.binary_dilation(background, iterations=2) & ~background
    whiteness = (rgb.min(axis=2).astype(float) - 150) / (255 - 150)
    alpha[edge] = np.clip(1 - whiteness[edge], 0, 1)

    # Quitar el "halo" blanco: deshacer la mezcla con blanco en el borde
    a = np.clip(alpha, 1e-3, 1)[..., None]
    color = np.clip((rgb.astype(float) - 255 * (1 - a)) / a, 0, 255)

    rgba = np.dstack([color, alpha * 255]).astype(np.uint8)
    return rgba


def split_poses(rgba: np.ndarray):
    filled = (rgba[..., 3] > 20).sum(axis=0) > 0
    spans, start, gap = [], None, 0
    for x, f in enumerate(filled):
        if f:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= MIN_GAP:
                spans.append((start, x - gap + 1))
                start, gap = None, 0
    if start is not None:
        spans.append((start, len(filled)))
    return spans


def split_figures(rgba: np.ndarray, count: int):
    """Separa las poses como figuras sueltas (para cuando el pelo de una invade la columna de otra).
    Devuelve una imagen por figura, de izquierda a derecha, con solo los píxeles de esa figura."""
    solid = rgba[..., 3] > 20
    # Unir los trocitos sueltos (purpurina del pelo, etc.) a su figura
    labels, n = ndimage.label(ndimage.binary_dilation(solid, iterations=4))
    sizes = ndimage.sum(solid, labels, range(1, n + 1))
    biggest = (np.argsort(-sizes)[:count] + 1).tolist()
    centers = ndimage.center_of_mass(solid, labels, biggest)
    order = [b for _, b in sorted(zip([c[1] for c in centers], biggest))]
    out = []
    for lab in order:
        mask = (labels == lab) & solid
        part = rgba.copy()
        part[..., 3] = np.where(mask, part[..., 3], 0)
        ys, xs = np.nonzero(mask)
        out.append(part[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    return out


def crop(rgba: np.ndarray, x0: int, x1: int) -> Image.Image:
    part = rgba[:, x0:x1]
    rows = np.nonzero((part[..., 3] > 20).any(axis=1))[0]
    y0, y1 = rows[0], rows[-1] + 1
    part = part[y0:y1]
    img = Image.fromarray(part, "RGBA")
    canvas = Image.new("RGBA", (img.width + 2 * PAD, img.height + 2 * PAD), (0, 0, 0, 0))
    canvas.paste(img, (PAD, PAD))
    return canvas


def main():
    """Sin argumentos recorta la hoja principal. Con argumentos:
    cut_sprites.py <imagen> <fila_y0> <fila_y1> <nombre1> <nombre2> ...
    (fila_y0/fila_y1 eligen una fila de la hoja, por si trae varias)."""
    src, names, rows = SRC, POSES, None
    if len(sys.argv) > 4:
        src = Path(sys.argv[1])
        rows = (int(sys.argv[2]), int(sys.argv[3]))
        names = sys.argv[4:]

    rgb = np.array(Image.open(src).convert("RGB"))
    if rows:
        rgb = rgb[rows[0]:rows[1]]
    rgba = remove_background(rgb)
    spans = split_poses(rgba)
    print("poses encontradas:", spans)
    OUT.mkdir(parents=True, exist_ok=True)
    if len(spans) == len(names):
        for name, (x0, x1) in zip(names, spans):
            img = crop(rgba, x0, x1)
            img.save(OUT / f"{name}.png")
            print(f"{name}.png  {img.size}")
        return

    # Las columnas se solapan: separar por figuras
    print("Las poses se solapan; las separo por figuras.")
    for name, part in zip(names, split_figures(rgba, len(names))):
        img = Image.fromarray(part, "RGBA")
        canvas = Image.new("RGBA", (img.width + 2 * PAD, img.height + 2 * PAD), (0, 0, 0, 0))
        canvas.paste(img, (PAD, PAD))
        canvas.save(OUT / f"{name}.png")
        print(f"{name}.png  {canvas.size}")


if __name__ == "__main__":
    main()
