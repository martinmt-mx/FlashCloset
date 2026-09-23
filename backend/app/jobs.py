"""Background processing of an uploaded garment photo.

The two generations take tens of seconds, so the upload endpoint returns immediately
and this runs afterwards, moving the row through pending → processing → ready/failed.
Failures are recorded on the row instead of raising into nowhere.
"""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.db.session import SessionFactory
from app.models import ClothingItem, ProcessingStatus
from app.services.dressers import build_dresser
from app.services.image_generation import Category as GenCategory
from app.services.pipeline import GarmentPipeline
from app.services.storage import LocalStorage


async def process_item(item_id: uuid.UUID, photo: bytes, filename: str) -> None:
    settings = get_settings()
    async with SessionFactory() as session:
        item = await session.get(ClothingItem, item_id)
        if item is None:
            return
        item.status = ProcessingStatus.PROCESSING
        await session.commit()

        category = GenCategory(item.category.value)
        description = item.name or f"a {item.category.value}"

        try:
            asset = await asyncio.to_thread(
                _run_pipeline, settings.base_avatar, photo, filename, category, description
            )
        except Exception as exc:  # noqa: BLE001 - the failure belongs on the row
            item.status = ProcessingStatus.FAILED
            item.error = str(exc)[:1000]
            await session.commit()
            return

        storage = LocalStorage(settings.media_dir)
        item.layer_image_url = storage.save(_png(asset.layer), ".png", folder="layers")
        item.preview_image_url = storage.save(_jpeg(asset.preview), ".jpg", folder="previews")
        item.thumbnail_image_url = storage.save(
            _png(thumbnail(asset.layer)), ".png", folder="thumbs"
        )
        item.generation = {
            "model": asset.model,
            "coverage": asset.stats.coverage,
            "bbox": list(asset.stats.bbox),
        }
        item.status = ProcessingStatus.READY
        item.error = None
        await session.commit()


def _run_pipeline(
    avatar_path: Path, photo: bytes, filename: str, category: GenCategory, description: str
):
    settings = get_settings()
    pipeline = GarmentPipeline(build_dresser(settings), avatar_path)

    # The generator reads the garment from disk, so stage the upload next to it.
    staged = settings.media_dir / "uploads" / f"{uuid.uuid4().hex}{Path(filename).suffix or '.png'}"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(photo)
    try:
        return pipeline.process(staged, category, description)
    finally:
        staged.unlink(missing_ok=True)


def thumbnail(layer: Image.Image, size: int = 200) -> Image.Image:
    """Crop an RGBA layer to its visible content and fit it into a square."""
    box = layer.getbbox()
    cropped = layer.crop(box) if box else layer
    cropped.thumbnail((size, size), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(cropped, ((size - cropped.width) // 2, (size - cropped.height) // 2), cropped)
    return canvas


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()
