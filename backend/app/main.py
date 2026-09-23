"""FlashCloset API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response
from starlette.types import Scope


class SpaFiles(StaticFiles):
    """Serve the single-page app, falling back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return FileResponse(Path(self.directory) / "index.html")

from app.api.routes import auth, avatars, items, outfits
from app.config import get_settings
from app.db.base import Base
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine while the schema is still moving; Alembic owns it once it settles.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(title="FlashCloset", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, avatars.router, items.router, outfits.router):
    app.include_router(router, prefix="/api")

settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "image_backend": settings.dresser_backend}


# Serving the built frontend from the API keeps everything on one origin, which means
# one URL to expose and no CORS to configure. Mounted last so /api and /media win.
if settings.frontend_dist.is_dir():
    app.mount("/", SpaFiles(directory=settings.frontend_dist, html=True), name="app")
