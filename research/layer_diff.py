"""Extract a garment layer by diffing a dressed avatar against the bare avatar.

The generative model reliably draws a garment at the right scale and pose when it
edits the avatar image in place, but it will not produce an isolated layer at that
same scale. Diffing the two renders recovers the layer without asking the model for it.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def extract_garment_layer(
    bare: Image.Image,
    dressed: Image.Image,
    threshold: int = 28,
    feather: float = 1.5,
    min_region_ratio: float = 0.002,
) -> Image.Image:
    """Return the dressed-avatar pixels that differ from the bare avatar, as RGBA."""
    if bare.size != dressed.size:
        dressed = dressed.resize(bare.size, Image.LANCZOS)

    bare_rgb = np.asarray(bare.convert("RGB"), dtype=np.int16)
    dressed_rgb = np.asarray(dressed.convert("RGB"), dtype=np.int16)

    # Max channel deviation is less forgiving of the model's subtle global re-rendering
    # than a mean would be, which keeps skin and background from leaking into the layer.
    delta = np.abs(dressed_rgb - bare_rgb).max(axis=2)
    mask = (delta > threshold).astype(np.uint8) * 255

    mask_img = Image.fromarray(mask, mode="L")
    # Close pinholes inside the garment, then drop speckle from re-rendering noise.
    mask_img = mask_img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    mask_img = _keep_largest_regions(mask_img, min_region_ratio)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(feather))

    layer = dressed.convert("RGBA")
    layer.putalpha(mask_img)
    return layer


def _keep_largest_regions(mask: Image.Image, min_region_ratio: float) -> Image.Image:
    """Drop connected components smaller than `min_region_ratio` of the canvas."""
    arr = np.asarray(mask) > 127
    h, w = arr.shape
    min_pixels = int(h * w * min_region_ratio)

    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    kept = np.zeros((h, w), dtype=bool)

    for start in zip(*np.nonzero(arr)):
        if labels[start]:
            continue
        current += 1
        stack = [start]
        labels[start] = current
        component = []
        while stack:
            y, x = stack.pop()
            component.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and arr[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = current
                    stack.append((ny, nx))
        if len(component) >= min_pixels:
            ys, xs = zip(*component)
            kept[list(ys), list(xs)] = True

    return Image.fromarray((kept * 255).astype(np.uint8), mode="L")


if __name__ == "__main__":
    bare = Image.open("flashcloset_base_avatar_v2.jpeg")
    dressed = Image.open("flashcloset_avatar_dressed.jpeg")

    layer = extract_garment_layer(bare, dressed)
    layer.save("garment_layer_diff.png")

    alpha = np.asarray(layer)[..., 3]
    print(f"layer coverage: {(alpha > 128).mean():.4f}")
    rows, cols = np.any(alpha > 128, axis=1), np.any(alpha > 128, axis=0)
    t, b = np.where(rows)[0][[0, -1]]
    l, r = np.where(cols)[0][[0, -1]]
    print(f"layer bbox: left={l} top={t} right={r} bottom={b}  size={r-l}x{b-t}")

    # Recompose the extracted layer back onto the bare avatar.
    Image.alpha_composite(bare.convert("RGBA"), layer).convert("RGB").save(
        "recomposed.jpg", quality=92
    )

    # And show the layer alone on a neutral backdrop.
    w, h = layer.size
    board = (np.indices((h, w)).sum(axis=0) // 64 % 2 * 40 + 200).astype(np.uint8)
    backdrop = Image.fromarray(board).convert("RGBA")
    Image.alpha_composite(backdrop, layer).convert("RGB").save("layer_on_checker.jpg", quality=92)
    print("done")
