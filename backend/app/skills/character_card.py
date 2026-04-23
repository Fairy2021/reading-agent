from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Chapter, Character, CharacterCard, CharacterState
from app.services.llm_extract import extract_character_card_from_evidences
from app.skills.base import SkillResult

SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？\n]")

EMOTION_KEYWORDS = {
    "warm": ["安慰", "温柔", "体贴", "照顾"],
    "sensitive": ["落泪", "伤感", "委屈", "叹"],
    "intense": ["怒", "恨", "急", "争"],
    "calm": ["平静", "沉吟", "缓缓", "从容"],
}


def _infer_style_signals(excerpts: list[str]) -> dict[str, int]:
    scores = {k: 0 for k in EMOTION_KEYWORDS}
    text = " ".join(excerpts)
    for style, keys in EMOTION_KEYWORDS.items():
        for key in keys:
            scores[style] += text.count(key)
    return scores


def _fallback_card(
    *,
    character_name: str,
    mention_count: int,
    first_chapter: int | None,
    excerpts: list[str],
) -> dict[str, str]:
    style_scores = _infer_style_signals(excerpts)
    dominant_style = max(style_scores, key=style_scores.get) if style_scores else "calm"

    personality_map = {
        "warm": "整体语气偏温和，优先安抚对方情绪后再表达判断。",
        "sensitive": "情绪细腻敏感，对细节和关系变化反应明显。",
        "intense": "表达较直接，情绪推动力强，回应速度快。",
        "calm": "语气克制，偏理性和秩序感，先观察再表态。",
    }
    emotional_map = {
        "warm": "当前情绪偏温暖，倾向于关照他人。",
        "sensitive": "当前情绪偏敏感，容易被情境触动。",
        "intense": "当前情绪起伏较强，反应带有冲劲。",
        "calm": "当前情绪总体稳定，表达节奏平稳。",
    }
    return {
        "identity_summary": (
            f"{character_name} 在第 {first_chapter or '未知'} 章附近首次出现，"
            f"当前累计提及约 {mention_count} 次。"
        ),
        "personality_summary": personality_map.get(dominant_style, personality_map["calm"]),
        "speaking_style": "以角色身份说话，先共情再回应，并尽量引用章节证据。",
        "values_and_taboo": "价值观：保持人设一致。禁忌：不得越过读者进度剧透。",
        "emotional_state": emotional_map.get(dominant_style, emotional_map["calm"]),
        "stance": "基于当前章节已发生事件给出立场，不预设未来结局。",
        "current_goal": "围绕读者问题给出情节内回应，优先情感交流和陪伴。",
        "relation_snapshot": "关系判断以当前进度可见互动为准。",
    }


def _collect_window_evidence(
    *,
    character: Character,
    chapter_rows: list[Chapter],
    limit: int,
) -> tuple[list[str], int]:
    aliases = {character.canonical_name}
    aliases.update(alias.alias for alias in character.aliases if alias.alias)

    snippets: list[str] = []
    latest_seen = 0
    for chapter in chapter_rows:
        text = (chapter.raw_text or "").strip()
        if not text:
            continue
        if not any(alias in text for alias in aliases):
            continue

        latest_seen = max(latest_seen, chapter.chapter_index)
        for sentence in SENTENCE_SPLIT_PATTERN.split(text):
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue
            if any(alias in sentence for alias in aliases):
                snippets.append(sentence[:260])
            if len(snippets) >= limit:
                break
        if len(snippets) >= limit:
            break

    dedup = list(dict.fromkeys(snippets))
    return dedup[:limit], latest_seen


class CharacterCardSkill:
    name = "character_card_build"

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
        characters = list(
            db.execute(
                select(Character)
                .where(Character.book_id == book_id)
                .options(
                    selectinload(Character.evidences),
                    selectinload(Character.card),
                    selectinload(Character.aliases),
                )
                .order_by(Character.mention_count.desc(), Character.canonical_name.asc())
            ).scalars()
        )
        if not characters:
            return SkillResult(self.name, status="failed", message="no discovered characters")

        if not incremental:
            character_ids = [c.id for c in characters]
            if character_ids:
                db.execute(delete(CharacterCard).where(CharacterCard.character_id.in_(character_ids)))
                db.execute(delete(CharacterState).where(CharacterState.character_id.in_(character_ids)))
                db.flush()

        max_index = max_chapter_index if max_chapter_index is not None else 10**9
        chapter_rows = list(
            db.execute(
                select(Chapter)
                .where(
                    Chapter.book_id == book_id,
                    Chapter.chapter_index >= min_chapter_index,
                    Chapter.chapter_index <= max_index,
                )
                .order_by(Chapter.chapter_index.asc())
            ).scalars()
        )

        processed_count = 0
        llm_count = 0
        fallback_count = 0
        state_written = 0

        candidate_payloads: list[tuple[Character, list[str], int]] = []
        for character in characters:
            window_excerpts, latest_window_chapter = _collect_window_evidence(
                character=character,
                chapter_rows=chapter_rows,
                limit=settings.skill_evidence_per_character,
            )
            if incremental and not window_excerpts:
                # Incremental mode only updates characters mentioned in this chapter window.
                continue

            if window_excerpts:
                excerpts = window_excerpts
                latest_chapter = latest_window_chapter
            else:
                evidences_sorted = sorted(character.evidences, key=lambda x: x.chapter_index)
                scoped_evidences = [
                    ev
                    for ev in evidences_sorted
                    if max_chapter_index is None or ev.chapter_index <= max_chapter_index
                ]
                excerpts = [ev.excerpt for ev in scoped_evidences if ev.excerpt][
                    : settings.skill_evidence_per_character
                ]
                latest_chapter = max(
                    (ev.chapter_index for ev in scoped_evidences),
                    default=max_chapter_index or 0,
                )

            if not excerpts:
                continue
            candidate_payloads.append((character, excerpts, latest_chapter))

        if settings.skill_card_llm_max_characters_per_run > 0:
            candidate_payloads = candidate_payloads[: settings.skill_card_llm_max_characters_per_run]

        for character, excerpts, latest_chapter in candidate_payloads:
            max_chars = max(300, settings.skill_card_evidence_chars)
            evidence_bundle: list[str] = []
            current_len = 0
            for text in excerpts:
                snippet = text.strip()
                if not snippet:
                    continue
                if current_len + len(snippet) > max_chars and evidence_bundle:
                    break
                evidence_bundle.append(snippet)
                current_len += len(snippet)

            if settings.skill_card_llm_enabled:
                try:
                    card_payload = extract_character_card_from_evidences(
                        name=character.canonical_name,
                        evidence_list=evidence_bundle,
                        mention_count=character.mention_count,
                        first_chapter_index=character.first_chapter_index,
                    )
                    llm_count += 1
                except Exception:
                    card_payload = _fallback_card(
                        character_name=character.canonical_name,
                        mention_count=character.mention_count,
                        first_chapter=character.first_chapter_index,
                        excerpts=evidence_bundle,
                    )
                    fallback_count += 1
            else:
                card_payload = _fallback_card(
                    character_name=character.canonical_name,
                    mention_count=character.mention_count,
                    first_chapter=character.first_chapter_index,
                    excerpts=evidence_bundle,
                )
                fallback_count += 1

            if character.card:
                character.card.identity_summary = card_payload["identity_summary"]
                character.card.personality_summary = card_payload["personality_summary"]
                character.card.speaking_style = card_payload["speaking_style"]
                character.card.values_and_taboo = card_payload["values_and_taboo"]
            else:
                db.add(
                    CharacterCard(
                        character_id=character.id,
                        identity_summary=card_payload["identity_summary"],
                        personality_summary=card_payload["personality_summary"],
                        speaking_style=card_payload["speaking_style"],
                        values_and_taboo=card_payload["values_and_taboo"],
                    )
                )
            processed_count += 1

            if not character.is_verified or latest_chapter <= 0:
                continue

            source_summary = " | ".join(evidence_bundle[: settings.skill_state_recent_evidence])[:600]
            existing_state = db.execute(
                select(CharacterState)
                .where(
                    CharacterState.character_id == character.id,
                    CharacterState.chapter_index == latest_chapter,
                )
                .limit(1)
            ).scalars().first()

            if existing_state:
                existing_state.emotional_state = card_payload["emotional_state"]
                existing_state.stance = card_payload["stance"]
                existing_state.current_goal = card_payload["current_goal"]
                existing_state.relation_snapshot = card_payload["relation_snapshot"]
                existing_state.source_summary = source_summary
            else:
                db.add(
                    CharacterState(
                        character_id=character.id,
                        chapter_index=latest_chapter,
                        emotional_state=card_payload["emotional_state"],
                        stance=card_payload["stance"],
                        current_goal=card_payload["current_goal"],
                        relation_snapshot=card_payload["relation_snapshot"],
                        source_summary=source_summary,
                    )
                )
            state_written += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "card_count": processed_count,
                "state_count": state_written,
                "llm_count": llm_count,
                "fallback_count": fallback_count,
                "max_chapter_index": max_chapter_index or 0,
            },
        )
