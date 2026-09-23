"""Recolor the extracted garment layer into demo variants.

Stand-ins so the carousel has something to swipe through; no extra AI generations.
The tint is applied as a luminance ramp so the folds and shading survive.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

VARIANTS: dict[str, tuple[int, int, int] | None] = {
    "black": None,               # the real extracted layer, untouched
    "burgundy": (150, 40, 62),
    "navy": (44, 62, 130),
    "emerald": (32, 120, 92),
}


def tint(layer: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    rgba = np.asarray(layer.convert("RGBA"), dtype=np.float32)
    rgb, alpha = rgba[..., :3], rgba[..., 3:]

    luminance = (rgb * (0.299, 0.587, 0.114)).sum(axis=2, keepdims=True) / 255.0
    # Lift the ramp so a near-black source still shows the target hue.
    ramp = 0.32 + 1.55 * luminance

    tinted = np.clip(np.array(color, dtype=np.float32) * ramp, 0, 255)
    return Image.fromarray(np.dstack([tinted, alpha]).astype(np.uint8), mode="RGBA")


def thumbnail(layer: Image.Image, size: int = 190) -> Image.Image:
    alpha = np.asarray(layer)[..., 3] > 16
    rows, cols = np.any(alpha, axis=1), np.any(alpha, axis=0)
    t, b = np.where(rows)[0][[0, -1]]
    l, r = np.where(cols)[0][[0, -1]]
    cropped = layer.crop((l, t, r, b))

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cropped.thumbnail((size - 16, size - 16), Image.LANCZOS)
    canvas.paste(
        cropped,
        ((size - cropped.width) // 2, (size - cropped.height) // 2),
        cropped,
    )
    return canvas


if __name__ == "__main__":
    source = Image.open("proto_garment.png").convert("RGBA")

    for name, color in VARIANTS.items():
        layer = source if color is None else tint(source, color)
        layer.save(f"item_{name}.png")
        thumbnail(layer).save(f"thumb_{name}.png")
        print(f"{name:10} -> item_{name}.png + thumb_{name}.png")
