"""Dress the base avatar with a real garment photo, via Gemini image editing.

The model is asked to edit the avatar in place rather than to draw an isolated
garment. Editing the same canvas is what makes the result land at the avatar's
own scale and pose; asking for a standalone layer produces art at an arbitrary
size that no longer lines up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import types


class Category(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    SHOES = "shoes"
    OUTERWEAR = "outerwear"
    FULL_BODY = "full_body"


# What the model should be told to cover, per category.
_COVERAGE: dict[Category, str] = {
    Category.TOP: "her torso and arms",
    Category.BOTTOM: "her hips and legs",
    Category.SHOES: "her feet only",
    Category.OUTERWEAR: "her torso and arms, worn over whatever she already wears",
    Category.FULL_BODY: "her torso, hips and legs",
}

# Flood-filling the garment is a small local edit; repainting everything around it is a
# whole-canvas rewrite, which the model degrades on when the garment is small (shoes).
_MATTE_PROMPT = """\
Recolour ONLY the {description} in this image to pure flat magenta #FF00FF. Fill it \
completely with that single solid colour, edge to edge, with no shading, no gradient and \
no highlights inside it, so it becomes a flat magenta silhouette of exactly its current shape.

Everything else must stay EXACTLY as it is: the background, her skin, her body, her face \
and her hair keep their original colours. Do not move, resize, redraw or restyle anything, \
and do not change the canvas size. The only difference between input and output must be the \
colour of the {description}.
"""

_PROMPT = """\
Image 1 is my 2D avatar. Image 2 is a photo of a real garment ({description}).

Edit IMAGE 1 in place: dress the character in that garment, drawn in the same \
illustrated art style as the avatar. This is an in-place edit, so these rules are absolute:

1) Return the same canvas at the same resolution, same crop, same zoom.
2) The character must not move, resize, or change pose by even one pixel — same body \
position, same arm angles, same leg position, same head, same hair, same face.
3) Everything not covered by the garment must stay exactly as it is in image 1: the \
background, the skin, the head, the hair.
4) Only add the garment onto {coverage}, fitted naturally to her exact body position.
5) Keep the garment's real colour, cut, pattern and details faithful to the photo.
6) Do not redraw or restyle the character. Do not add any other clothing or accessories.
"""


@dataclass(frozen=True)
class DressResult:
    image_bytes: bytes
    mime_type: str
    model: str
    text_response: str | None


class Dresser(Protocol):
    """Any image-editing backend able to run the pipeline's two passes."""

    def dress(
        self, avatar_path: Path, garment_path: Path, category: Category, description: str
    ) -> DressResult: ...

    def matte(self, dressed: DressResult, description: str) -> DressResult: ...


class AvatarDresser:
    """Thin wrapper over the image model, so the pipeline can be tested with a fake."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def dress(
        self,
        avatar_path: Path,
        garment_path: Path,
        category: Category,
        description: str,
    ) -> DressResult:
        """Pass one: draw the garment onto the avatar, in place."""
        prompt = _PROMPT.format(description=description, coverage=_COVERAGE[category])
        return self._generate([prompt, _as_part(avatar_path), _as_part(garment_path)])

    def matte(self, dressed: DressResult, description: str) -> DressResult:
        """Pass two: repaint everything except the garment magenta, so it can be keyed out.

        This costs a second generation, but it is what makes extraction work for garments
        whose colour is close to the avatar's own — cream, white, skin-toned leather.
        """
        prompt = _MATTE_PROMPT.format(description=description)
        part = types.Part.from_bytes(data=dressed.image_bytes, mime_type=dressed.mime_type)
        return self._generate([prompt, part])

    def compose(self, prompt: str, images: list[Path]) -> DressResult:
        """Free-form generation from a prompt and reference images, used for avatars."""
        return self._generate([prompt, *(_as_part(path) for path in images)])

    def _generate(self, contents: list) -> DressResult:
        response = self._client.models.generate_content(
            model=self._model, contents=contents
        )

        image_part = _first_image(response)
        if image_part is None:
            raise RuntimeError(
                f"The model returned no image. Text was: {_first_text(response)!r}"
            )

        return DressResult(
            image_bytes=image_part.data,
            mime_type=image_part.mime_type or "image/png",
            model=self._model,
            text_response=_first_text(response),
        )


_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _as_part(path: Path) -> types.Part:
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"Unsupported image type: {path.suffix}")
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def _iter_parts(response) -> list:
    if not response.candidates:
        return []
    content = response.candidates[0].content
    return list(content.parts or []) if content else []


def _first_image(response):
    for part in _iter_parts(response):
        if getattr(part, "inline_data", None) and part.inline_data.data:
            return part.inline_data
    return None


def _first_text(response) -> str | None:
    for part in _iter_parts(response):
        if getattr(part, "text", None):
            return part.text
    return None
