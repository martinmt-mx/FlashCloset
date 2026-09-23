"""Extract a garment layer from a dressed avatar using the avatar's known palette.

The model re-renders the whole character when it edits in place, so a pixel diff is
useless. But the avatar is a fixed asset drawn in flat cel-shaded colors, so its palette
can be profiled once and stored. Anything in the dressed render that is far from every
palette entry is garment.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def profile_palette(avatar: Image.Image, colors: int = 12) -> np.ndarray:
    """The avatar's dominant flat colors: background, skin, hair, outlines, base layer."""
    quantized = avatar.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT)
    palette = np.asarray(quantized.getpalette()[: colors * 3], dtype=np.int16).reshape(-1, 3)
    counts = np.bincount(np.asarray(quantized).ravel(), minlength=colors)
    return palette[counts > 0]


def segment_garment(
    dressed: Image.Image,
    palette: np.ndarray,
    tolerance: int = 46,
    feather: float = 1.5,
    min_region_ratio: float = 0.004,
) -> Image.Image:
    rgb = np.asarray(dressed.convert("RGB"), dtype=np.int16)
    h, w, _ = rgb.shape

    # Distance from every pixel to its nearest palette entry.
    flat = rgb.reshape(-1, 1, 3)
    distance = np.abs(flat - palette.reshape(1, -1, 3)).max(axis=2).min(axis=1)
    mask = (distance.reshape(h, w) > tolerance).astype(np.uint8) * 255

    mask_img = Image.fromarray(mask, mode="L")
    # Erode away the character's thin black outlines, which share the garment's colour,
    # then dilate the surviving solid garment body back to its true extent.
    mask_img = mask_img.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(9))
    mask_img = _largest_region(mask_img, min_region_ratio)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(feather))

    layer = dressed.convert("RGBA")
    layer.putalpha(mask_img)
    return layer


def _largest_region(mask: Image.Image, min_region_ratio: float) -> Image.Image:
    arr = np.asarray(mask) > 127
    h, w = arr.shape
    min_pixels = int(h * w * min_region_ratio)
    seen = np.zeros_like(arr)
    kept = np.zeros_like(arr)

    for start in zip(*np.nonzero(arr)):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        component = []
        while stack:
            y, x = stack.pop()
            component.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and arr[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(component) >= min_pixels:
            ys, xs = zip(*component)
            kept[list(ys), list(xs)] = True

    return Image.fromarray((kept * 255).astype(np.uint8), mode="L")


if __name__ == "__main__":
    bare = Image.open("flashcloset_base_avatar_v2.jpeg")
    dressed = Image.open("flashcloset_avatar_dressed.jpeg")
    if dressed.size != bare.size:
        dressed = dressed.resize(bare.size, Image.LANCZOS)

    palette = profile_palette(bare)
    print("avatar palette:")
    for c in palette:
        print("   ", tuple(int(v) for v in c))

    layer = segment_garment(dressed, palette)
    layer.save("garment_layer_palette.png")

    alpha = np.asarray(layer)[..., 3]
    solid = alpha > 128
    print(f"coverage: {solid.mean():.4f}")
    rows, cols = np.any(solid, axis=1), np.any(solid, axis=0)
    t, b = np.where(rows)[0][[0, -1]]
    l, r = np.where(cols)[0][[0, -1]]
    print(f"bbox: left={l} top={t} right={r} bottom={b}  size={r-l}x{b-t}")

    Image.alpha_composite(bare.convert("RGBA"), layer).convert("RGB").save(
        "recomposed_palette.jpg", quality=92
    )

    w, h = layer.size
    board = (np.indices((h, w)).sum(axis=0) // 64 % 2 * 40 + 200).astype(np.uint8)
    Image.alpha_composite(Image.fromarray(board).convert("RGBA"), layer).convert("RGB").save(
        "layer_palette_on_checker.jpg", quality=92
    )
    print("done")
