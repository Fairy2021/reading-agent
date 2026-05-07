import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("book_id", "character_id", "asset_type", "version", name="uq_media_asset_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    asset_type: Mapped[str] = mapped_column(String(32), default="portrait", index=True)
    chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    style_prompt: Mapped[str] = mapped_column(Text, default="")
    storage_url: Mapped[str] = mapped_column(Text, default="")
    generator: Mapped[str] = mapped_column(String(64), default="pending")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_agent: Mapped[str] = mapped_column(String(64), default="visual-agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AssetJob(Base):
    __tablename__ = "asset_jobs"
    __table_args__ = (
        UniqueConstraint("book_id", "idempotency_key", name="uq_asset_job_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    asset_type: Mapped[str] = mapped_column(String(32), default="portrait", index=True)
    chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    style_prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    task_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    result_asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
