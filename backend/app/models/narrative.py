import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoryProgression(Base):
    __tablename__ = "story_progressions"
    __table_args__ = (UniqueConstraint("book_id", "chapter_index", name="uq_story_progression_chapter"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chapter_title: Mapped[str] = mapped_column(String(255), default="")
    progression_stage: Mapped[str] = mapped_column(String(64), default="development")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class DialogueConstraint(Base):
    __tablename__ = "dialogue_constraints"
    __table_args__ = (UniqueConstraint("book_id", "chapter_index", name="uq_dialogue_constraint_chapter"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    allowed_scope: Mapped[str] = mapped_column(Text, default="")
    blocked_topics: Mapped[str] = mapped_column(Text, default="")
    roleplay_policy: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
