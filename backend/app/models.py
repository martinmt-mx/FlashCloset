"""The closet's data model.

Two decisions here come from what the image pipeline turned out to need:

* The fit transform (offset/scale) lives on `ClothingItem` as the item's default,
  because a garment is adjusted once and then looks right every time it is worn.
  `OutfitItem` can still override it for a single look.
* Garments are processed asynchronously, so `status` and `error` are part of the
  row rather than something inferred from whether a file exists.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JsonColumn, created_at, updated_at, uuid_pk


class Category(str, enum.Enum):
    TOP = "top"
    BOTTOM = "bottom"
    SHOES = "shoes"
    OUTERWEAR = "outerwear"
    ACCESSORY = "accessory"
    FULL_BODY = "full_body"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


# Painting order. Bottoms go under tops, outerwear over both, accessories last.
DEFAULT_Z_INDEX: dict[Category, int] = {
    Category.SHOES: 5,
    Category.BOTTOM: 10,
    Category.FULL_BODY: 15,
    Category.TOP: 20,
    Category.OUTERWEAR: 30,
    Category.ACCESSORY: 40,
}

# Only one garment per slot can be worn at a time; outerwear layers over a top.
EXCLUSIVE_SLOTS: dict[Category, str] = {
    Category.TOP: "torso",
    Category.FULL_BODY: "torso",
    Category.BOTTOM: "legs",
    Category.SHOES: "feet",
    Category.OUTERWEAR: "outer",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_at()

    avatars: Mapped[list["Avatar"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    items: Mapped[list["ClothingItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    outfits: Mapped[list["Outfit"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="default")
    base_image_url: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)

    # Measured once from the base image; the pipeline needs it to place every garment.
    profile: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    created_at: Mapped[datetime] = created_at()

    user: Mapped[User] = relationship(back_populates="avatars")


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    avatar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("avatars.id", ondelete="CASCADE"))

    name: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[Category] = mapped_column(Enum(Category, native_enum=False), index=True)
    z_index: Mapped[int] = mapped_column(Integer)

    original_image_url: Mapped[str] = mapped_column(Text)
    layer_image_url: Mapped[str | None] = mapped_column(Text)
    preview_image_url: Mapped[str | None] = mapped_column(Text)
    # The layer sits in a full-body canvas, so a garment shrinks to a few pixels in a
    # wardrobe button. The thumbnail is the layer cropped to what it actually covers.
    thumbnail_image_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, native_enum=False), default=ProcessingStatus.PENDING, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)

    # Normalised fit, as fractions of the avatar canvas, so it holds at any render size.
    offset_x: Mapped[float] = mapped_column(Float, default=0.0)
    offset_y: Mapped[float] = mapped_column(Float, default=0.0)
    scale: Mapped[float] = mapped_column(Float, default=1.0)

    # Prompt, model and layer metrics, kept for debugging a bad extraction later.
    generation: Mapped[dict] = mapped_column(JsonColumn, default=dict)

    # Sharing. Every avatar is generated from the same pose template, so bodies come out
    # within a couple of percent of each other and a borrowed layer lands close enough for
    # the fit control to finish the job. Copies carry their own fit so adjusting a borrowed
    # garment never touches the original.
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clothing_items.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    user: Mapped[User] = relationship(back_populates="items")

    @property
    def slot(self) -> str | None:
        return EXCLUSIVE_SLOTS.get(self.category)


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    avatar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("avatars.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(String(100))
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_at()

    user: Mapped[User] = relationship(back_populates="outfits")
    items: Mapped[list["OutfitItem"]] = relationship(
        back_populates="outfit", cascade="all, delete-orphan", order_by="OutfitItem.z_index"
    )


class OutfitItem(Base):
    __tablename__ = "outfit_items"
    __table_args__ = (UniqueConstraint("outfit_id", "clothing_item_id"),)

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True
    )
    clothing_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clothing_items.id", ondelete="CASCADE"), primary_key=True
    )
    z_index: Mapped[int] = mapped_column(Integer)

    # Null means "use the garment's own saved fit"; set only when this look differs.
    offset_x: Mapped[float | None] = mapped_column(Float)
    offset_y: Mapped[float | None] = mapped_column(Float)
    scale: Mapped[float | None] = mapped_column(Float)

    outfit: Mapped[Outfit] = relationship(back_populates="items")
    item: Mapped[ClothingItem] = relationship()
