from __future__ import annotations

from app.core.config import settings


def split_text_to_chunks(
    text: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split long chapter text into retrieval chunks.

    Strategy:
    - Prefer paragraph boundaries first.
    - Keep chunk length around `chunk_size`.
    - Add light overlap to preserve cross-paragraph continuity.
    """
    target = chunk_size or settings.rag_chunk_size
    keep_overlap = overlap if overlap is not None else settings.rag_chunk_overlap

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    chunks: list[str] = []
    buffer: list[str] = []
    current_len = 0

    def flush_buffer() -> None:
        nonlocal buffer, current_len
        if not buffer:
            return
        merged = "\n\n".join(buffer).strip()
        if merged:
            chunks.append(merged)
        buffer = []
        current_len = 0

    for para in paragraphs:
        para_len = len(para)

        if para_len >= target * 2:
            flush_buffer()
            start = 0
            step = max(1, target - keep_overlap)
            while start < para_len:
                chunk = para[start : start + target].strip()
                if chunk:
                    chunks.append(chunk)
                start += step
            continue

        if buffer and current_len + para_len + 2 > target:
            flush_buffer()

        buffer.append(para)
        current_len += para_len + 2

    flush_buffer()
    return chunks
