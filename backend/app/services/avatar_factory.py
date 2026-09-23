"""Build a user's avatar from their photo, and refuse to keep a bad one.

Every garment layer a user ever generates is aligned to their avatar's geometry, so a
flawed avatar is not a cosmetic problem: an arm crossing the torso poisons every layer
that follows. That asymmetry is why this retries on its own rather than handing the
first result to the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.services.appearance import (
    Appearance,
    AvatarCheck,
    build_avatar_prompt,
    check_avatar,
    measure_appearance,
)
from app.services.image_generation import AvatarDresser


@dataclass(frozen=True)
class AvatarBuild:
    image: Image.Image
    appearance: Appearance
    check: AvatarCheck
    attempts: int


def build_from_photo(
    photo: Image.Image,
    template: Path,
    dresser: AvatarDresser,
    workspace: Path,
    attempts: int = 3,
) -> AvatarBuild:
    """Measure, generate, verify, and retry. The last attempt is returned even if it
    fails its checks, so the caller can show the user what went wrong."""
    appearance = measure_appearance(photo)
    prompt = build_avatar_prompt(appearance)

    workspace.mkdir(parents=True, exist_ok=True)
    photo_path = workspace / "reference.png"
    photo.convert("RGB").save(photo_path)

    best: AvatarBuild | None = None
    try:
        for attempt in range(1, attempts + 1):
            result = dresser.compose(prompt, [template, photo_path])
            image = Image.open(BytesIO(result.image_bytes)).convert("RGB")
            check = check_avatar(image, appearance)
            build = AvatarBuild(image, appearance, check, attempt)
            if check.passed:
                return build
            best = build
    finally:
        photo_path.unlink(missing_ok=True)

    if best is None:
        raise RuntimeError("The avatar generator returned nothing")
    return best


def accept_existing(avatar: Image.Image) -> AvatarBuild:
    """Take an avatar the user already has. Only the pose contract can be checked here,
    since without the original photo there is no likeness to compare against."""
    appearance = measure_appearance(avatar)
    return AvatarBuild(avatar, appearance, check_avatar(avatar, appearance), attempts=0)
