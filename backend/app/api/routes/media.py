from __future__ import annotations

from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings

router = APIRouter()


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are supported")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL host is required")


def _stream_remote_content(url: str) -> Iterator[bytes]:
    with requests.get(url, stream=True, timeout=20) as response:
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Upstream image request failed ({response.status_code})",
            )
        for chunk in response.iter_content(chunk_size=262144):
            if chunk:
                yield chunk


@router.get("/image_proxy")
def proxy_image(url: str = Query(..., min_length=4)) -> StreamingResponse:
    _validate_remote_url(url)
    response = requests.head(url, timeout=10, allow_redirects=True)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream image not reachable ({response.status_code})",
        )
    content_type = response.headers.get("content-type", "application/octet-stream")
    return StreamingResponse(_stream_remote_content(url), media_type=content_type)


@router.get("/media/portraits/{file_name}")
def get_cached_portrait(file_name: str) -> FileResponse:
    base_dir = Path(settings.portrait_cache_dir)
    target = (base_dir / file_name).resolve()
    if base_dir not in target.parents and target != base_dir:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(target)
