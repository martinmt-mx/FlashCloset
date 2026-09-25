"""Move the closet off this machine: files to the bucket, rows to Postgres.

Run it once, from the machine that still holds the real data. It reads the local
SQLite database and media folder and writes to whatever DATABASE_URL and R2_* point
at, so nothing is destroyed: the local copy stays exactly as it is and can be run
again if a step goes wrong.

    python backend/scripts/migrate_to_cloud.py --check    # credentials only
    python backend/scripts/migrate_to_cloud.py --files    # upload media/
    python backend/scripts/migrate_to_cloud.py --db       # copy the rows
    python backend/scripts/migrate_to_cloud.py --all

Object keys mirror the local paths, so "media/layers/ab12.png" becomes the key
"layers/ab12.png". That makes rewriting the stored URLs a plain prefix swap instead
of a lookup table, and makes a re-run overwrite rather than duplicate.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models import Avatar, ClothingItem, Outfit, OutfitItem, User  # noqa: E402
from app.services.storage import S3Storage  # noqa: E402

LOCAL_PREFIX = "/media/"
# Parents before children: a row cannot be inserted before what it points at exists.
ORDER = (User, Avatar, ClothingItem, Outfit, OutfitItem)
URL_COLUMNS = {
    Avatar: ("base_image_url",),
    ClothingItem: (
        "original_image_url",
        "layer_image_url",
        "thumbnail_image_url",
        "preview_image_url",
    ),
}


def bucket_from(settings) -> S3Storage:
    missing = [
        name
        for name, value in (
            ("R2_BUCKET", settings.r2_bucket),
            ("R2_ENDPOINT_URL", settings.r2_endpoint_url),
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_PUBLIC_BASE_URL", settings.r2_public_base_url),
        )
        if not value
    ]
    if missing:
        raise SystemExit("faltan variables: " + ", ".join(missing))
    return S3Storage(
        bucket=settings.r2_bucket,
        endpoint_url=settings.r2_endpoint_url,
        access_key=settings.r2_access_key_id,
        secret_key=settings.r2_secret_access_key,
        public_base_url=settings.r2_public_base_url,
    )


def rewrite(url: str | None, public_base: str) -> str | None:
    """Point a stored URL at the bucket. Anything already absolute is left alone."""
    if not url or not url.startswith(LOCAL_PREFIX):
        return url
    return f"{public_base.rstrip('/')}/{url[len(LOCAL_PREFIX):]}"


def upload_files(settings) -> int:
    storage = bucket_from(settings)
    media = settings.media_dir
    files = [p for p in media.rglob("*") if p.is_file()]
    if not files:
        print("no hay archivos en media/")
        return 0

    total = 0
    for i, path in enumerate(files, 1):
        key = path.relative_to(media).as_posix()
        storage.put_at(key, path.read_bytes(), path.suffix)
        total += path.stat().st_size
        if i % 25 == 0 or i == len(files):
            print(f"  {i}/{len(files)}  ({total / 1e6:.1f} MB)")
    print(f"subidos {len(files)} archivos, {total / 1e6:.1f} MB")
    return len(files)


async def heal_orphan_roots(src) -> int:
    """Repair garments descended from an original that no longer exists.

    Retiring the generic character deleted the garments it owned, and SQLite does not
    enforce foreign keys, so the copies kept pointing at ids that had gone. Postgres
    does enforce them and refuses the insert.

    Nulling the dangling id would satisfy the constraint but break copy de-duplication:
    `source_item_id or id` is what identifies a garment across closets, so two copies
    of one original would stop looking related and could be imported twice. Instead the
    oldest of each orphaned group is promoted to be the root and its siblings point at
    it, which keeps every group identified by a single id, as before.

    This only edits the in-memory objects being copied; the local database is untouched.
    """
    items = list(await src.scalars(select(ClothingItem)))
    known = {item.id for item in items}
    orphans: dict[object, list[ClothingItem]] = {}
    for item in items:
        if item.source_item_id and item.source_item_id not in known:
            orphans.setdefault(item.source_item_id, []).append(item)

    for group in orphans.values():
        group.sort(key=lambda item: item.created_at)
        root, rest = group[0], group[1:]
        root.source_item_id = None
        for sibling in rest:
            sibling.source_item_id = root.id
    return len(orphans)


async def copy_rows(settings) -> None:
    local_url = f"sqlite+aiosqlite:///{(ROOT / 'flashcloset.db').as_posix()}"
    remote_url = settings.database_url
    if remote_url.startswith("sqlite"):
        raise SystemExit(
            "DATABASE_URL sigue apuntando a SQLite; ponlo en el Postgres de destino"
        )

    source = create_async_engine(local_url)
    target = create_async_engine(remote_url)
    SourceSession = async_sessionmaker(source, expire_on_commit=False)
    TargetSession = async_sessionmaker(target, expire_on_commit=False)

    async with target.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SourceSession() as src, TargetSession() as dst:
        repointed = await heal_orphan_roots(src)
        if repointed:
            print(f"  raices huerfanas reparadas: {repointed}")

        # Looks can name garments that were deleted from under them; SQLite let those
        # rows linger and Postgres will not. They are already broken, so they are
        # skipped rather than migrated into a constraint violation.
        live_items = set(await src.scalars(select(ClothingItem.id)))

        for model in ORDER:
            rows = list(await src.scalars(select(model)))
            # Composite keys exist (outfit_items), so identity is the whole primary key.
            keys = [column.name for column in model.__table__.primary_key.columns]

            def key_of(row) -> tuple:
                return tuple(getattr(row, name) for name in keys)

            existing = {key_of(row) for row in await dst.scalars(select(model))}
            added = skipped = 0
            for row in rows:
                if key_of(row) in existing:
                    continue
                if model is OutfitItem and row.clothing_item_id not in live_items:
                    skipped += 1
                    continue
                values = {
                    column.name: getattr(row, column.name)
                    for column in model.__table__.columns
                }
                for field in URL_COLUMNS.get(model, ()):
                    values[field] = rewrite(values.get(field), settings.r2_public_base_url)
                dst.add(model(**values))
                added += 1
            await dst.commit()
            note = f"  ({skipped} saltadas por prenda inexistente)" if skipped else ""
            print(f"  {model.__name__:14s} {added} nuevas de {len(rows)}{note}")

    await source.dispose()
    await target.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--db", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not any((args.check, args.files, args.db, args.all)):
        parser.print_help()
        return 1

    if args.check or args.all:
        bucket_from(settings)
        print("credenciales R2: ok")
        print(f"DATABASE_URL -> {settings.database_url.split('@')[-1]}")
        print(f"URLs publicas -> {settings.r2_public_base_url}")

    if args.files or args.all:
        print("\nsubiendo media/ ...")
        upload_files(settings)

    if args.db or args.all:
        print("\ncopiando filas ...")
        asyncio.run(copy_rows(settings))

    return 0


if __name__ == "__main__":
    sys.exit(main())
