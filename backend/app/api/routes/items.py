"""The closet: upload a garment photo, watch it process, adjust how it sits."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.avatars import ensure_default_avatar
from app.config import get_settings
from app.jobs import process_item
from app.models import DEFAULT_Z_INDEX, Category, ClothingItem, ProcessingStatus
from app.schemas import ClothingItemOut, CopyRequest, Fit, ShareFlag
from app.services.storage import LocalStorage

router = APIRouter(prefix="/clothing-items", tags=["closet"])

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


@router.post("", response_model=ClothingItemOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_item(
    session: SessionDep,
    user: CurrentUser,
    background: BackgroundTasks,
    photo: UploadFile = File(...),
    category: Category = Form(...),
    name: str | None = Form(None),
    avatar_id: uuid.UUID | None = Form(None),
) -> ClothingItem:
    """Accepts the photo and returns straight away; the pipeline runs in the background."""
    raw = await photo.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The photo is over 12MB")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The photo is empty")

    avatar_for_item = avatar_id or (await ensure_default_avatar(session, user)).id
    storage = LocalStorage(get_settings().media_dir)
    suffix = "." + (photo.filename or "photo.jpg").rsplit(".", 1)[-1].lower()

    item = ClothingItem(
        user_id=user.id,
        avatar_id=avatar_for_item,
        name=name,
        category=category,
        z_index=DEFAULT_Z_INDEX[category],
        original_image_url=storage.save(raw, suffix, folder="originals"),
        status=ProcessingStatus.PENDING,
    )
    session.add(item)
    await session.commit()

    background.add_task(process_item, item.id, raw, photo.filename or "photo.jpg")
    return item


@router.get("", response_model=list[ClothingItemOut])
async def list_items(
    session: SessionDep,
    user: CurrentUser,
    category: Category | None = None,
    avatar_id: uuid.UUID | None = None,
) -> list[ClothingItem]:
    """A closet belongs to one avatar: its layers are aligned to that body's geometry,
    so garments made for one character do not fit another."""
    avatar = avatar_id or (await ensure_default_avatar(session, user)).id
    query = select(ClothingItem).where(
        ClothingItem.user_id == user.id, ClothingItem.avatar_id == avatar
    )
    if category:
        query = query.where(ClothingItem.category == category)
    result = await session.scalars(query.order_by(ClothingItem.created_at.desc()))
    return list(result)


@router.get("/{item_id}", response_model=ClothingItemOut)
async def get_item(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ClothingItem:
    return await _owned(session, user, item_id)


@router.patch("/{item_id}/fit", response_model=ClothingItemOut)
async def save_fit(
    item_id: uuid.UUID, body: Fit, session: SessionDep, user: CurrentUser
) -> ClothingItem:
    """Stores the adjustment once so the garment sits right every time it is worn."""
    item = await _owned(session, user, item_id)
    item.offset_x, item.offset_y, item.scale = body.offset_x, body.offset_y, body.scale
    await session.commit()
    return item


@router.post("/{item_id}/reprocess", response_model=ClothingItemOut, status_code=status.HTTP_202_ACCEPTED)
async def reprocess(
    item_id: uuid.UUID, session: SessionDep, user: CurrentUser, background: BackgroundTasks
) -> ClothingItem:
    """Generation varies run to run, so a poor layer is worth one more attempt."""
    item = await _owned(session, user, item_id)
    if item.status is ProcessingStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "That garment is already being processed")

    original = get_settings().media_dir / item.original_image_url.split("/media/")[-1]
    if not original.exists():
        raise HTTPException(status.HTTP_410_GONE, "The original photo is no longer stored")

    item.status = ProcessingStatus.PENDING
    item.error = None
    await session.commit()
    background.add_task(process_item, item.id, original.read_bytes(), original.name)
    return item


@router.patch("/{item_id}/share", response_model=ClothingItemOut)
async def set_shared(
    item_id: uuid.UUID, body: ShareFlag, session: SessionDep, user: CurrentUser
) -> ClothingItem:
    item = await _owned(session, user, item_id)
    if body.shared and item.status is not ProcessingStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a finished garment can be shared")
    item.is_shared = body.shared
    await session.commit()
    return item


@router.get("/shared/catalog", response_model=list[ClothingItemOut])
async def shared_catalog(
    session: SessionDep,
    user: CurrentUser,
    category: Category | None = None,
    avatar_id: uuid.UUID | None = None,
) -> list[ClothingItem]:
    """Everything that can be added to a closet that is not generated from scratch.

    That means garments other people shared, and also your own from your other
    characters: a second avatar starts empty, and re-generating clothes you already
    own would be paying twice for the same wardrobe.
    """
    destination = avatar_id or (await ensure_default_avatar(session, user)).id
    query = select(ClothingItem).where(
        ClothingItem.status == ProcessingStatus.READY,
        ClothingItem.avatar_id != destination,
        or_(
            ClothingItem.is_shared.is_(True),
            ClothingItem.user_id == user.id,
        ),
    )
    if category:
        query = query.where(ClothingItem.category == category)
    result = await session.scalars(query.order_by(ClothingItem.created_at.desc()))

    owned = await _roots_in_closet(session, destination)
    return [
        item
        for item in result
        if (item.is_shared or item.user_id == user.id) and _root_of(item) not in owned
    ]


@router.post("/{item_id}/copy", response_model=ClothingItemOut, status_code=status.HTTP_201_CREATED)
async def copy_to_closet(
    item_id: uuid.UUID, body: CopyRequest, session: SessionDep, user: CurrentUser
) -> ClothingItem:
    """Take a shared garment into your closet.

    The layer files are immutable, so the copy points at the same images rather than
    duplicating them; what it gets of its own is the fit, since it will be worn on a
    different body and will likely need a nudge.
    """
    source = await session.get(ClothingItem, item_id)
    if source is None or not (source.is_shared or source.user_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared garment")
    if source.status is not ProcessingStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "That garment is not finished yet")

    avatar_id = body.avatar_id or (await ensure_default_avatar(session, user)).id

    # A garment is the same garment however many times it is passed along, so the
    # identity that matters is the original it descends from, not the row copied.
    if _root_of(source) in await _roots_in_closet(session, avatar_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ese personaje ya tiene esa prenda en su clóset"
        )

    copy = ClothingItem(
        user_id=user.id,
        avatar_id=avatar_id,
        name=source.name,
        category=source.category,
        z_index=source.z_index,
        original_image_url=source.original_image_url,
        layer_image_url=source.layer_image_url,
        preview_image_url=source.preview_image_url,
        thumbnail_image_url=source.thumbnail_image_url,
        status=ProcessingStatus.READY,
        offset_x=source.offset_x,
        offset_y=source.offset_y,
        scale=source.scale,
        source_item_id=source.id,
        generation={**source.generation, "copied_from": str(source.id)},
    )
    session.add(copy)
    await session.commit()
    return copy


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await session.delete(await _owned(session, user, item_id))
    await session.commit()


def _root_of(item: ClothingItem) -> uuid.UUID:
    """The original a garment descends from; a garment is its own root."""
    return item.source_item_id or item.id


async def _roots_in_closet(session: SessionDep, avatar_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(ClothingItem).where(ClothingItem.avatar_id == avatar_id)
    )
    return {_root_of(item) for item in rows}


async def _owned(session: SessionDep, user: CurrentUser, item_id: uuid.UUID) -> ClothingItem:
    item = await session.get(ClothingItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such garment")
    return item
