"""Run the garment pipeline over real photos and report what came out.

    python experiments/pipeline_smoke_test.py              # all cases, via the API
    python experiments/pipeline_smoke_test.py --local      # reuse renders on disk
    python experiments/pipeline_smoke_test.py camisole     # one case

--local skips both generations and reads assets/dressed + assets/mattes instead,
so the extraction can be iterated on without spending API credit.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.garment_layer import MatteStyle, extract_from_matte  # noqa: E402
from app.services.image_generation import AvatarDresser, Category  # noqa: E402
from app.services.pipeline import _REGION_FOR, GarmentAsset, GarmentPipeline, profile_of  # noqa: E402

AVATAR = "base_v3.jpeg"


@dataclass(frozen=True)
class Case:
    name: str
    filename: str
    category: Category
    description: str


CASES = [
    Case("camisole_v3", "camisole_polkadot.webp", Category.TOP,
         "a cream satin camisole with black polka dots and cream lace trim"),
    Case("pants_v3", "pants_black.webp", Category.BOTTOM,
         "black flared trousers with a pale pink and black lace waistband"),
    Case("tee_v3", "tee_print.webp", Category.TOP,
         "a white short-sleeved t-shirt with a vintage kewpie mermaid print on the front"),
    Case("shoes_v3", "shoes_tan.webp", Category.SHOES,
         "a pair of tan leather mary jane flats with an ankle strap"),
]


def from_disk(case: Case, settings: Settings, profile) -> GarmentAsset:
    dressed_path = settings.assets_dir / "dressed" / f"{case.name}.jpeg"
    if not dressed_path.exists():
        raise FileNotFoundError(f"missing {dressed_path.relative_to(ROOT)}")

    # A "_inverted" file is a positive matte: the garment itself is flooded magenta.
    positive_path = settings.assets_dir / "mattes" / f"{case.name}_inverted.jpeg"
    matte_path = positive_path if positive_path.exists() else (
        settings.assets_dir / "mattes" / f"{case.name}.jpeg"
    )
    if not matte_path.exists():
        raise FileNotFoundError(f"missing {matte_path.relative_to(ROOT)}")

    dressed = Image.open(dressed_path).convert("RGB")
    matte = Image.open(matte_path).convert("RGB")
    style = MatteStyle.POSITIVE if matte_path == positive_path else MatteStyle.NEGATIVE
    layer, stats = extract_from_matte(
        matte, profile, region=_REGION_FOR[case.category], style=style, dressed=dressed
    )
    return GarmentAsset(
        layer=layer, preview=dressed, matte=matte, stats=stats, model=f"local/{style.value}"
    )


def report(case: Case, asset: GarmentAsset, avatar: Image.Image, out_dir: Path) -> None:
    out = out_dir / case.name
    out.mkdir(parents=True, exist_ok=True)

    asset.layer.save(out / "layer.png")
    asset.preview.save(out / "dressed.png")
    Image.alpha_composite(avatar.convert("RGBA"), asset.layer).convert("RGB").save(
        out / "recomposed.jpg", quality=92
    )
    _on_checker(asset.layer).save(out / "layer_on_checker.jpg", quality=92)

    left, top, right, bottom = asset.stats.bbox
    print(f"  coverage {asset.stats.coverage:.4f}   bbox {asset.stats.bbox}"
          f"   {right - left}x{bottom - top}")


def _on_checker(layer: Image.Image) -> Image.Image:
    w, h = layer.size
    board = (np.indices((h, w)).sum(axis=0) // 64 % 2 * 38 + 200).astype(np.uint8)
    return Image.alpha_composite(Image.fromarray(board).convert("RGBA"), layer).convert("RGB")


def main() -> None:
    settings = Settings.load()
    use_local = "--local" in sys.argv
    wanted = {a for a in sys.argv[1:] if not a.startswith("--")}
    cases = [c for c in CASES if not wanted or any(w in c.name for w in wanted)]

    avatar_path = settings.assets_dir / "avatar" / AVATAR
    avatar = Image.open(avatar_path).convert("RGB")
    profile = profile_of(avatar_path)

    use_comfy = "--comfy" in sys.argv
    source = "local renders" if use_local else "ComfyUI + Kontext" if use_comfy else settings.image_model
    print(f"source : {source}")
    print(f"avatar : {AVATAR} {avatar.size}, body box {profile.body_box}")

    pipeline = None
    if use_comfy:
        from app.services.comfy_dresser import ComfyKontextDresser

        pipeline = GarmentPipeline(ComfyKontextDresser(), avatar_path)
    elif not use_local:
        dresser = AvatarDresser(api_key=settings.gemini_api_key, model=settings.image_model)
        pipeline = GarmentPipeline(dresser, avatar_path)

    for case in cases:
        print(f"\n=== {case.name} ({case.category.value}) ===")
        started = time.monotonic()
        try:
            if use_local:
                asset = from_disk(case, settings, profile)
            else:
                asset = pipeline.process(
                    settings.assets_dir / "garments" / case.filename,
                    case.category,
                    case.description,
                )
        except Exception as exc:  # noqa: BLE001 - an experiment reports, it does not crash
            print(f"  FAILED: {exc}")
            continue

        print(f"  {time.monotonic() - started:.1f}s")
        out_dir = settings.output_dir / "comfy" if use_comfy else settings.output_dir
        report(case, asset, avatar, out_dir)
        if use_comfy:
            asset.matte.save(out_dir / case.name / "matte.png")

    print(f"\nOutputs in {settings.output_dir}")


if __name__ == "__main__":
    main()
