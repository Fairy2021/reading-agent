from __future__ import annotations

import hashlib
import math
import re

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


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """Deterministic local embedding for MVP.

    Why this exists:
    - Works on a personal laptop without external model service.
    - Keeps pgvector retrieval pipeline unblocked.
    - Can be replaced by real embedding API later with the same interface.
    """
    vector_dim = dim or settings.rag_embedding_dim
    vec = [0.0] * vector_dim

    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        idx = int.from_bytes(digest[:8], "big") % vector_dim
        sign = 1.0 if (digest[8] % 2 == 0) else -1.0
        weight = 1.0 + (digest[9] / 255.0) * 0.25
        vec[idx] += sign * weight

    return _normalize(vec)
