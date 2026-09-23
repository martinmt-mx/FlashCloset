"""Compare the two ways of producing a garment layer, on the same garment.

  A  one generation  — the model draws the garment alone on a magenta field.
  B  two generations — the model dresses the avatar, then repaints everything
                       that is not the garment magenta.

Both are cut out with the same chroma key, then placed on the avatar with the
best uniform scale+offset available, which is all the app's manual fit control
can express. Whatever error survives that fit is error the user cannot correct.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research"))

from chroma_key import KeyColor, remove_chroma_background  # noqa: E402


@dataclass(frozen=True)
class Cutout:
    layer: Image.Image
    box: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]

    @property
    def aspect(self) -> float:
        return self.width / self.height


def cut_out(path: Path, min_area_ratio: float = 0.004) -> Cutout:
    layer = remove_chroma_background(Image.open(path), KeyColor.MAGENTA)
    solid = np.asarray(layer)[..., 3] > 128

    # Keep only the garment blob, dropping JPEG speckle and any leaked border.
    labels, count = ndimage.label(ndimage.binary_opening(solid, iterations=2))
    if count:
        sizes = ndimage.sum_labels(solid, labels, index=range(1, count + 1))
        solid = labels == int(np.argmax(sizes)) + 1

    alpha = np.asarray(layer)[..., 3] * solid
    layer.putalpha(Image.fromarray(alpha.astype(np.uint8)))

    ys, xs = np.where(solid)
    return Cutout(layer, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))


def place(cut: Cutout, target_box: tuple[int, int, int, int], canvas: tuple[int, int],
          fit: str) -> Image.Image:
    """Uniform scale + translate, matching either height or width of the target box."""
    tx0, ty0, tx1, ty1 = target_box
    scale = (ty1 - ty0) / cut.height if fit == "height" else (tx1 - tx0) / cut.width

    cropped = cut.layer.crop(cut.box)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    scaled = cropped.resize(size, Image.LANCZOS)

    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    cx, cy = (tx0 + tx1) // 2, (ty0 + ty1) // 2
    out.paste(scaled, (cx - size[0] // 2, cy - size[1] // 2), scaled)
    return out


def iou(a: Image.Image, b: Image.Image) -> float:
    m1 = np.asarray(a)[..., 3] > 128
    m2 = np.asarray(b)[..., 3] > 128
    union = (m1 | m2).sum()
    return float((m1 & m2).sum() / union) if union else 0.0


def main() -> None:
    avatar = Image.open(ROOT / "assets/avatar/base_v3.jpeg").convert("RGBA")
    canvas = avatar.size

    two_pass = cut_out(ROOT / "assets/mattes/camisole_v3.jpeg")
    one_pass = cut_out(ROOT / "assets/isolated/camisole_v3.jpeg")

    # The two-pass layer is already registered to the avatar, so it is the reference.
    scale = canvas[0] / two_pass.layer.width
    reference = two_pass.layer.resize(canvas, Image.LANCZOS)
    ref_box = tuple(round(v * scale) for v in two_pass.box)

    print(f"canvas {canvas}")
    print(f"B (2 pasadas)  bbox {ref_box}  {round((ref_box[2]-ref_box[0]))}x"
          f"{round((ref_box[3]-ref_box[1]))}  aspect {two_pass.aspect:.3f}")
    print(f"A (1 pasada)   {one_pass.width}x{one_pass.height}  aspect {one_pass.aspect:.3f}")
    print(f"desajuste de proporcion: {abs(one_pass.aspect/two_pass.aspect - 1) * 100:.1f}%")
    print()

    out_dir = ROOT / "output" / "comparacion_v3"
    out_dir.mkdir(parents=True, exist_ok=True)

    panels = [("B_dos_pasadas", reference)]
    for fit in ("height", "width"):
        placed = place(one_pass, ref_box, canvas, fit)
        print(f"A ajustada por {fit:6s} -> IoU contra B = {iou(placed, reference):.3f}")
        panels.append((f"A_una_pasada_{fit}", placed))

    for name, layer in panels:
        Image.alpha_composite(avatar, layer).convert("RGB").save(
            out_dir / f"{name}.jpg", quality=92
        )

    strip = [Image.open(out_dir / f"{n}.jpg") for n, _ in panels]
    sheet = Image.new("RGB", (strip[0].width * len(strip), strip[0].height), "white")
    for i, im in enumerate(strip):
        sheet.paste(im, (i * im.width, 0))
    sheet.thumbnail((1600, 1600))
    sheet.save(ROOT / "output" / "comparacion_v3.jpg", quality=90)
    print(f"\n{[n for n, _ in panels]}")


if __name__ == "__main__":
    main()
