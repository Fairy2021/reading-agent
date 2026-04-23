from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Character, CharacterAlias, CharacterEvidence, CharacterState
from app.skills.base import SkillResult

HONORIFIC_SUFFIXES = (
    "儿",
    "姑娘",
    "姑奶奶",
    "公子",
    "夫人",
    "太太",
    "姨娘",
    "嫂子",
    "姐姐",
    "哥哥",
    "弟弟",
    "妹妹",
    "老爷",
    "太君",
    "老太太",
    "嬷嬷",
    "妈妈",
)
NOISE_NAMES = {"众人", "众人都", "便说", "不知", "因说", "因笑", "都笑", "便问", "大家", "有人"}
NOISE_SUFFIXES = {"说", "笑", "问", "答", "道", "叹", "想", "听", "看", "叫", "哭"}


def _canonical_candidates(name: str) -> list[str]:
    cands = [name]
    if name.endswith("儿") and len(name) >= 3:
        cands.append(name[:-1])
    for suf in HONORIFIC_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf) + 1:
            cands.append(name[: -len(suf)])
    if len(name) == 3:
        cands.append(name[1:])
    if len(name) >= 3 and name[-1] in NOISE_SUFFIXES:
        cands.append(name[:-1])
    return list(dict.fromkeys(cands))


def _is_probably_noise(name: str) -> bool:
    if not name:
        return True
    if name in NOISE_NAMES:
        return True
    if len(name) >= 3 and name[-1] in NOISE_SUFFIXES:
        return True
    return False


def _merge_character(source: Character, target: Character, db: Session) -> tuple[int, int]:
    alias_added = 0
    state_dropped = 0

    existing_aliases = {a.alias for a in target.aliases}
    if source.canonical_name not in existing_aliases:
        db.add(CharacterAlias(character_id=target.id, alias=source.canonical_name, source="normalization"))
        existing_aliases.add(source.canonical_name)
        alias_added += 1

    for alias in source.aliases:
        if alias.alias in existing_aliases:
            continue
        db.add(CharacterAlias(character_id=target.id, alias=alias.alias, source="normalization"))
        existing_aliases.add(alias.alias)
        alias_added += 1

    source_evidences = list(db.execute(select(CharacterEvidence).where(CharacterEvidence.character_id == source.id)).scalars())
    for ev in source_evidences:
        ev.character_id = target.id

    source_states = list(db.execute(select(CharacterState).where(CharacterState.character_id == source.id)).scalars())
    target_state_chapters = {
        st.chapter_index
        for st in db.execute(select(CharacterState).where(CharacterState.character_id == target.id)).scalars()
    }
    for st in source_states:
        if st.chapter_index in target_state_chapters:
            db.delete(st)
            state_dropped += 1
        else:
            st.character_id = target.id

    if target.card is None and source.card is not None:
        source.card.character_id = target.id

    target.mention_count += source.mention_count
    target.confidence = max(target.confidence, source.confidence)
    if source.first_chapter_index is not None:
        if target.first_chapter_index is None:
            target.first_chapter_index = source.first_chapter_index
        else:
            target.first_chapter_index = min(target.first_chapter_index, source.first_chapter_index)

    db.delete(source)
    return alias_added, state_dropped


class CharacterNormalizationSkill:
    name = "character_normalization_build"

    def run(self, db: Session, *, book_id: str, **_: object) -> SkillResult:
        if not settings.skill_character_alias_merge_enabled:
            return SkillResult(self.name, metrics={"merge_count": 0, "verified_count": 0}, message="alias merge disabled")

        characters = list(
            db.execute(
                select(Character)
                .where(Character.book_id == book_id)
                .options(selectinload(Character.aliases), selectinload(Character.card), selectinload(Character.states))
                .order_by(Character.mention_count.desc(), Character.canonical_name.asc())
            ).scalars()
        )
        if not characters:
            return SkillResult(self.name, status="failed", message="no characters")

        name_to_character = {c.canonical_name: c for c in characters}
        merge_pairs: list[tuple[Character, Character]] = []

        for source in characters:
            for cand in _canonical_candidates(source.canonical_name):
                target = name_to_character.get(cand)
                if not target:
                    continue
                if target.id == source.id:
                    continue
                if target.mention_count < source.mention_count:
                    continue
                merge_pairs.append((source, target))
                break

        merged_ids: set[str] = set()
        merge_count = 0
        alias_added = 0
        state_dropped = 0

        for source, target in merge_pairs:
            if source.id in merged_ids or target.id in merged_ids:
                continue
            if source.id == target.id:
                continue
            a_count, s_count = _merge_character(source, target, db)
            alias_added += a_count
            state_dropped += s_count
            merged_ids.add(source.id)
            merge_count += 1

        refreshed = list(db.execute(select(Character).where(Character.book_id == book_id)).scalars())
        verified_count = 0
        unverifed_count = 0
        for character in refreshed:
            if _is_probably_noise(character.canonical_name):
                character.is_verified = False
                character.confidence = min(character.confidence, 0.19)
                unverifed_count += 1
                continue
            character.is_verified = bool(
                character.confidence >= 0.2 and character.mention_count >= settings.skill_character_min_mentions
            )
            if character.is_verified:
                verified_count += 1
            else:
                unverifed_count += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "merge_count": merge_count,
                "alias_added": alias_added,
                "state_dropped": state_dropped,
                "verified_count": verified_count,
                "unverified_count": unverifed_count,
            },
        )

