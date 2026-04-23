from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Chapter, ChapterChunk
from app.services.embedding import embed_text


@dataclass
class Evidence:
    chapter_index: int
    chapter_title: str
    chunk_id: str
    chunk_index: int
    content: str
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def get_book_max_chapter_index(db: Session, book_id: str) -> int:
    stmt = select(func.max(Chapter.chapter_index)).where(Chapter.book_id == book_id)
    max_index = db.execute(stmt).scalar_one_or_none()
    return int(max_index or 0)


def _base_evidence_stmt(book_id: str, max_chapter_index: int) -> Select:
    return (
        select(ChapterChunk, Chapter.chapter_index, Chapter.title)
        .join(Chapter, Chapter.id == ChapterChunk.chapter_id)
        .where(
            Chapter.book_id == book_id,
            Chapter.chapter_index <= max_chapter_index,
            ChapterChunk.embedding.is_not(None),
        )
    )


def retrieve_story_evidence(
    db: Session,
    *,
    book_id: str,
    query: str,
    max_chapter_index: int,
    top_k: int | None = None,
) -> list[Evidence]:
    top_n = top_k or settings.rag_top_k
    if max_chapter_index <= 0:
        return []

    query_embedding = embed_text(query)
    distance_expr = ChapterChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        _base_evidence_stmt(book_id=book_id, max_chapter_index=max_chapter_index)
        .add_columns(distance_expr.label("distance"))
        .order_by(distance_expr.asc())
        .limit(top_n)
    )
    rows = db.execute(stmt).all()

    evidences: list[Evidence] = []
    for chunk, chapter_index, chapter_title, distance in rows:
        score = 1.0 - float(distance or 0.0)
        evidences.append(
            Evidence(
                chapter_index=int(chapter_index),
                chapter_title=chapter_title or "",
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=max(0.0, min(1.0, score)),
            )
        )
    return evidences
