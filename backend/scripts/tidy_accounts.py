"""One-off maintenance: rotate passwords, name the characters, retire the template one.

The generic character stays on disk as the pose template new avatars are generated
from; what gets removed is its copy sitting in someone's wardrobe.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionFactory, engine  # noqa: E402
from app.models import Avatar, ClothingItem, Outfit, User  # noqa: E402
from app.security import hash_password  # noqa: E402

OWNER = "martin@flashcloset.app"
GUEST = "mar@flashcloset.app"


def new_password() -> str:
    return secrets.token_urlsafe(10)


async def main() -> None:
    passwords = {OWNER: new_password(), GUEST: new_password()}

    async with SessionFactory() as db:
        for email, password in passwords.items():
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                print(f"  falta la cuenta {email}")
                continue
            user.hashed_password = hash_password(password)

        guest = await db.scalar(select(User).where(User.email == GUEST))
        if guest:
            guest.display_name = "Mar"
            for avatar in await db.scalars(select(Avatar).where(Avatar.user_id == guest.id)):
                avatar.name = "Mar"
                avatar.is_default = True

        owner = await db.scalar(select(User).where(User.email == OWNER))
        if owner:
            avatars = list(await db.scalars(select(Avatar).where(Avatar.user_id == owner.id)))
            generic = [a for a in avatars if a.name == "default"]
            keeper = next((a for a in avatars if a.name != "default"), None)

            if keeper and generic:
                keeper.name = "Mar"
                keeper.is_default = True
                kept_roots = {
                    (item.source_item_id or item.id)
                    for item in await db.scalars(
                        select(ClothingItem).where(ClothingItem.avatar_id == keeper.id)
                    )
                }
                for stale in generic:
                    # Move the wardrobe across before dropping the character, otherwise
                    # the cascade would take the garments with it.
                    for item in await db.scalars(
                        select(ClothingItem).where(ClothingItem.avatar_id == stale.id)
                    ):
                        root = item.source_item_id or item.id
                        if root in kept_roots:
                            await db.delete(item)
                        else:
                            kept_roots.add(root)
                            item.avatar_id = keeper.id
                    for outfit in await db.scalars(
                        select(Outfit).where(Outfit.avatar_id == stale.id)
                    ):
                        outfit.avatar_id = keeper.id
                    await db.delete(stale)
                print(f"  personaje genérico retirado de {OWNER}")

        await db.commit()

        print("\ncredenciales nuevas:")
        for email, password in passwords.items():
            print(f"  {email:28s} {password}")

        print("\npersonajes por cuenta:")
        for user in await db.scalars(select(User)):
            names = [a.name for a in await db.scalars(
                select(Avatar).where(Avatar.user_id == user.id)
            )]
            if names:
                print(f"  {user.email:28s} {names}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
