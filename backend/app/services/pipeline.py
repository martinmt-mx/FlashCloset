"""Turn a photo of real clothing into a garment layer for the avatar.

    photo + avatar ──► dress (generation 1) ──► matte (generation 2) ──► chroma key ──► layer

Generating on the avatar rather than in isolation is what makes the garment land at the
right scale and drape to the body; the matte pass is what makes it cuttable regardless of
the garment's colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.services.garment_layer import (
    AvatarProfile,
    BodyRegion,
    LayerStats,
    MatteStyle,
    extract_from_matte,
    profile_avatar,
)
from app.services.image_generation import Category, Dresser

_REGION_FOR: dict[Category, BodyRegion] = {
    Category.TOP: BodyRegion.TORSO,
    Category.OUTERWEAR: BodyRegion.TORSO,
    Category.BOTTOM: BodyRegion.LEGS,
    Category.SHOES: BodyRegion.FEET,
    Category.FULL_BODY: BodyRegion.WHOLE,
}


@dataclass(frozen=True)
class GarmentAsset:
    layer: Image.Image      # RGBA, aligned to the avatar canvas
    preview: Image.Image    # the dressed render, useful for a thumbnail
    matte: Image.Image      # kept for debugging a bad extraction
    stats: LayerStats
    model: str


class GarmentPipeline:
    def __init__(self, dresser: Dresser, avatar_path: Path) -> None:
        self._dresser = dresser
        self._avatar_path = avatar_path
        self._profile = profile_of(avatar_path)

    @property
    def profile(self) -> AvatarProfile:
        return self._profile

    def process(
        self, garment_path: Path, category: Category, description: str
    ) -> GarmentAsset:
        dressed = self._dresser.dress(
            avatar_path=self._avatar_path,
            garment_path=garment_path,
            category=category,
            description=description,
        )
        matte = self._dresser.matte(dressed, description=description)

        matte_image = Image.open(BytesIO(matte.image_bytes)).convert("RGB")
        preview = Image.open(BytesIO(dressed.image_bytes)).convert("RGB")
        layer, stats = extract_from_matte(
            matte_image,
            self._profile,
            region=_REGION_FOR[category],
            style=MatteStyle.POSITIVE,
            dressed=preview,
        )

        return GarmentAsset(
            layer=layer,
            preview=preview,
            matte=matte_image,
            stats=stats,
            model=dressed.model,
        )


def profile_of(avatar_path: Path) -> AvatarProfile:
    return profile_avatar(Image.open(avatar_path).convert("RGB"))
