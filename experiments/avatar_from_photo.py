"""Measure a photo, print the avatar prompt, and check a generated avatar against it.

    python experiments/avatar_from_photo.py FOTO [AVATAR_GENERADO]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.appearance import (  # noqa: E402
    build_avatar_prompt,
    check_avatar,
    measure_appearance,
)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    photo_path = Path(sys.argv[1])
    appearance = measure_appearance(Image.open(photo_path))

    print(f"foto: {photo_path.name}")
    print(f"  piel {appearance.skin_hex}  (confianza {appearance.skin_confidence:.1%})")
    print(f"  pelo {appearance.hair_hex or 'no medible — preguntar al usuario'}"
          f"  (confianza {appearance.hair_confidence:.1%})")

    if len(sys.argv) < 3:
        print("\n--- prompt ---\n")
        print(build_avatar_prompt(appearance))
        return 0

    avatar_path = Path(sys.argv[2])
    check = check_avatar(Image.open(avatar_path), appearance)
    print(f"\navatar: {avatar_path.name}")
    print(check.report())
    return 0 if check.passed else 1


if __name__ == "__main__":
    sys.exit(main())
