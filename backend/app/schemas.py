"""Request and response shapes for the API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Category, ProcessingStatus


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None
    invite_code: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None


class AvatarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_image_url: str
    is_default: bool
    profile: dict


class Fit(BaseModel):
    """Normalised placement, as fractions of the avatar canvas."""

    offset_x: float = Field(ge=-1, le=1)
    offset_y: float = Field(ge=-1, le=1)
    scale: float = Field(gt=0.1, le=3)


class ClothingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    category: Category
    z_index: int
    status: ProcessingStatus
    error: str | None
    original_image_url: str
    layer_image_url: str | None
    preview_image_url: str | None
    thumbnail_image_url: str | None
    offset_x: float
    offset_y: float
    scale: float
    is_shared: bool
    source_item_id: uuid.UUID | None
    created_at: datetime


class ShareFlag(BaseModel):
    shared: bool


class CopyRequest(BaseModel):
    avatar_id: uuid.UUID | None = None


class OutfitItemIn(BaseModel):
    clothing_item_id: uuid.UUID
    z_index: int | None = None
    offset_x: float | None = None
    offset_y: float | None = None
    scale: float | None = None


class OutfitIn(BaseModel):
    name: str | None = None
    avatar_id: uuid.UUID | None = None
    items: list[OutfitItemIn] = []


class OutfitItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clothing_item_id: uuid.UUID
    z_index: int
    offset_x: float | None
    offset_y: float | None
    scale: float | None


class OutfitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    avatar_id: uuid.UUID
    is_favorite: bool
    created_at: datetime
    items: list[OutfitItemOut]
