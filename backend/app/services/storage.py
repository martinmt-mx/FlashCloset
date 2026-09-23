"""Where generated images live.

Behind an interface from the start so moving to S3 later is a config change rather
than a rewrite of every call site.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    def save(self, content: bytes, suffix: str, folder: str = "") -> str:
        """Store bytes and return the URL the frontend should request."""


class LocalStorage(StorageBackend):
    def __init__(self, root: Path, base_url: str = "/media") -> None:
        self._root = root
        self._base_url = base_url.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, suffix: str, folder: str = "") -> str:
        name = f"{uuid.uuid4().hex}{suffix}"
        directory = self._root / folder if folder else self._root
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(content)
        return f"{self._base_url}/{folder}/{name}" if folder else f"{self._base_url}/{name}"
