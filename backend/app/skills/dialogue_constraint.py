from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DialogueConstraint, StoryProgression
from app.skills.base import SkillResult


class DialogueConstraintSkill:
    name = "dialogue_constraint_build"

    def run(
        self,
        db: Session,
        *,
        book_id: str,
        max_chapter_index: int | None = None,
        **_: object,
    ) -> SkillResult:
        stmt = select(StoryProgression).where(StoryProgression.book_id == book_id)
        if max_chapter_index is not None:
            stmt = stmt.where(StoryProgression.chapter_index <= max_chapter_index)
        progressions = list(db.execute(stmt.order_by(StoryProgression.chapter_index.asc())).scalars())
        if not progressions:
            return SkillResult(self.name, metrics={"constraint_count": 0})

        db.execute(delete(DialogueConstraint).where(DialogueConstraint.book_id == book_id))
        db.flush()

        for p in progressions:
            allowed_scope = f"仅允许引用第1章至第{p.chapter_index}章的已发生剧情。"
            blocked_topics = f"禁止剧透第{p.chapter_index + 1}章及之后剧情。"
            policy = (
                "保持角色口吻；证据不足时明确说明不确定；"
                "避免捏造未出现人物关系。"
            )
            db.add(
                DialogueConstraint(
                    book_id=book_id,
                    chapter_index=p.chapter_index,
                    allowed_scope=allowed_scope,
                    blocked_topics=blocked_topics,
                    roleplay_policy=policy,
                )
            )
        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "constraint_count": len(progressions),
                "max_chapter_index": progressions[-1].chapter_index,
            },
        )
