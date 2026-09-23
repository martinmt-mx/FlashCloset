"""Measure a person's appearance from their photo, and check a generated avatar against it.

Measuring beats asking. A user cannot name their own skin tone in a way a renderer can
use, and an identity label like a nationality does not determine pixels — worse, it tends
to drag the model toward its own stereotype. A hex value taken from the photo is objective,
and the same measurement run on the result tells us whether the model honoured it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage


@dataclass(frozen=True)
class Appearance:
    skin_rgb: tuple[int, int, int]
    hair_rgb: tuple[int, int, int] | None
    skin_confidence: float          # fraction of the frame classified as skin
    hair_confidence: float

    @property
    def skin_hex(self) -> str:
        return "#%02X%02X%02X" % self.skin_rgb

    @property
    def hair_hex(self) -> str | None:
        return None if self.hair_rgb is None else "#%02X%02X%02X" % self.hair_rgb


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Classic RGB skin rule: red dominant, not grey, not blown out."""
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    return (
        (red > 95) & (green > 40) & (blue > 20)
        & (spread > 15) & (np.abs(red - green) > 15)
        & (red > green) & (green > blue) & (red < 250)
    )


def measure_appearance(photo: Image.Image) -> Appearance:
    rgb = np.asarray(photo.convert("RGB"), dtype=np.float32)
    height = rgb.shape[0]

    skin = _skin_mask(rgb)
    skin_pixels = rgb[skin]
    skin_rgb = (
        tuple(int(v) for v in np.median(skin_pixels, axis=0))
        if skin_pixels.size
        else (200, 160, 140)
    )

    # Hair: dark, unsaturated-ish pixels in the upper part of the frame, next to skin.
    # Only trusted when there is enough of it; otherwise the caller should ask instead.
    top = rgb[: int(height * 0.45)]
    luma = top @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    near_head = ndimage.binary_dilation(skin[: int(height * 0.45)], iterations=12)
    hair = near_head & (luma < 140) & ~_skin_mask(top)

    hair_pixels = top[hair]
    hair_confidence = float(hair.mean())
    hair_rgb = (
        tuple(int(v) for v in np.median(hair_pixels, axis=0))
        if hair_confidence > 0.01
        else None
    )

    return Appearance(
        skin_rgb=skin_rgb,
        hair_rgb=hair_rgb,
        skin_confidence=float(skin.mean()),
        hair_confidence=hair_confidence,
    )


def _hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    high, low = max(rgb), min(rgb)
    value = high / 255.0
    saturation = 0.0 if high == 0 else (high - low) / high
    if high == low:
        return 0.0, saturation, value

    red, green, blue = rgb
    span = high - low
    if high == red:
        hue = (green - blue) / span % 6
    elif high == green:
        hue = (blue - red) / span + 2
    else:
        hue = (red - green) / span + 4
    return hue * 60.0, saturation, value


def _hue_gap(a: float, b: float) -> float:
    gap = abs(a - b) % 360
    return min(gap, 360 - gap)


@dataclass(frozen=True)
class AvatarCheck:
    passed: bool
    problems: list[str]
    skin_delta: tuple[int, int, int]
    arm_runs: float
    body_fill: float

    def report(self) -> str:
        status = "OK" if self.passed else "RECHAZADO"
        lines = [f"{status}  desvio de piel={self.skin_delta}"
                 f"  tramos en cintura={self.arm_runs:.1f}"
                 f"  altura del cuerpo={self.body_fill:.0%}"]
        lines += [f"  - {problem}" for problem in self.problems]
        return "\n".join(lines)


def check_avatar(
    avatar: Image.Image,
    expected: Appearance,
    max_hue_gap: float = 8.0,
    max_saturation_gap: float = 0.09,
    max_value_gap: float = 0.22,
    min_body_fill: float = 0.75,
) -> AvatarCheck:
    """Reject an avatar before it becomes the base every garment is aligned to.

    A bad avatar is expensive in a way a bad garment is not: every layer generated
    afterwards inherits its pose, so an arm crossing the torso poisons the whole closet.
    """
    rgb = np.asarray(avatar.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape
    problems: list[str] = []

    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0)
    if np.abs(border - background).max(axis=1).mean() > 12:
        problems.append("el fondo no es plano")

    subject = np.abs(rgb - background).max(axis=2) > 24
    subject = ndimage.binary_opening(subject, iterations=2)
    if not subject.any():
        return AvatarCheck(False, ["no se encontró ninguna figura"], (0, 0, 0), 0.0, 0.0)

    rows = np.where(np.any(subject, axis=1))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    body_fill = (bottom - top) / height
    if body_fill < min_body_fill:
        problems.append(f"la figura ocupa solo el {body_fill:.0%} del alto")
    if top < 4 or bottom > height - 4:
        problems.append("la figura toca el borde del lienzo")

    # At the waist a correct pose reads as three runs across a scanline: arm, body, arm.
    band = subject[top + int((bottom - top) * 0.45) : top + int((bottom - top) * 0.58)]
    runs = [ndimage.label(row)[1] for row in band]
    arm_runs = float(np.median(runs)) if runs else 0.0
    if arm_runs < 3:
        problems.append("los brazos no están despegados del torso")

    measured = measure_appearance(avatar)
    delta = tuple(int(a - b) for a, b in zip(measured.skin_rgb, expected.skin_rgb))

    # Hue and saturation carry the likeness; lightness is judged loosely because the
    # illustrated style legitimately brightens skin, and raw RGB distance punishes that
    # far harder than the eye does.
    got, want = _hsv(measured.skin_rgb), _hsv(expected.skin_rgb)
    if _hue_gap(got[0], want[0]) > max_hue_gap:
        problems.append(
            f"el matiz de la piel se desvió: {got[0]:.0f}° en vez de {want[0]:.0f}°"
        )
    if abs(got[1] - want[1]) > max_saturation_gap:
        direction = "saturada" if got[1] > want[1] else "apagada"
        problems.append(
            f"la piel quedó demasiado {direction}: {got[1]:.2f} contra {want[1]:.2f}"
        )
    if abs(got[2] - want[2]) > max_value_gap:
        direction = "clara" if got[2] > want[2] else "oscura"
        problems.append(f"la piel quedó demasiado {direction}: {got[2]:.2f} contra {want[2]:.2f}")

    return AvatarCheck(not problems, problems, delta, arm_runs, body_fill)


AVATAR_PROMPT = """\
Image 1 is the pose template for my dress-up game. Image 2 is a photo of a real person.

Create a 2D character avatar of the person in image 2, drawn in EXACTLY the pose, framing, \
proportions and art style of image 1: semi-flat cel-shaded illustration, clean bold \
outlines, soft shading.

Pose rules, taken from image 1 and not from the photo, all mandatory:
1) Full body, front-facing, weight on one leg with the hip slightly popped.
2) One arm bent about 90 degrees at the elbow, forearm forward and out, hand in a loose fist.
3) The other arm hangs down and away from the body at about 25 degrees, and its hand must \
NOT touch the hip or thigh - leave a clear gap of background between that arm and the body.
4) Nothing crosses in front of the torso or the thighs: no arm, no hand, no hair.
5) Hair kept behind the shoulders, off the chest. Both wrists visible.
6) Legs slightly apart, not overlapping.

Appearance, to be matched exactly:
- Skin tone is exactly {skin_hex}. Do not tan it, do not warm it, do not make it more \
orange or more sun-kissed than that value.{hair_line}
- Keep her face, hair length and texture, glasses and tattoos recognisable as the same person.

Ignore the clothes in the photo. Dress the avatar only in a plain neutral beige base \
bodysuit, because clothing layers are drawn on top later.

Flat uniform light grey background, no gradient, no shadow. Portrait 3:4, the character \
filling most of the frame height with a small even margin.
"""


def build_avatar_prompt(appearance: Appearance) -> str:
    hair_line = (
        f"\n- Hair colour is approximately {appearance.hair_hex}."
        if appearance.hair_hex
        else ""
    )
    return AVATAR_PROMPT.format(skin_hex=appearance.skin_hex, hair_line=hair_line)
