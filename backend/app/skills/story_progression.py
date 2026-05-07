from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Chapter, StoryProgression
from app.skills.base import SkillResult


def _stage_for(chapter_index: int, max_chapter: int) -> str:
    if max_chapter <= 0:
        return "development"
    ratio = chapter_index / max_chapter
    if ratio <= 0.2:
        return "opening"
    if ratio <= 0.6:
        return "development"
    if ratio <= 0.85:
        return "climax"
    return "resolution"


class StoryProgressionSkill:
    name = "story_progression_build"

    def run(
        self,
        db: Session,
        *,
        book_id: str,
        max_chapter_index: int | None = None,
        **_: object,
    ) -> SkillResult:
        stmt = select(Chapter).where(Chapter.book_id == book_id)
        if max_chapter_index is not None:
            stmt = stmt.where(Chapter.chapter_index <= max_chapter_index)
        chapters = list(db.execute(stmt.order_by(Chapter.chapter_index.asc())).scalars())
        if not chapters:
            return SkillResult(self.name, metrics={"progression_count": 0})

        max_idx = max(c.chapter_index for c in chapters)
        db.execute(delete(StoryProgression).where(StoryProgression.book_id == book_id))
        db.flush()

        for chapter in chapters:
            snippet = (chapter.raw_text or "").replace("\n", " ").strip()[:220]
            db.add(
                StoryProgression(
                    book_id=book_id,
                    chapter_index=chapter.chapter_index,
                    chapter_title=chapter.title or "",
                    progression_stage=_stage_for(chapter.chapter_index, max_idx),
                    summary=snippet or (chapter.title or ""),
                )
            )
        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "progression_count": len(chapters),
                "max_chapter_index": max_idx,
            },
        )
