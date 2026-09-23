"""Draw the PWA icons in the app's own visual language.

Generated rather than hand-drawn so the palette stays in sync with theme.css: the
same purple stage, the same glossy pink orb with its white rim and highlight.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"

BG_TOP = (90, 33, 150)
BG_BOTTOM = (43, 17, 80)
PINK_LIGHT = (255, 158, 210)
PINK_DEEP = (194, 22, 110)
WHITE = (255, 255, 255)


def draw_icon(size: int, maskable: bool) -> Image.Image:
    icon = Image.new("RGB", (size, size), BG_BOTTOM)
    painter = ImageDraw.Draw(icon)

    for y in range(size):
        blend = y / size
        painter.line(
            [(0, y), (size, y)],
            fill=tuple(round(a + (b - a) * blend) for a, b in zip(BG_TOP, BG_BOTTOM)),
        )

    # A maskable icon may be cropped to a circle by the launcher, so keep the art
    # inside the safe zone rather than filling the square.
    scale = 0.62 if maskable else 0.78
    orb = size * scale
    box = [(size - orb) / 2, (size - orb) / 2, (size + orb) / 2, (size + orb) / 2]

    # Vertical gradient clipped to the disc, rather than stacked ellipses: overlapping
    # shapes read as a blob, a clipped ramp reads as a moulded plastic button.
    ramp = Image.new("RGB", (1, size))
    ramp_painter = ImageDraw.Draw(ramp)
    for y in range(size):
        blend = y / size
        ramp_painter.point(
            (0, y),
            fill=tuple(round(a + (b - a) * blend) for a, b in zip(PINK_LIGHT, PINK_DEEP)),
        )

    disc = Image.new("L", (size, size), 0)
    ImageDraw.Draw(disc).ellipse(box, fill=255)
    icon.paste(ramp.resize((size, size)), (0, 0), disc)

    painter.ellipse(box, outline=WHITE, width=max(3, size // 26))

    # Gloss: translucent, wide and shallow, sitting high enough to clear the glyph.
    # Painted opaque it reads as a white disc stuck on the front rather than a sheen.
    gloss_w, gloss_h = orb * 0.54, orb * 0.17
    sheen = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).ellipse(
        [size / 2 - gloss_w / 2, box[1] + orb * 0.06,
         size / 2 + gloss_w / 2, box[1] + orb * 0.06 + gloss_h],
        fill=(255, 255, 255, 135),
    )
    icon = Image.alpha_composite(icon.convert("RGBA"), sheen).convert("RGB")

    _draw_top(ImageDraw.Draw(icon), size, scale)
    return icon


def _draw_top(painter: ImageDraw.ImageDraw, size: int, scale: float) -> None:
    """A tank top silhouette, the same glyph the Tops category uses."""
    unit = size * scale * 0.34
    cx, cy = size / 2, size / 2 + size * 0.05

    shoulder = unit * 0.62
    hem = unit * 0.52
    top = cy - unit * 0.72
    bottom = cy + unit * 0.78

    painter.polygon(
        [
            (cx - shoulder, top + unit * 0.22),
            (cx - shoulder * 0.52, top),
            (cx - shoulder * 0.16, top + unit * 0.30),
            (cx + shoulder * 0.16, top + unit * 0.30),
            (cx + shoulder * 0.52, top),
            (cx + shoulder, top + unit * 0.22),
            (cx + hem * 0.86, top + unit * 0.62),
            (cx + hem, bottom),
            (cx - hem, bottom),
            (cx - hem * 0.86, top + unit * 0.62),
        ],
        fill=WHITE,
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_icon(size, maskable=False).save(OUT / f"icon-{size}.png")
        print(f"escrito {(OUT / f'icon-{size}.png').name}")
    draw_icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
    print("escrito icon-maskable-512.png")
