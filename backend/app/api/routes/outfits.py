"""Saved looks: which garments are worn together, and in what order."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.avatars import ensure_default_avatar
from app.models import EXCLUSIVE_SLOTS, ClothingItem, Outfit, OutfitItem
from app.schemas import OutfitIn, OutfitOut

router = APIRouter(prefix="/outfits", tags=["outfits"])


@router.post("", response_model=OutfitOut, status_code=status.HTTP_201_CREATED)
async def create_outfit(body: OutfitIn, session: SessionDep, user: CurrentUser) -> Outfit:
    avatar_id = body.avatar_id or (await ensure_default_avatar(session, user)).id
    outfit = Outfit(user_id=user.id, avatar_id=avatar_id, name=body.name)

    seen_slots: set[str] = set()
    for entry in body.items:
        item = await session.get(ClothingItem, entry.clothing_item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such garment: {entry.clothing_item_id}")

        slot = EXCLUSIVE_SLOTS.get(item.category)
        if slot and slot in seen_slots:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Two garments cannot both occupy the {slot} slot"
            )
        if slot:
            seen_slots.add(slot)

        outfit.items.append(
            OutfitItem(
                clothing_item_id=item.id,
                z_index=entry.z_index if entry.z_index is not None else item.z_index,
                offset_x=entry.offset_x,
                offset_y=entry.offset_y,
                scale=entry.scale,
            )
        )

    session.add(outfit)
    await session.commit()
    return await _load(session, outfit.id)


@router.get("", response_model=list[OutfitOut])
async def list_outfits(session: SessionDep, user: CurrentUser) -> list[Outfit]:
    result = await session.scalars(
        select(Outfit)
        .where(Outfit.user_id == user.id)
        .options(selectinload(Outfit.items))
        .order_by(Outfit.created_at.desc())
    )
    return list(result)


@router.get("/{outfit_id}", response_model=OutfitOut)
async def get_outfit(outfit_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Outfit:
    outfit = await _load(session, outfit_id)
    if outfit is None or outfit.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such outfit")
    return outfit


@router.delete("/{outfit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outfit(outfit_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    outfit = await session.get(Outfit, outfit_id)
    if outfit is None or outfit.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such outfit")
    await session.delete(outfit)
    await session.commit()


async def _load(session: SessionDep, outfit_id: uuid.UUID) -> Outfit | None:
    return await session.scalar(
        select(Outfit).where(Outfit.id == outfit_id).options(selectinload(Outfit.items))
    )
