"""Pick the image backend the pipeline runs on.

Both implement the same contract, so nothing downstream knows which one it got.
"""

from __future__ import annotations

from app.config import Settings
from app.services.image_generation import Dresser


def build_dresser(settings: Settings) -> Dresser:
    if settings.dresser_backend == "comfy":
        from app.services.comfy_dresser import ComfyKontextDresser

        return ComfyKontextDresser(base_url=settings.comfy_url)

    from app.services.image_generation import AvatarDresser

    return AvatarDresser(
        api_key=settings.require_gemini_key(), model=settings.image_model
    )
