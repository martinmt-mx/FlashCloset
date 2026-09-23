"""Turn a magenta segmentation matte into a clean, reusable garment layer.

The matte comes back with junk the model added around the edges — letterbox bars
where it changed the aspect ratio, and occasionally scenery leaked in from the
source photo. Keeping the largest blob inside the category's region of the body
discards all of it without needing to know what the junk is.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from app.services.chroma import KeyColor, remove_chroma


class MatteStyle(str, Enum):
    """Which side of the matte the key colour marks.

    NEGATIVE asks the model to repaint everything except the garment, which means
    rewriting almost the whole canvas — it degrades badly when the garment is small.
    POSITIVE asks it to flood-fill just the garment, a small local edit, and is the
    more reliable instruction; the garment's real colours then come from the dressed
    render rather than from the matte.
    """

    NEGATIVE = "negative"
    POSITIVE = "positive"


class BodyRegion(str, Enum):
    """Vertical slice of the character a category may occupy."""

    TORSO = "torso"
    LEGS = "legs"
    FEET = "feet"
    WHOLE = "whole"


# Fractions of the character's bounding-box height, measured from its top.
_REGION_SPAN: dict[BodyRegion, tuple[float, float]] = {
    BodyRegion.TORSO: (0.00, 0.62),
    BodyRegion.LEGS: (0.38, 1.00),
    BodyRegion.FEET: (0.82, 1.00),
    BodyRegion.WHOLE: (0.00, 1.00),
}


@dataclass(frozen=True)
class AvatarProfile:
    """Facts about the base avatar, computed once and stored with it."""

    size: tuple[int, int]
    background: np.ndarray                # (3,) the flat backdrop colour
    body_box: tuple[int, int, int, int]   # left, top, right, bottom of the character


def profile_avatar(avatar: Image.Image) -> AvatarProfile:
    rgb = np.asarray(avatar.convert("RGB"), dtype=np.int16)

    # The backdrop is flat, so the border median identifies it without guessing.
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0).astype(np.int16)

    is_body = np.abs(rgb - background).max(axis=2) > 24
    rows, cols = np.any(is_body, axis=1), np.any(is_body, axis=0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]

    return AvatarProfile(
        size=avatar.size,
        background=background,
        body_box=(int(left), int(top), int(right), int(bottom)),
    )


@dataclass(frozen=True)
class LayerStats:
    coverage: float
    bbox: tuple[int, int, int, int]


def extract_from_matte(
    matte: Image.Image,
    profile: AvatarProfile,
    region: BodyRegion = BodyRegion.WHOLE,
    feather: float = 1.3,
    style: MatteStyle = MatteStyle.POSITIVE,
    dressed: Image.Image | None = None,
) -> tuple[Image.Image, LayerStats]:
    """Cut the garment out of a magenta matte, scaled to the avatar's canvas."""
    if matte.size != profile.size:
        matte = matte.resize(profile.size, Image.LANCZOS)

    if style is MatteStyle.NEGATIVE:
        keyed = remove_chroma(matte, KeyColor.MAGENTA)
        solid = np.asarray(keyed)[..., 3] > 128
    else:
        if dressed is None:
            raise ValueError("A positive matte needs the dressed render for its colours.")
        keyed = dressed.convert("RGBA")
        if keyed.size != profile.size:
            keyed = keyed.resize(profile.size, Image.LANCZOS)
        solid = _is_magenta(matte)

    solid &= _region_mask(profile, region)
    solid = _keep_main_blobs(solid)
    solid = ndimage.binary_fill_holes(solid)

    if not solid.any():
        raise ValueError("The matte contained no garment inside the expected region.")

    alpha = Image.fromarray((solid * 255).astype(np.uint8), mode="L")
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))

    layer = keyed.copy()
    layer.putalpha(alpha)

    rows, cols = np.any(solid, axis=1), np.any(solid, axis=0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    stats = LayerStats(
        coverage=float(solid.mean()),
        bbox=(int(left), int(top), int(right), int(bottom)),
    )
    return layer, stats


def _is_magenta(image: Image.Image) -> np.ndarray:
    """Hue test rather than an exact match, so shading inside the fill still counts."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (np.minimum(red, blue) - green > 0.25) & (np.abs(red - blue) < 0.35)


def _region_mask(profile: AvatarProfile, region: BodyRegion) -> np.ndarray:
    left, top, right, bottom = profile.body_box
    start, end = _REGION_SPAN[region]
    height = bottom - top

    width, canvas_height = profile.size
    mask = np.zeros((canvas_height, width), dtype=bool)
    # Generous horizontal padding: sleeves and skirts swing wider than the bare body.
    pad = int((right - left) * 0.6)
    y0 = max(0, top + int(height * start) - 10)
    y1 = min(canvas_height, top + int(height * end) + 10)
    mask[y0:y1, max(0, left - pad) : min(width, right + pad)] = True
    return mask


def _keep_main_blobs(mask: np.ndarray, relative_size: float = 0.25) -> np.ndarray:
    """Keep every blob at least `relative_size` of the biggest one.

    Keeping only the biggest would drop one of a pair of shoes, since the two are
    separate components. The ratio still discards speckle and the letterbox bars the
    model sometimes adds, which are far smaller than the garment.
    """
    mask = ndimage.binary_opening(mask, iterations=2)
    labels, count = ndimage.label(mask)
    if count <= 1:
        return mask

    sizes = ndimage.sum_labels(mask, labels, index=range(1, count + 1))
    keep = np.where(sizes >= sizes.max() * relative_size)[0] + 1
    return np.isin(labels, keep)
