"""Cut the base avatar out of its flat backdrop so it sits on the app's stage.

The generator always returns the character on an opaque grey card. Left as-is it
renders as a grey rectangle floating over the room, which breaks the illusion the
whole art direction depends on.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


def cut_out_backdrop(avatar: Image.Image, tolerance: int = 26, feather: float = 1.0) -> Image.Image:
    rgb = np.asarray(avatar.convert("RGB"), dtype=np.int16)

    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0).astype(np.int16)

    character = np.abs(rgb - background).max(axis=2) > tolerance
    character = ndimage.binary_closing(character, iterations=2)

    # Keep the body, drop any speckle the JPEG left in the backdrop.
    labels, count = ndimage.label(character)
    if count > 1:
        sizes = ndimage.sum_labels(character, labels, index=range(1, count + 1))
        character = labels == int(np.argmax(sizes)) + 1
    character = ndimage.binary_fill_holes(character)

    alpha = Image.fromarray((character * 255).astype(np.uint8), mode="L")
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))

    cut = avatar.convert("RGBA")
    cut.putalpha(alpha)
    return cut
