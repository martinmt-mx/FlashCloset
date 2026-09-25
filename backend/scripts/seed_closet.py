"""Seed the closet with the garments already validated by the pipeline experiments.

Lets the frontend be built against real layers without spending generations.

    python backend/scripts/seed_closet.py correo@ejemplo.app
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
from app.db.base import Base  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.jobs import thumbnail  # noqa: E402
from app.api.routes.avatars import transparent_avatar  # noqa: E402
from app.models import DEFAULT_Z_INDEX, Avatar, Category, ClothingItem, ProcessingStatus, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.pipeline import profile_of  # noqa: E402
from app.services.storage import build_storage  # noqa: E402

SEEDS = [
    ("camisole_v3", "camisola de lunares", Category.TOP),
    ("pants_v3", "pantalón negro acampanado", Category.BOTTOM),
    ("tee_v3", "remera blanca estampada", Category.TOP),
    ("shoes_v3", "zapatos camel", Category.SHOES),
]


async def main(email: str) -> None:
    settings = get_settings()
    storage = build_storage(settings)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, hashed_password=hash_password("contrasenia123"),
                        display_name="seed")
            session.add(user)
            await session.commit()
            print(f"created user {email} (password: contrasenia123)")

        avatar = await session.scalar(
            select(Avatar).where(Avatar.user_id == user.id, Avatar.is_default.is_(True))
        )
        if avatar is None:
            profile = profile_of(settings.base_avatar)
            avatar = Avatar(
                user_id=user.id,
                base_image_url=storage.save(transparent_avatar(settings.base_avatar), ".png", "avatars"),
                profile={"size": list(profile.size), "body_box": list(profile.body_box),
                         "background": [int(v) for v in profile.background]},
            )
            session.add(avatar)
            await session.commit()

        for folder, name, category in SEEDS:
            layer = settings.output_dir / folder / "layer.png"
            preview = settings.output_dir / folder / "recomposed.jpg"
            if not layer.exists():
                print(f"skipped {name}: no layer at {layer.relative_to(ROOT)}")
                continue

            existing = await session.scalar(
                select(ClothingItem).where(ClothingItem.user_id == user.id,
                                           ClothingItem.name == name)
            )
            if existing:
                print(f"kept    {name}")
                continue

            thumb = BytesIO()
            thumbnail(Image.open(layer).convert("RGBA")).save(thumb, format="PNG")

            session.add(ClothingItem(
                user_id=user.id,
                avatar_id=avatar.id,
                name=name,
                category=category,
                z_index=DEFAULT_Z_INDEX[category],
                original_image_url=storage.save(layer.read_bytes(), ".png", "originals"),
                layer_image_url=storage.save(layer.read_bytes(), ".png", "layers"),
                thumbnail_image_url=storage.save(thumb.getvalue(), ".png", "thumbs"),
                preview_image_url=storage.save(preview.read_bytes(), ".jpg", "previews")
                if preview.exists() else None,
                status=ProcessingStatus.READY,
                generation={"source": "seeded from validated pipeline output"},
            ))
            print(f"seeded  {name}")

        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "martin@flashcloset.app"))
