"""The base character every garment layer is aligned to."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.models import Avatar, User
from app.schemas import AvatarOut
from app.services.avatar_factory import accept_existing, build_from_photo
from app.services.avatar_prep import cut_out_backdrop
from app.services.dressers import build_dresser
from app.services.garment_layer import profile_avatar
from app.services.pipeline import profile_of
from app.services.storage import build_storage

router = APIRouter(prefix="/avatars", tags=["avatar"])


@router.get("", response_model=list[AvatarOut])
async def list_avatars(session: SessionDep, user: CurrentUser) -> list[Avatar]:
    await ensure_default_avatar(session, user)
    result = await session.scalars(select(Avatar).where(Avatar.user_id == user.id))
    return list(result)


@router.post("", response_model=AvatarOut, status_code=status.HTTP_201_CREATED)
async def create_avatar(
    session: SessionDep,
    user: CurrentUser,
    photo: UploadFile = File(...),
    mode: Literal["generate", "import"] = Form("generate"),
    name: str = Form("mi personaje"),
    make_default: bool = Form(False),
) -> Avatar:
    """Create an avatar from a full-body photo, or import one already drawn.

    Closets do not transfer between avatars: a garment layer is aligned to the body it
    was generated against. A new avatar therefore starts empty, and its garments are
    filled by generating or by copying shared ones.
    """
    raw = await photo.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The photo is empty")

    settings = get_settings()
    source = Image.open(BytesIO(raw))

    if mode == "import":
        build = accept_existing(source.convert("RGB"))
    else:
        dresser = build_dresser(settings)
        try:
            build = await run_in_threadpool(
                build_from_photo, source, settings.base_avatar, dresser,
                settings.media_dir / "tmp",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Avatar generation failed: {exc}"
            ) from exc

    if not build.check.passed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "The avatar did not pass its checks", "problems": build.check.problems},
        )

    cut = cut_out_backdrop(build.image)
    buffer = BytesIO()
    cut.save(buffer, format="PNG")

    storage = build_storage(settings)
    profile = profile_avatar(build.image)

    if make_default:
        for other in await session.scalars(
            select(Avatar).where(Avatar.user_id == user.id, Avatar.is_default.is_(True))
        ):
            other.is_default = False

    avatar = Avatar(
        user_id=user.id,
        name=name,
        base_image_url=storage.save(buffer.getvalue(), ".png", folder="avatars"),
        is_default=make_default,
        profile={
            "size": list(profile.size),
            "body_box": list(profile.body_box),
            "background": [int(v) for v in profile.background],
            "skin": build.appearance.skin_hex,
            "attempts": build.attempts,
        },
    )
    session.add(avatar)
    await session.commit()
    return avatar


async def ensure_default_avatar(session: AsyncSession, user: User) -> Avatar:
    """Give the user a character to dress, bootstrapping one only if they have none.

    The check is "any avatar", not "a default one": once someone has made their own
    character and dropped the generic template, re-creating it would put a stranger
    back in their wardrobe every time this ran.
    """
    existing = await session.scalar(
        select(Avatar)
        .where(Avatar.user_id == user.id)
        .order_by(Avatar.is_default.desc(), Avatar.created_at)
    )
    if existing:
        return existing

    settings = get_settings()
    source = settings.base_avatar
    storage = build_storage(settings)
    profile = profile_of(source)

    avatar = Avatar(
        user_id=user.id,
        name="default",
        base_image_url=storage.save(transparent_avatar(source), ".png", folder="avatars"),
        is_default=True,
        profile={
            "size": list(profile.size),
            "body_box": list(profile.body_box),
            "background": [int(v) for v in profile.background],
        },
    )
    session.add(avatar)
    await session.commit()
    return avatar


def transparent_avatar(source: Path) -> bytes:
    buffer = BytesIO()
    cut_out_backdrop(Image.open(source).convert("RGB")).save(buffer, format="PNG")
    return buffer.getvalue()
