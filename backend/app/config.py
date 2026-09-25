"""Application settings, loaded from the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Secrets live in gitignored env files; nothing secret is ever hardcoded here.
# Both files are read, not just the first one found: the API key predates the hosting
# settings and still lives on its own, so stopping at it would silently ignore .env.
# load_dotenv does not overwrite what is already set, so the first file to define a
# name wins, and a real environment variable beats both.
for candidate in (PROJECT_ROOT / "gemini_api_key.env", PROJECT_ROOT / ".env"):
    if candidate.exists():
        load_dotenv(candidate)


class Settings(BaseSettings):
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    image_model: str = Field(default="gemini-3.1-flash-image", alias="IMAGE_MODEL")

    # "gemini" is fast and costs per image; "comfy" runs FLUX.1 Kontext on the local GPU,
    # which is free but takes minutes per pass and holds the card while it works.
    dresser_backend: str = Field(default="gemini", alias="DRESSER_BACKEND")
    comfy_url: str = Field(default="http://127.0.0.1:8188", alias="COMFY_URL")

    # SQLite in development; point this at Postgres in production and nothing else changes.
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'flashcloset.db').as_posix()}",
        alias="DATABASE_URL",
    )
    # 32 bytes minimum for HS256. Production must override this via JWT_SECRET;
    # the default exists so a fresh clone runs, not because it is safe.
    jwt_secret: str = Field(
        default="dev-only-insecure-key-replace-me-in-production", alias="JWT_SECRET"
    )
    jwt_ttl_hours: int = 24 * 14

    assets_dir: Path = PROJECT_ROOT / "assets"
    output_dir: Path = PROJECT_ROOT / "output"
    media_dir: Path = PROJECT_ROOT / "media"

    # "local" writes under media_dir and serves it from /media; "s3" puts the files in
    # an S3-compatible bucket. Hosted, the container's disk is wiped on every redeploy,
    # so anything that must outlive a deploy has to be "s3".
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    r2_bucket: str = Field(default="", alias="R2_BUCKET")
    r2_endpoint_url: str = Field(default="", alias="R2_ENDPOINT_URL")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    # What the browser fetches: the bucket's public domain, not the upload endpoint.
    r2_public_base_url: str = Field(default="", alias="R2_PUBLIC_BASE_URL")

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # A tunnelled URL is reachable by anyone who has it, so registration is closed by
    # default and opened either outright or behind a shared code.
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")
    invite_code: str = Field(default="", alias="INVITE_CODE")

    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    class Config:
        populate_by_name = True
        extra = "ignore"

    @property
    def base_avatar(self) -> Path:
        return self.assets_dir / "avatar" / "base_v3.jpeg"

    def require_gemini_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Put it in gemini_api_key.env at the project root."
            )
        return self.gemini_api_key

    # Kept so the experiment scripts written before the API keep working.
    @classmethod
    def load(cls) -> "Settings":
        settings = get_settings()
        settings.require_gemini_key()
        return settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
