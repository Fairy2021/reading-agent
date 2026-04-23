from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Chapter, Character, CharacterAlias, CharacterEvidence
from app.services.llm_extract import extract_characters_from_text
from app.skills.base import SkillResult

SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？\n]")
HINT_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,4}(?=说道|笑道|问道|答道|叹道|想道|便道|道)")
NAME_ALLOWED_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,8}$")
PUNCTUATION_PATTERN = re.compile(r"[：:\s()（）“”\"'·、，,。！？!？；;《》<>【】\[\]]")

STOPWORDS = {
    "众人",
    "众人都",
    "便说",
    "不知",
    "因说",
    "因笑",
    "都笑",
    "便问",
    "看官",
    "有人",
    "此人",
    "那人",
    "我们",
    "你们",
    "他们",
    "自己",
    "大家",
}

NOISE_SUFFIXES = {"笑", "说", "道", "问", "答", "叹", "想", "听", "看", "叫", "哭"}


@dataclass
class _CharacterAccumulator:
    canonical_name: str
    aliases: set[str] = field(default_factory=set)
    mention_count: int = 0
    first_chapter_index: int | None = None
    evidences: list[tuple[int, str, str]] = field(default_factory=list)


def _compute_confidence(*, mention_count: int, max_mention_count: int, alias_count: int) -> float:
    if max_mention_count <= 0:
        return 0.1
    mention_score = math.log1p(mention_count) / math.log1p(max_mention_count)
    alias_bonus = min(0.08, max(0.0, (alias_count - 1) * 0.02))
    value = 0.1 + 0.82 * mention_score + alias_bonus
    return round(max(0.05, min(0.99, value)), 4)


def _normalize_name(name: str) -> str:
    return PUNCTUATION_PATTERN.sub("", name).strip()


def _is_valid_name(name: str) -> bool:
    if not name:
        return False
    if name in STOPWORDS:
        return False
    if name.startswith("第") and ("章" in name or "回" in name):
        return False
    if not NAME_ALLOWED_PATTERN.match(name):
        return False
    if len(name) >= 3 and name[-1] in NOISE_SUFFIXES:
        return False
    return True


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
    seen = set()
    for start in starts:
        if start in seen:
            continue
        seen.add(start)
        segments.append(text[start : start + segment_len])
        if len(segments) >= max_segments:
            break
    return segments


def _sentence_evidences(text: str, aliases: set[str], limit: int) -> list[str]:
    snippets: list[str] = []
    for sentence in SENTENCE_SPLIT_PATTERN.split(text):
        sentence = sentence.strip()
        if len(sentence) < 8:
            continue
        if any(alias in sentence for alias in aliases):
            snippets.append(sentence[:260])
        if len(snippets) >= limit:
            break
    return snippets


def _fallback_name_candidates(text: str) -> list[dict[str, str | list[str]]]:
    results: list[dict[str, str | list[str]]] = []
    for m in HINT_PATTERN.finditer(text):
        name = _normalize_name(m.group(0))
        if _is_valid_name(name):
            results.append({"name": name, "aliases": [name], "evidence": ""})
    return results


def _count_mentions(text: str, aliases: set[str]) -> int:
    counts = [text.count(alias) for alias in aliases if alias]
    if not counts:
        return 0
    return max(counts)


def _dedupe_evidences(evidences: list[tuple[int, str, str]], limit: int) -> list[tuple[int, str, str]]:
    uniq: list[tuple[int, str, str]] = []
    seen = set()
    for ev in sorted(evidences, key=lambda x: (x[0], x[2])):
        key = (ev[0], ev[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ev)
        if len(uniq) >= limit:
            break
    return uniq


def _load_existing_accumulators(
    db: Session,
    *,
    book_id: str,
) -> tuple[dict[str, _CharacterAccumulator], dict[str, str]]:
    by_canonical: dict[str, _CharacterAccumulator] = {}
    alias_to_canonical: dict[str, str] = {}

    characters = list(
        db.execute(
            select(Character)
            .where(Character.book_id == book_id)
            .options(selectinload(Character.aliases), selectinload(Character.evidences))
        ).scalars()
    )
    for character in characters:
        acc = _CharacterAccumulator(
            canonical_name=character.canonical_name,
            mention_count=character.mention_count or 0,
            first_chapter_index=character.first_chapter_index,
            evidences=[
                (ev.chapter_index, ev.chapter_id, ev.excerpt)
                for ev in sorted(character.evidences, key=lambda x: x.chapter_index)[
                    : settings.skill_evidence_per_character
                ]
                if ev.excerpt
            ],
        )
        acc.aliases.add(character.canonical_name)
        for alias in character.aliases:
            if _is_valid_name(alias.alias):
                acc.aliases.add(alias.alias)
        by_canonical[acc.canonical_name] = acc

        for alias in acc.aliases:
            alias_to_canonical[alias] = acc.canonical_name

    return by_canonical, alias_to_canonical


class CharacterDiscoverySkill:
    name = "character_discovery"

    def run(
        self,
        db: Session,
        *,
        book_id: str,
        min_chapter_index: int = 1,
        max_chapter_index: int | None = None,
        incremental: bool = True,
        **_: object,
    ) -> SkillResult:
        max_available = db.execute(
            select(Chapter.chapter_index)
            .where(Chapter.book_id == book_id)
            .order_by(Chapter.chapter_index.desc())
            .limit(1)
        ).scalar_one_or_none()
        if max_available is None:
            return SkillResult(self.name, status="failed", message="no chapters found")

        target_max = min(max_chapter_index or int(max_available), int(max_available))
        target_min = max(1, min_chapter_index)
        if target_min > target_max:
            return SkillResult(
                self.name,
                metrics={
                    "character_count": 0,
                    "evidence_count": 0,
                    "processed_chapters": 0,
                },
                message="no new chapter range",
            )

        chapters = list(
            db.execute(
                select(Chapter)
                .where(
                    Chapter.book_id == book_id,
                    Chapter.chapter_index >= target_min,
                    Chapter.chapter_index <= target_max,
                )
                .order_by(Chapter.chapter_index.asc())
            ).scalars()
        )
        if not chapters:
            return SkillResult(self.name, status="failed", message="no chapters in range")

        if incremental:
            by_canonical, alias_to_canonical = _load_existing_accumulators(db, book_id=book_id)
        else:
            by_canonical = {}
            alias_to_canonical = {}

        llm_success_chapters = 0
        llm_failed_chapters = 0
        fallback_used_chapters = 0

        for chapter in chapters:
            text = (chapter.raw_text or "").strip()
            if not text:
                continue

            extracted_items: list[dict[str, str | list[str]]] = []
            llm_ok = False
            segments = _chapter_segments(
                text,
                segment_len=settings.skill_character_llm_segment_len,
                max_segments=settings.skill_character_llm_max_segments,
            )
            for segment in segments:
                try:
                    extracted = extract_characters_from_text(segment)
                    extracted_items.extend(extracted)
                    llm_ok = True
                except Exception:
                    continue

            if llm_ok:
                llm_success_chapters += 1
            else:
                llm_failed_chapters += 1
                if settings.skill_character_fallback_enabled:
                    fallback_used_chapters += 1
                    extracted_items = _fallback_name_candidates(text)

            chapter_touched: set[str] = set()
            for item in extracted_items:
                raw_name = item.get("name")
                raw_aliases = item.get("aliases", [])
                raw_evidence = item.get("evidence", "")

                if not isinstance(raw_name, str):
                    continue
                name = _normalize_name(raw_name)
                if not _is_valid_name(name):
                    continue

                aliases = {name}
                if isinstance(raw_aliases, list):
                    for alias in raw_aliases:
                        if not isinstance(alias, str):
                            continue
                        alias_norm = _normalize_name(alias)
                        if _is_valid_name(alias_norm):
                            aliases.add(alias_norm)

                matched = sorted({alias_to_canonical[a] for a in aliases if a in alias_to_canonical})
                canonical = matched[0] if matched else name
                acc = by_canonical.setdefault(canonical, _CharacterAccumulator(canonical_name=canonical))

                if acc.first_chapter_index is None:
                    acc.first_chapter_index = chapter.chapter_index
                else:
                    acc.first_chapter_index = min(acc.first_chapter_index, chapter.chapter_index)

                acc.aliases.update(aliases)
                for alias in aliases:
                    alias_to_canonical[alias] = canonical

                if isinstance(raw_evidence, str):
                    excerpt = raw_evidence.strip()[:260]
                    if excerpt:
                        acc.evidences.append((chapter.chapter_index, chapter.id, excerpt))

                chapter_touched.add(canonical)

            for canonical in chapter_touched:
                acc = by_canonical.get(canonical)
                if acc is None:
                    continue
                mention = _count_mentions(text, acc.aliases)
                acc.mention_count += max(1, mention)
                snippets = _sentence_evidences(text, acc.aliases, settings.skill_evidence_per_character)
                for snippet in snippets:
                    acc.evidences.append((chapter.chapter_index, chapter.id, snippet))

        threshold = settings.skill_character_min_mentions
        ranked_candidates = sorted(
            (acc for acc in by_canonical.values() if acc.mention_count >= threshold and _is_valid_name(acc.canonical_name)),
            key=lambda x: (-x.mention_count, x.first_chapter_index or 10**9, x.canonical_name),
        )[: settings.skill_character_max_count]
        keep_names = {acc.canonical_name for acc in ranked_candidates}

        existing_characters = {
            c.canonical_name: c
            for c in db.execute(
                select(Character)
                .where(Character.book_id == book_id)
                .options(selectinload(Character.aliases), selectinload(Character.evidences))
            ).scalars()
        }

        if not incremental:
            for existing in existing_characters.values():
                db.delete(existing)
            db.flush()
            existing_characters = {}
        else:
            for name, existing in existing_characters.items():
                if name not in keep_names:
                    existing.is_verified = False

        created_count = 0
        updated_count = 0
        evidence_count = 0
        max_mention = max((acc.mention_count for acc in ranked_candidates), default=0)

        for acc in ranked_candidates:
            acc.evidences = _dedupe_evidences(acc.evidences, settings.skill_evidence_per_character)
            confidence = _compute_confidence(
                mention_count=acc.mention_count,
                max_mention_count=max_mention,
                alias_count=len(acc.aliases),
            )
            is_verified = _is_valid_name(acc.canonical_name) and confidence >= 0.2

            character = existing_characters.get(acc.canonical_name)
            if character is None:
                character = Character(
                    book_id=book_id,
                    canonical_name=acc.canonical_name,
                    first_chapter_index=acc.first_chapter_index,
                    mention_count=acc.mention_count,
                    confidence=confidence,
                    is_verified=is_verified,
                )
                db.add(character)
                db.flush()
                created_count += 1
            else:
                character.first_chapter_index = acc.first_chapter_index
                character.mention_count = acc.mention_count
                character.confidence = confidence
                character.is_verified = is_verified
                updated_count += 1

            existing_aliases = {a.alias for a in character.aliases}
            alias_candidates = sorted(a for a in acc.aliases if _is_valid_name(a))
            if character.canonical_name not in alias_candidates:
                alias_candidates.insert(0, character.canonical_name)
            for alias in alias_candidates[:20]:
                if alias in existing_aliases:
                    continue
                db.add(CharacterAlias(character_id=character.id, alias=alias, source="llm_discovery"))

            existing_evidence_keys = {(e.chapter_index, e.excerpt) for e in character.evidences}
            for chapter_idx, chapter_id, excerpt in acc.evidences:
                key = (chapter_idx, excerpt)
                if key in existing_evidence_keys:
                    continue
                db.add(
                    CharacterEvidence(
                        character_id=character.id,
                        chapter_id=chapter_id,
                        chapter_index=chapter_idx,
                        evidence_type="mention",
                        excerpt=excerpt,
                    )
                )
                existing_evidence_keys.add(key)
                evidence_count += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "character_count": len(ranked_candidates),
                "created_count": created_count,
                "updated_count": updated_count,
                "evidence_count": evidence_count,
                "processed_chapters": len(chapters),
                "range_min": target_min,
                "range_max": target_max,
                "llm_success_chapters": llm_success_chapters,
                "llm_failed_chapters": llm_failed_chapters,
                "fallback_used_chapters": fallback_used_chapters,
            },
        )

