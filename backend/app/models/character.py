import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("book_id", "canonical_name", name="uq_character_book_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    first_chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    aliases: Mapped[list["CharacterAlias"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
    card: Mapped["CharacterCard | None"] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evidences: Mapped[list["CharacterEvidence"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
    states: Mapped[list["CharacterState"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
    graph_metric: Mapped["RelationshipGraphNodeMetric | None"] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        uselist=False,
    )
    portrait: Mapped["CharacterPortrait | None"] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CharacterAlias(Base):
    __tablename__ = "character_aliases"
    __table_args__ = (UniqueConstraint("character_id", "alias", name="uq_character_alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    character: Mapped[Character] = relationship(back_populates="aliases")


class CharacterCard(Base):
    __tablename__ = "character_cards"
    __table_args__ = (UniqueConstraint("character_id", name="uq_character_card_character"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    identity_summary: Mapped[str] = mapped_column(Text, default="")
    personality_summary: Mapped[str] = mapped_column(Text, default="")
    speaking_style: Mapped[str] = mapped_column(Text, default="")
    values_and_taboo: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    character: Mapped[Character] = relationship(back_populates="card")


class CharacterEvidence(Base):
    __tablename__ = "character_evidences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    chapter_id: Mapped[str] = mapped_column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), default="mention")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    character: Mapped[Character] = relationship(back_populates="evidences")


class RelationshipEdge(Base):
    __tablename__ = "relationship_edges"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "source_character_id",
            "target_character_id",
            "relation_type",
            name="uq_relationship_edge",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    source_character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    target_character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(64), default="co_occurrence")
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    first_chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class CharacterState(Base):
    __tablename__ = "character_states"
    __table_args__ = (
        UniqueConstraint("character_id", "chapter_index", name="uq_character_state_chapter"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    emotional_state: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(Text, default="")
    current_goal: Mapped[str] = mapped_column(Text, default="")
    relation_snapshot: Mapped[str] = mapped_column(Text, default="")
    source_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    character: Mapped[Character] = relationship(back_populates="states")


class RelationshipGraphNodeMetric(Base):
    __tablename__ = "relationship_graph_node_metrics"
    __table_args__ = (
        UniqueConstraint("book_id", "character_id", name="uq_graph_node_metric_book_character"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    degree: Mapped[int] = mapped_column(Integer, default=0)
    in_degree: Mapped[int] = mapped_column(Integer, default=0)
    out_degree: Mapped[int] = mapped_column(Integer, default=0)
    weighted_degree: Mapped[float] = mapped_column(Float, default=0.0)
    relation_diversity: Mapped[int] = mapped_column(Integer, default=0)
    last_chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    character: Mapped[Character] = relationship(back_populates="graph_metric")


class CharacterPortrait(Base):
    __tablename__ = "character_portraits"
    __table_args__ = (
        UniqueConstraint("book_id", "character_id", name="uq_character_portrait_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    unlocked_chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    style_prompt: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    generator: Mapped[str] = mapped_column(String(64), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    character: Mapped[Character] = relationship(back_populates="portrait")


class SessionMemory(Base):
    __tablename__ = "session_memories"
    __table_args__ = (
        UniqueConstraint("book_id", "session_id", "role_name", name="uq_session_memory_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    emotion_tag: Mapped[str] = mapped_column(String(64), default="neutral")
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    last_user_message: Mapped[str] = mapped_column(Text, default="")
    last_assistant_message: Mapped[str] = mapped_column(Text, default="")
    last_chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
