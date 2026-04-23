from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Chapter, Character, RelationshipEdge
from app.services.llm_extract import extract_relationships_from_text
from app.skills.base import SkillResult

RELATION_MAP = {
    "亲属": "kinship",
    "家人": "kinship",
    "朋友": "friend",
    "友人": "friend",
    "对立": "conflict",
    "冲突": "conflict",
    "仇": "conflict",
    "主仆": "master_servant",
    "主从": "master_servant",
    "情感": "romance",
    "爱情": "romance",
    "同盟": "alliance",
    "合作": "alliance",
    "其他": "other",
}


def _normalize_relation_type(label: str) -> str:
    text = (label or "").strip()
    if not text:
        return "other"
    for k, v in RELATION_MAP.items():
        if k in text:
            return v
    return "other"


def _chapter_segments(text: str, *, segment_len: int, max_segments: int) -> list[str]:
    if len(text) <= segment_len:
        return [text]
    segments: list[str] = []
    if len(text) <= segment_len * max_segments:
        for i in range(0, len(text), segment_len):
            segments.append(text[i : i + segment_len])
            if len(segments) >= max_segments:
                break
        return segments
    starts = [0, max(0, len(text) // 2 - segment_len // 2), max(0, len(text) - segment_len)]
    used = set()
    for start in starts:
        if start in used:
            continue
        used.add(start)
        segments.append(text[start : start + segment_len])
        if len(segments) >= max_segments:
            break
    return segments


def _fallback_cooccurrence(
    text: str,
    *,
    alias_to_character: dict[str, Character],
) -> list[tuple[Character, Character, str, int, str]]:
    present_ids: set[str] = set()
    id_to_character: dict[str, Character] = {}
    for alias, character in alias_to_character.items():
        if alias and alias in text:
            present_ids.add(character.id)
            id_to_character[character.id] = character

    chars = [id_to_character[cid] for cid in sorted(present_ids)]
    pairs: list[tuple[Character, Character, str, int, str]] = []
    for left, right in combinations(chars, 2):
        pairs.append((left, right, "co_occurrence", 2, "同章节共现"))
    return pairs


class RelationshipStateSkill:
    name = "relationship_state_build"

    def run(
        self,
        db: Session,
        *,
        book_id: str,
        max_chapter_index: int | None = None,
        **_: object,
    ) -> SkillResult:
        characters = list(
            db.execute(
                select(Character)
                .where(Character.book_id == book_id, Character.is_verified.is_(True))
                .options(selectinload(Character.aliases))
                .order_by(Character.canonical_name.asc())
            ).scalars()
        )
        if len(characters) < 2:
            db.execute(delete(RelationshipEdge).where(RelationshipEdge.book_id == book_id))
            db.commit()
            return SkillResult(self.name, metrics={"edge_count": 0})

        alias_to_character: dict[str, Character] = {}
        for character in characters:
            alias_to_character[character.canonical_name] = character
            for alias in character.aliases:
                alias_to_character[alias.alias] = character

        chapter_stmt = select(Chapter).where(Chapter.book_id == book_id)
        if max_chapter_index is not None:
            chapter_stmt = chapter_stmt.where(Chapter.chapter_index <= max_chapter_index)
        chapters = list(db.execute(chapter_stmt.order_by(Chapter.chapter_index.asc())).scalars())

        relation_stats: dict[tuple[str, str, str], dict[str, int | str | None]] = defaultdict(
            lambda: {"count": 0, "strength_sum": 0, "first": None, "last": None, "evidence": ""}
        )
        llm_success_chapters = 0
        llm_failed_chapters = 0
        fallback_edges = 0

        for chapter in chapters:
            text = chapter.raw_text or ""
            if not text:
                continue

            extracted: list[tuple[Character, Character, str, int, str]] = []
            llm_ok = False
            for segment in _chapter_segments(
                text,
                segment_len=settings.skill_relationship_llm_segment_len,
                max_segments=settings.skill_relationship_llm_max_segments,
            ):
                try:
                    rows = extract_relationships_from_text(segment)
                    for row in rows:
                        source_name = str(row.get("source", "")).strip()
                        target_name = str(row.get("target", "")).strip()
                        source = alias_to_character.get(source_name)
                        target = alias_to_character.get(target_name)
                        if not source or not target:
                            continue
                        if source.id == target.id:
                            continue
                        relation_type = _normalize_relation_type(str(row.get("relation_type", "")))
                        strength = int(row.get("strength", 3))
                        strength = max(1, min(5, strength))
                        evidence = str(row.get("evidence", "") or "")
                        extracted.append((source, target, relation_type, strength, evidence))
                    llm_ok = True
                except Exception:
                    continue

            if llm_ok:
                llm_success_chapters += 1
            else:
                llm_failed_chapters += 1
                if settings.skill_relationship_fallback_enabled:
                    fallback = _fallback_cooccurrence(text, alias_to_character=alias_to_character)
                    extracted.extend(fallback)
                    fallback_edges += len(fallback)

            for source, target, relation_type, strength, evidence in extracted:
                key = (source.id, target.id, relation_type)
                stat = relation_stats[key]
                stat["count"] = int(stat["count"]) + 1
                stat["strength_sum"] = int(stat["strength_sum"]) + strength
                if stat["first"] is None:
                    stat["first"] = chapter.chapter_index
                stat["last"] = chapter.chapter_index
                if not stat["evidence"] and evidence:
                    stat["evidence"] = evidence[:240]

        db.execute(delete(RelationshipEdge).where(RelationshipEdge.book_id == book_id))
        db.flush()

        edge_count = 0
        min_count = settings.skill_relationship_min_cooccurrence
        for (source_id, target_id, relation_type), stat in relation_stats.items():
            count = int(stat["count"])
            if count < min_count:
                continue
            avg_strength = int(round(int(stat["strength_sum"]) / max(count, 1)))
            strength = round(min(1.0, max(0.1, avg_strength / 5.0)), 4)
            db.add(
                RelationshipEdge(
                    book_id=book_id,
                    source_character_id=source_id,
                    target_character_id=target_id,
                    relation_type=relation_type,
                    strength=strength,
                    first_chapter_index=int(stat["first"]) if stat["first"] is not None else None,
                    last_chapter_index=int(stat["last"]) if stat["last"] is not None else None,
                    evidence_excerpt=str(stat["evidence"] or ""),
                )
            )
            edge_count += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "edge_count": edge_count,
                "min_cooccurrence": min_count,
                "max_chapter_index": max_chapter_index or 0,
                "llm_success_chapters": llm_success_chapters,
                "llm_failed_chapters": llm_failed_chapters,
                "fallback_edges": fallback_edges,
            },
        )

