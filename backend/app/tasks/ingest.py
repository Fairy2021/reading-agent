from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Book, Chapter, ChapterChunk, CharacterPortrait
from app.services import embed_text, generate_character_portrait, split_text_to_chunks
from app.services.image_service import cache_remote_portrait
from app.skills import run_book_skill_pipeline, serialize_skill_results
from app.worker.celery_app import celery_app

CHAPTER_HEADING_PATTERN = re.compile(
    r"(?m)^(第[0-9〇零一二三四五六七八九十百千万两廿卅]+[回章节卷部][^\n]{0,40})\s*$"
)


def _read_text_with_fallback(file_path: Path) -> str:
    encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except Exception as exc:  # noqa: PERF203
            last_error = exc
            continue
    raise RuntimeError(f"Failed to decode file with known encodings: {last_error}")


def _split_by_chapter_headings(text: str) -> list[tuple[str, str]]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(CHAPTER_HEADING_PATTERN.finditer(cleaned))
    if len(matches) < 2:
        return []

    chapters: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        if body:
            chapters.append((title, body))
    return chapters


def _fallback_split(text: str, max_chars: int = 8000) -> list[tuple[str, str]]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if not paragraphs:
        return [("Chunk 1", cleaned[:max_chars])]

    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para) + 2
        if buffer and current_size + para_size > max_chars:
            chunk_idx = len(chunks) + 1
            chunks.append((f"Chunk {chunk_idx}", "\n\n".join(buffer)))
            buffer = [para]
            current_size = para_size
        else:
            buffer.append(para)
            current_size += para_size

    if buffer:
        chunk_idx = len(chunks) + 1
        chunks.append((f"Chunk {chunk_idx}", "\n\n".join(buffer)))
    return chunks


def _build_chapters(text: str) -> list[tuple[str, str]]:
    chapters = _split_by_chapter_headings(text)
    if chapters:
        return chapters
    return _fallback_split(text)


def _dispatch_portrait_generation_tasks(
    db,
    *,
    book_id: str,
    min_chapter_index: int,
    max_chapter_index: int,
) -> int:
    if not settings.portrait_generation_enabled:
        return 0

    stmt = select(CharacterPortrait.id).where(
        CharacterPortrait.book_id == book_id,
        CharacterPortrait.status == "queued",
        CharacterPortrait.unlocked_chapter_index >= min_chapter_index,
        CharacterPortrait.unlocked_chapter_index <= max_chapter_index,
    )
    portrait_ids = list(db.execute(stmt).scalars().all())
    for portrait_id in portrait_ids:
        generate_portrait_task.delay(portrait_id=portrait_id)
    return len(portrait_ids)


def _persist_book_content(book_id: str, chapters: Iterable[tuple[str, str]]) -> tuple[int, int]:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            raise ValueError("Book not found")
        book.skill_checkpoint_chapter = 0

        existing_chapter_ids = db.execute(
            select(Chapter.id).where(Chapter.book_id == book_id)
        ).scalars().all()
        if existing_chapter_ids:
            db.execute(delete(ChapterChunk).where(ChapterChunk.chapter_id.in_(existing_chapter_ids)))

        db.execute(delete(Chapter).where(Chapter.book_id == book_id))

        chapter_count = 0
        chunk_count = 0

        for chapter_index, (title, raw_text) in enumerate(chapters, start=1):
            chapter = Chapter(
                book_id=book_id,
                chapter_index=chapter_index,
                title=(title or f"Chapter {chapter_index}")[:255],
                raw_text=raw_text,
            )
            db.add(chapter)
            db.flush()
            chapter_count += 1

            chunks = split_text_to_chunks(raw_text)
            for chunk_index, content in enumerate(chunks, start=1):
                db.add(
                    ChapterChunk(
                        chapter_id=chapter.id,
                        chunk_index=chunk_index,
                        content=content,
                        embedding=embed_text(content),
                    )
                )
                chunk_count += 1

        book.status = "ready" if chapter_count > 0 else "failed"
        db.commit()
        return chapter_count, chunk_count
    except Exception:
        rollback_book = db.get(Book, book_id)
        if rollback_book:
            rollback_book.status = "failed"
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="books.ingest", queue="ingest")
def ingest_book_task(book_id: str, file_path: str | None = None) -> dict:
    if not file_path:
        return {"book_id": book_id, "status": "failed", "reason": "file_path is required"}

    source = Path(file_path)
    if not source.exists():
        return {"book_id": book_id, "status": "failed", "reason": "file does not exist"}

    text = _read_text_with_fallback(source)
    chapters = _build_chapters(text)
    chapter_count, chunk_count = _persist_book_content(book_id=book_id, chapters=chapters)
    skill_result = run_book_skills_task(
        book_id=book_id,
        max_chapter_index=chapter_count,
        incremental=settings.skill_default_incremental,
    )
    return {
        "book_id": book_id,
        "status": "ready",
        "chapter_count": chapter_count,
        "chunk_count": chunk_count,
        "skill_results": skill_result.get("skill_results", []),
    }


@celery_app.task(name="books.embed", queue="embed")
def build_embeddings_task(book_id: str) -> dict[str, str | int]:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return {"book_id": book_id, "status": "failed", "reason": "book not found"}

        chapters = db.execute(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
        ).scalars().all()
        if not chapters:
            return {"book_id": book_id, "status": "failed", "reason": "no chapters"}

        chunk_count = 0
        for chapter in chapters:
            db.execute(delete(ChapterChunk).where(ChapterChunk.chapter_id == chapter.id))
            chunks = split_text_to_chunks(chapter.raw_text)
            for chunk_index, content in enumerate(chunks, start=1):
                db.add(
                    ChapterChunk(
                        chapter_id=chapter.id,
                        chunk_index=chunk_index,
                        content=content,
                        embedding=embed_text(content),
                    )
                )
                chunk_count += 1
        db.commit()
        return {"book_id": book_id, "status": "embedded", "chunk_count": chunk_count}
    finally:
        db.close()


@celery_app.task(name="books.skills_pipeline", queue="ingest")
def run_book_skills_task(
    book_id: str,
    skill_names: list[str] | None = None,
    max_chapter_index: int | None = None,
    incremental: bool = True,
) -> dict:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return {"book_id": book_id, "status": "failed", "reason": "book not found"}

        max_available = db.execute(
            select(Chapter.chapter_index)
            .where(Chapter.book_id == book_id)
            .order_by(Chapter.chapter_index.desc())
            .limit(1)
        ).scalar_one_or_none()
        if max_available is None:
            return {"book_id": book_id, "status": "failed", "reason": "no chapters found"}

        target_max = min(max_chapter_index or int(max_available), int(max_available))
        if incremental:
            start_from = max(1, int(book.skill_checkpoint_chapter or 0) + 1)
        else:
            start_from = 1

        if start_from > target_max:
            return {
                "book_id": book_id,
                "status": "completed",
                "skill_results": [],
                "failed_count": 0,
                "portrait_tasks_enqueued": 0,
                "message": "no new chapter range",
                "range_min": start_from,
                "range_max": target_max,
                "checkpoint_chapter": int(book.skill_checkpoint_chapter or 0),
            }

        results = run_book_skill_pipeline(
            db,
            book_id=book_id,
            skill_names=skill_names,
            min_chapter_index=start_from,
            max_chapter_index=target_max,
            incremental=incremental,
        )
        serialized = serialize_skill_results(results)
        failed_count = sum(1 for r in serialized if r["status"] != "success")
        status = "completed_with_errors" if failed_count else "completed"
        if failed_count == 0:
            book.skill_checkpoint_chapter = max(int(book.skill_checkpoint_chapter or 0), target_max)
            db.commit()

        portrait_tasks_enqueued = _dispatch_portrait_generation_tasks(
            db,
            book_id=book_id,
            min_chapter_index=start_from,
            max_chapter_index=target_max,
        )
        return {
            "book_id": book_id,
            "status": status,
            "skill_results": serialized,
            "failed_count": failed_count,
            "portrait_tasks_enqueued": portrait_tasks_enqueued,
            "range_min": start_from,
            "range_max": target_max,
            "checkpoint_chapter": int(book.skill_checkpoint_chapter or 0),
        }
    finally:
        db.close()


@celery_app.task(name="books.generate_portrait", queue="image")
def generate_portrait_task(portrait_id: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        portrait = db.get(CharacterPortrait, portrait_id)
        if not portrait:
            return {"portrait_id": portrait_id, "status": "failed", "reason": "portrait not found"}

        if portrait.status == "ready" and portrait.image_url:
            return {
                "portrait_id": portrait_id,
                "book_id": portrait.book_id,
                "status": "skipped",
                "reason": "already ready",
            }

        portrait.status = "generating"
        portrait.generator = settings.portrait_generator_name
        db.commit()

        try:
            image_url, generator = generate_character_portrait(
                book_id=portrait.book_id,
                character_id=portrait.character_id,
                prompt=portrait.style_prompt,
            )
            cached_url = cache_remote_portrait(
                image_url=image_url,
                book_id=portrait.book_id,
                character_id=portrait.character_id,
            )
            if cached_url:
                image_url = cached_url
        except Exception as exc:  # noqa: PERF203
            portrait.status = "failed"
            portrait.generator = settings.portrait_generator_name
            db.commit()
            return {
                "portrait_id": portrait_id,
                "book_id": portrait.book_id,
                "status": "failed",
                "reason": str(exc),
            }

        portrait.image_url = image_url
        portrait.status = "ready"
        portrait.generator = generator
        db.commit()
        return {
            "portrait_id": portrait_id,
            "book_id": portrait.book_id,
            "status": "ready",
            "image_url": image_url,
        }
    finally:
        db.close()
