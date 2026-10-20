"""The public wall.

Reading is open to anyone with the link, which is the point: the wall is the front
page. Writing needs an account, and there is deliberately nothing to react with, so
no endpoint exists for likes or replies.
"""

from __future__ import annotations

import uuid
from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.models import Post
from app.schemas import PostOut
from app.services.storage import build_storage

router = APIRouter(prefix="/posts", tags=["wall"])

MAX_BODY = 500
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Posted photos are read at a glance on a phone; full camera resolution would cost
# the reader seconds of loading for detail the layout never shows.
MAX_IMAGE_EDGE = 1600


def _as_out(post: Post) -> PostOut:
    author = post.user.display_name or post.user.email.split("@")[0]
    return PostOut(
        id=post.id,
        author=author,
        body=post.body,
        feeling=post.feeling,
        image_url=post.image_url,
        created_at=post.created_at,
    )


@router.get("", response_model=list[PostOut])
async def list_posts(session: SessionDep, limit: int = 50) -> list[PostOut]:
    """Newest first. No authentication: this is the front page."""
    result = await session.scalars(
        select(Post)
        .options(selectinload(Post.user))
        .order_by(desc(Post.created_at))
        .limit(max(1, min(limit, 200)))
    )
    return [_as_out(post) for post in result]


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    session: SessionDep,
    user: CurrentUser,
    body: str = Form(""),
    feeling: str | None = Form(None),
    photo: UploadFile | None = File(None),
) -> PostOut:
    text = body.strip()
    mood = (feeling or "").strip() or None

    raw = await photo.read() if photo is not None else b""
    if not text and not raw:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A post needs either words or a picture"
        )
    if len(text) > MAX_BODY:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Keep it under {MAX_BODY} characters"
        )
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That picture is too large")

    image_url = None
    if raw:
        try:
            picture = Image.open(BytesIO(raw))
            picture.load()
        except (UnidentifiedImageError, OSError):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "That file is not an image"
            ) from None

        picture = picture.convert("RGB")
        picture.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.LANCZOS)
        buffer = BytesIO()
        picture.save(buffer, format="JPEG", quality=86, optimize=True)
        storage = build_storage(get_settings())
        image_url = storage.save(buffer.getvalue(), ".jpg", folder="posts")

    post = Post(user_id=user.id, body=text, feeling=mood, image_url=image_url)
    session.add(post)
    await session.commit()
    # user is already loaded; attaching it avoids a lazy load on a closed session.
    post.user = user
    return _as_out(post)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(session: SessionDep, user: CurrentUser, post_id: uuid.UUID) -> None:
    post = await session.get(Post, post_id)
    # Same answer whether it never existed or belongs to the other account: the
    # wall is public, so an owner should not be discoverable by probing ids.
    if post is None or post.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such post")
    await session.delete(post)
    await session.commit()
