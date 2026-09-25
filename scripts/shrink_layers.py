"""Shrink the stored PNG layers without changing how they look or where they sit.

The pipeline writes full-canvas RGBA PNGs in truecolour, which run 2-4 MB each. The
garments are flat cel-shaded art with a few dozen real colours, so almost all of that
is wasted. Quantising the colour channel alone takes roughly 6x off.

The alpha channel is deliberately left untouched. Quantising RGBA together is far
smaller still, but it collapses the soft edge the matte pipeline works to produce
(256 alpha levels down to about 85), which shows up as jagged garment outlines.

    python scripts/shrink_layers.py --dry-run   # measure, change nothing
    python scripts/shrink_layers.py             # rewrite in place, after a backup

Filenames do not change, so no database URL has to be rewritten.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("layers", "avatars")
COLOURS = 192


def shrink(data: bytes) -> tuple[bytes, float]:
    """Return the smaller PNG and the mean colour error over visible pixels."""
    original = Image.open(BytesIO(data)).convert("RGBA")
    alpha = original.getchannel("A")

    rgb = original.convert("RGB").quantize(colors=COLOURS, method=Image.FASTOCTREE)
    smaller = rgb.convert("RGBA")
    smaller.putalpha(alpha)

    before = np.asarray(original, dtype=np.int16)
    after = np.asarray(smaller, dtype=np.int16)
    visible = before[..., 3] > 40
    error = (
        float(np.abs(before[..., :3][visible] - after[..., :3][visible]).mean())
        if visible.any()
        else 0.0
    )

    buffer = BytesIO()
    smaller.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="measure only")
    parser.add_argument("--media", default=str(ROOT / "media"))
    args = parser.parse_args()

    media = Path(args.media)
    files = [p for folder in FOLDERS for p in sorted((media / folder).glob("*.png"))]
    if not files:
        print(f"no hay PNG en {media}")
        return 1

    if not args.dry_run:
        backup = media.with_name(media.name + "_sin_comprimir")
        if backup.exists():
            print(f"ya existe el respaldo {backup.name}; muevelo o borralo antes de seguir")
            return 1
        backup.mkdir(parents=True)
        for folder in FOLDERS:
            shutil.copytree(media / folder, backup / folder)
        print(f"respaldo en {backup.name}")

    total_before = total_after = 0
    worst = 0.0
    for path in files:
        data = path.read_bytes()
        smaller, error = shrink(data)
        worst = max(worst, error)
        total_before += len(data)
        # A "smaller" file that came out bigger means the source was already efficient;
        # keeping the original is strictly better than writing a worse one.
        if len(smaller) < len(data):
            total_after += len(smaller)
            if not args.dry_run:
                path.write_bytes(smaller)
        else:
            total_after += len(data)

    saved = total_before - total_after
    print(f"{len(files)} archivos")
    print(f"  antes   {total_before / 1e6:7.1f} MB")
    print(f"  despues {total_after / 1e6:7.1f} MB   (-{saved / 1e6:.1f} MB, "
          f"{total_before / max(total_after, 1):.1f}x)")
    print(f"  peor error de color: {worst:.1f} / 255")
    if args.dry_run:
        print("\n(dry-run: no se escribio nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
