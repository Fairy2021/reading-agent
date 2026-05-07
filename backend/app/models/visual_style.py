import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VisualStyleProfile(Base):
    __tablename__ = "visual_style_profiles"
    __table_args__ = (UniqueConstraint("book_id", name="uq_visual_style_profile_book"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    style_name: Mapped[str] = mapped_column(String(64), default="ink-wash")
    palette: Mapped[str] = mapped_column(Text, default="rice paper, ink black, cinnabar accent")
    brush: Mapped[str] = mapped_column(Text, default="xieyi, soft brush, layered wash")
    mood: Mapped[str] = mapped_column(Text, default="classical, restrained, poetic")
    negative_prompt: Mapped[str] = mapped_column(
        Text,
        default="modern city, neon, sci-fi, 3D render, watermark, text artifacts",
    )
    locked: Mapped[str] = mapped_column(String(8), default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
