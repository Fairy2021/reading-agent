from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import requests

from app.core.config import settings

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens = [m.group(0) for m in TOKEN_PATTERN.finditer(lowered)]
    return [tok for tok in tokens if tok]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _fit_dim(vec: list[float], dim: int) -> list[float]:
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


def _resolve_embeddings_url() -> str:
    base = (settings.embedding_api_base_url or settings.openai_base_url or "").strip()
    if not base:
        return ""
    if base.endswith("/embeddings"):
        return base
    return f"{base.rstrip('/')}/embeddings"


def _extract_embedding_vector(payload: dict[str, Any]) -> list[float]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError("invalid embeddings response")
    first = data[0]
    if not isinstance(first, dict):
        raise RuntimeError("invalid embeddings response item")
    embedding = first.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("missing embedding vector")
    return [float(v) for v in embedding]


def _remote_embed_text(text: str, *, dim: int) -> list[float]:
    api_url = _resolve_embeddings_url()
    api_key = (settings.embedding_api_key or settings.openai_api_key or "").strip()
    model = (settings.embedding_model or settings.openai_embedding_model or "").strip()
    if not api_url:
        raise RuntimeError("EMBEDDING_API_BASE_URL is empty")
    if not api_key:
        raise RuntimeError("EMBEDDING_API_KEY is empty")
    if not model:
        raise RuntimeError("EMBEDDING_MODEL is empty")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }
    payload: dict[str, Any] = {
        "model": model,
        "input": text,
        "encoding_format": "float",
    }
    # Some providers support dimension control for OpenAI-compatible embeddings.
    if dim > 0:
        payload["dimensions"] = dim

    session = requests.Session()
    session.trust_env = False
    def _post(json_payload: dict[str, Any]) -> dict[str, Any]:
        response = session.post(
            api_url,
            headers=headers,
            json=json_payload,
            timeout=settings.embedding_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    try:
        data = _post(payload)
    except Exception:
        payload.pop("dimensions", None)
        data = _post(payload)
    vec = _extract_embedding_vector(data)
    return _fit_dim(vec, dim)


def _local_embed_text(text: str, dim: int) -> list[float]:
    """Deterministic local embedding for MVP fallback."""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        idx = int.from_bytes(digest[:8], "big") % dim
        sign = 1.0 if (digest[8] % 2 == 0) else -1.0
        weight = 1.0 + (digest[9] / 255.0) * 0.25
        vec[idx] += sign * weight

    return _normalize(vec)


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """Embed text into a vector.

    Modes:
    - local: deterministic hash embedding for offline/dev fallback.
    - remote: OpenAI-compatible embedding endpoint, suitable for Chinese-friendly models.
    """
    vector_dim = dim or settings.rag_embedding_dim
    request_dim = settings.embedding_dimensions or vector_dim
    provider = (settings.embedding_provider or "local").strip().lower()

    if provider == "remote":
        remote_vec = _remote_embed_text(text, dim=request_dim)
        return _fit_dim(remote_vec, vector_dim)
    return _local_embed_text(text, vector_dim)
