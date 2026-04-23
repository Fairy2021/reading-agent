from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import requests

from app.tools.image_generate_tool import image_generate_tool
from app.core.config import settings


def build_portrait_seed(book_id: str, character_id: str) -> int:
    raw = f"{book_id}:{character_id}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:8], 16)


def generate_character_portrait(*, book_id: str, character_id: str, prompt: str) -> tuple[str, str]:
    seed = build_portrait_seed(book_id=book_id, character_id=character_id)
    result = image_generate_tool(prompt=prompt, seed=seed)
    return result["image_url"], result["generator"]


def _infer_extension(content_type: str, fallback: str = ".jpg") -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(content_type.lower(), fallback)


def cache_remote_portrait(*, image_url: str, book_id: str, character_id: str) -> Optional[str]:
    if not settings.portrait_cache_enabled:
        return None
    if not image_url:
        return None

    cache_dir = Path(settings.portrait_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:16]
    filename_base = f"{book_id}-{character_id}-{url_hash}"

    try:
        response = requests.get(image_url, stream=True, timeout=20)
    except requests.RequestException:
        return None

    if response.status_code >= 400:
        return None

    content_type = response.headers.get("content-type", "image/jpeg")
    suffix = _infer_extension(content_type)
    file_path = cache_dir / f"{filename_base}{suffix}"

    try:
        with file_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=262144):
                if chunk:
                    handle.write(chunk)
    except OSError:
        return None

    return f"/api/media/portraits/{file_path.name}"
