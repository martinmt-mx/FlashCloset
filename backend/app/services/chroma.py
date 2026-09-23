"""Cut a subject out of a flat chroma field into a real alpha channel.

Generative models cannot emit an alpha channel — asked for transparency they
invent a checkerboard — so the pipeline asks for a flat key colour instead and
does the matting here, deterministically.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PIL import Image


class KeyColor(str, Enum):
    MAGENTA = "magenta"
    GREEN = "green"


# (channel that is LOW on the key, channels that are HIGH)
_CHANNELS: dict[KeyColor, tuple[int, tuple[int, int]]] = {
    KeyColor.MAGENTA: (1, (0, 2)),
    KeyColor.GREEN: (0, (1, 1)),
}


def remove_chroma(
    image: Image.Image,
    key: KeyColor = KeyColor.MAGENTA,
    soft_edge: tuple[float, float] = (0.12, 0.35),
    despill: float = 1.0,
) -> Image.Image:
    """`soft_edge` ramps alpha across the key difference, keeping antialiased
    outlines smooth rather than producing a jagged one-bit mask."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    low_idx, high_idx = _CHANNELS[key]

    difference = np.minimum(rgb[..., high_idx[0]], rgb[..., high_idx[1]]) - rgb[..., low_idx]

    lo, hi = soft_edge
    alpha = 1.0 - np.clip((difference - lo) / (hi - lo), 0.0, 1.0)

    if despill:
        # Pull the key colour out of edge pixels so no coloured fringe survives.
        spill = np.clip(difference, 0.0, None) * despill
        rgb[..., high_idx[0]] -= spill
        if high_idx[1] != high_idx[0]:
            rgb[..., high_idx[1]] -= spill
        rgb = np.clip(rgb, 0.0, 1.0)

    rgba = np.dstack([rgb, alpha])
    return Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")
