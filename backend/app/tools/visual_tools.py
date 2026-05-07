from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, VisualStyleProfile


def ensure_visual_style_profile(db: Session, *, book_id: str) -> VisualStyleProfile:
    row = db.execute(
        select(VisualStyleProfile).where(VisualStyleProfile.book_id == book_id).limit(1)
    ).scalars().first()
    if row:
        return row
    row = VisualStyleProfile(book_id=book_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_visual_style_clause(profile: VisualStyleProfile) -> str:
    return (
        f"风格锁定[{profile.style_name}]；"
        f"色板[{profile.palette}]；"
        f"笔触[{profile.brush}]；"
        f"氛围[{profile.mood}]；"
        f"负向[{profile.negative_prompt}]。"
    )


def get_scene_evidence_snippets(
    db: Session,
    *,
    book_id: str,
    chapter_index: int | None,
    max_items: int = 3,
    max_chars_each: int = 140,
) -> list[str]:
    if not chapter_index:
        return []
    chapter = db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id, Chapter.chapter_index == chapter_index)
        .limit(1)
    ).scalars().first()
    if not chapter or not chapter.raw_text:
        return []
    lines = [line.strip() for line in chapter.raw_text.split("\n") if line.strip()]
    snippets: list[str] = []
    for line in lines:
        if len(line) < 12:
            continue
        snippets.append(line[:max_chars_each])
        if len(snippets) >= max_items:
            break
    return snippets
