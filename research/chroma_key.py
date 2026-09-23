"""Chroma key background removal for AI-generated garment layers."""

from __future__ import annotations

from enum import Enum
from io import BytesIO

import numpy as np
from PIL import Image


class KeyColor(str, Enum):
    MAGENTA = "magenta"
    GREEN = "green"


# Channel that must be LOW for a pixel to count as background, vs the two that must be HIGH.
_KEY_CHANNELS: dict[KeyColor, tuple[int, tuple[int, int]]] = {
    KeyColor.MAGENTA: (1, (0, 2)),  # G low, R+B high
    KeyColor.GREEN: (0, (1, 1)),    # R low, G high (B also low, handled by the ramp)
}


def remove_chroma_background(
    image: Image.Image,
    key: KeyColor = KeyColor.MAGENTA,
    soft_edge: tuple[float, float] = (0.12, 0.35),
    despill_strength: float = 1.0,
) -> Image.Image:
    """Cut a garment out of a flat chroma background into a real alpha channel.

    `soft_edge` is the (opaque_below, transparent_above) ramp on the key difference,
    which keeps antialiased outlines smooth instead of producing a jagged 1-bit mask.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    low_idx, high_idx = _KEY_CHANNELS[key]

    low = rgb[..., low_idx]
    high = np.minimum(rgb[..., high_idx[0]], rgb[..., high_idx[1]])

    # How strongly this pixel leans toward the key color.
    difference = high - low

    lo, hi = soft_edge
    alpha = 1.0 - np.clip((difference - lo) / (hi - lo), 0.0, 1.0)

    if despill_strength:
        # Pull the key color out of semi-transparent edge pixels so no fringe survives.
        spill = np.clip(difference, 0.0, None) * despill_strength
        rgb[..., high_idx[0]] -= spill
        if high_idx[1] != high_idx[0]:
            rgb[..., high_idx[1]] -= spill
        rgb = np.clip(rgb, 0.0, 1.0)

    rgba = np.dstack([rgb, alpha])
    return Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")


def coverage_ratio(image: Image.Image, threshold: int = 128) -> float:
    """Fraction of the canvas the cut-out garment occupies. Used as a sanity check."""
    alpha = np.asarray(image.convert("RGBA"))[..., 3]
    return float((alpha > threshold).mean())


def content_bounds(image: Image.Image, threshold: int = 128) -> tuple[int, int, int, int]:
    """Bounding box (left, top, right, bottom) of the non-transparent content."""
    alpha = np.asarray(image.convert("RGBA"))[..., 3] > threshold
    rows = np.any(alpha, axis=1)
    cols = np.any(alpha, axis=0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    return int(left), int(top), int(right), int(bottom)


if __name__ == "__main__":
    source = Image.open("flashcloset_garment_magenta.jpeg")
    cut = remove_chroma_background(source)
    cut.save("garment_chromakey.png")

    print(f"coverage: {coverage_ratio(cut):.3f}")
    print(f"bounds:   {content_bounds(cut)}")

    avatar = Image.open("flashcloset_base_avatar_v2.jpeg").convert("RGBA")
    Image.alpha_composite(avatar, cut).convert("RGB").save("overlay_chromakey.jpg", quality=92)

    # Checkerboard render so we can eyeball the cutout edges on their own.
    w, h = cut.size
    tile = 64
    board = np.indices((h, w)).sum(axis=0) // tile % 2
    backdrop = Image.fromarray((board * 40 + 200).astype(np.uint8)).convert("RGBA")
    Image.alpha_composite(backdrop, cut).convert("RGB").save("cutout_on_checker.jpg", quality=92)
    print("done")
