"""Add a batch of real garments to the closets, with or without API credit.

Two modes, because the two generations are the only part that needs Gemini:

    python backend/scripts/add_garments.py --prompts      # print what to paste into Gemini
    python backend/scripts/add_garments.py                # ingest the renders from disk

--prompts writes nothing; it just prints, per garment, the dress prompt and the matte
prompt exactly as the API path sends them, so a run in the Gemini web UI produces the
same two images the pipeline would have produced itself.

Ingest expects, for each garment:
    assets/dressed/<name>.jpeg           the avatar wearing it
    assets/mattes/<name>_inverted.jpeg   the same render, garment flooded magenta

and inserts the extracted layer into every account listed in ACCOUNTS, so both closets
get their own copy aligned to their own character.
"""

from __future__ import annotations

import asyncio
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.jobs import thumbnail  # noqa: E402
from app.models import DEFAULT_Z_INDEX, Avatar, ClothingItem, ProcessingStatus, User  # noqa: E402
from app.services.garment_layer import BodyRegion, MatteStyle, extract_from_matte  # noqa: E402
from app.services.image_generation import _COVERAGE, Category  # noqa: E402
from app.services.image_generation import _MATTE_PROMPT, _PROMPT  # noqa: E402
from app.services.pipeline import _REGION_FOR, profile_of  # noqa: E402
from app.services.storage import LocalStorage  # noqa: E402

ACCOUNTS = ["martin@flashcloset.app", "mar@flashcloset.app"]


class Garment:
    """One real garment: its photo, how it is described to the model, where it sits."""

    def __init__(self, name: str, photo: str, category: Category, label: str, described: str,
                 region: BodyRegion | None = None):
        self.name = name
        self.photo = photo
        self.category = category
        self.label = label          # what the closet shows
        self.described = described  # what the prompts say
        # Category is a wardrobe slot; region is where on the canvas to look for the
        # garment. They usually agree, but knee-high boots are SHOES that reach far
        # above the feet, so the two have to be settable apart.
        self.region = region or _REGION_FOR[category]


BATCH = [
    Garment("vest_grey", "vest_grey.png", Category.TOP, "chaleco gris con blusa blanca",
            "a grey tailored waistcoat worn over a white short-sleeved collared shirt"),
    Garment("skirt_pinstripe", "skirt_pinstripe.png", Category.BOTTOM, "falda negra de rayas",
            "a black pinstriped pleated mini skirt"),
    Garment("skirt_denim", "skirt_denim.png", Category.BOTTOM, "falda de mezclilla",
            "a dark blue denim pleated mini skirt"),
    Garment("shrug_fur", "shrug_fur.webp", Category.OUTERWEAR, "bolero de piel sintética",
            "a cropped brown faux fur shrug jacket with a wide collar and elbow-length sleeves"),
    Garment("heels_red", "heels_red.png", Category.SHOES, "tacones rojos",
            "a pair of red satin pointed-toe slingback kitten heels"),
    Garment("boots_black", "boots_black.png", Category.SHOES, "botas negras largas",
            "a pair of black leather knee-high pointed-toe boots with buckle straps "
            "and a kitten heel", region=BodyRegion.LEGS),
]


def print_prompts() -> None:
    settings = get_settings()
    for garment in BATCH:
        photo = settings.assets_dir / "garments" / garment.photo
        mark = "" if photo.exists() else "   (FALTA LA FOTO)"
        print("=" * 78)
        print(f"{garment.name}  |  {garment.label}  |  {garment.category.value}{mark}")
        print(f"foto: assets/garments/{garment.photo}")
        print(f"guardar en: assets/dressed/{garment.name}.jpeg")
        print("-" * 78)
        print("PASO 1 - adjunta el avatar (assets/avatar/base_v3.jpeg) y la foto de la prenda:")
        print()
        print(_PROMPT.format(
            description=garment.described, coverage=_COVERAGE[garment.category]
        ))
        print("-" * 78)
        print(f"PASO 2 - sobre la imagen del paso 1, guardar en: "
              f"assets/mattes/{garment.name}_inverted.jpeg")
        print()
        print(_MATTE_PROMPT.format(description=garment.described))
        print()


async def ingest() -> None:
    settings = get_settings()
    storage = LocalStorage(settings.media_dir)
    profile = profile_of(settings.base_avatar)

    ready: list[tuple[Garment, Image.Image, Image.Image]] = []
    for garment in BATCH:
        dressed_path = settings.assets_dir / "dressed" / f"{garment.name}.jpeg"
        matte_path = settings.assets_dir / "mattes" / f"{garment.name}_inverted.jpeg"
        missing = [p for p in (dressed_path, matte_path) if not p.exists()]
        if missing:
            print(f"pendiente  {garment.label}: falta "
                  f"{', '.join(str(p.relative_to(ROOT)) for p in missing)}")
            continue

        dressed = Image.open(dressed_path).convert("RGB")
        matte = Image.open(matte_path).convert("RGB")
        layer, stats = extract_from_matte(
            matte, profile, region=garment.region,
            style=MatteStyle.POSITIVE, dressed=dressed,
        )
        # A layer covering almost nothing means the matte pass did not take; adding it
        # would put an invisible garment in the closet, which is worse than skipping it.
        if stats.coverage < 0.005:
            print(f"descartada {garment.label}: la capa salió casi vacía "
                  f"(cobertura {stats.coverage:.3%}), repetir el paso 2")
            continue
        print(f"extraída   {garment.label}: cobertura {stats.coverage:.2%}")
        ready.append((garment, layer, dressed))

    if not ready:
        print("\nno hay nada que insertar todavía")
        await engine.dispose()
        return

    async with SessionFactory() as session:
        for email in ACCOUNTS:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                print(f"  falta la cuenta {email}")
                continue
            avatar = await session.scalar(
                select(Avatar)
                .where(Avatar.user_id == user.id)
                .order_by(Avatar.is_default.desc(), Avatar.created_at)
            )
            if avatar is None:
                print(f"  {email} no tiene personaje")
                continue

            for garment, layer, dressed in ready:
                existing = await session.scalar(
                    select(ClothingItem).where(
                        ClothingItem.user_id == user.id,
                        ClothingItem.name == garment.label,
                    )
                )
                if existing:
                    print(f"  ya estaba  {email:28s} {garment.label}")
                    continue

                png, thumb, preview = BytesIO(), BytesIO(), BytesIO()
                layer.save(png, format="PNG")
                thumbnail(layer).save(thumb, format="PNG")
                dressed.save(preview, format="JPEG", quality=90)

                session.add(ClothingItem(
                    user_id=user.id,
                    avatar_id=avatar.id,
                    name=garment.label,
                    category=garment.category,
                    z_index=DEFAULT_Z_INDEX[garment.category],
                    original_image_url=storage.save(
                        (settings.assets_dir / "garments" / garment.photo).read_bytes(),
                        Path(garment.photo).suffix, "originals",
                    ),
                    layer_image_url=storage.save(png.getvalue(), ".png", "layers"),
                    thumbnail_image_url=storage.save(thumb.getvalue(), ".png", "thumbs"),
                    preview_image_url=storage.save(preview.getvalue(), ".jpg", "previews"),
                    status=ProcessingStatus.READY,
                    generation={"source": f"batch add_garments/{garment.name}"},
                ))
                print(f"  agregada   {email:28s} {garment.label}")

        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    if "--prompts" in sys.argv:
        print_prompts()
    else:
        asyncio.run(ingest())
