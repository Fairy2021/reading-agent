from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Character, CharacterAlias, CharacterEvidence, CharacterState
from app.services.character_name_filter import is_noise_like_character_name
from app.services.llm_extract import verify_character_candidates
from app.skills.base import SkillResult

SPEECH_SUFFIXES = {"说", "笑", "问", "答", "道", "叹", "想", "听", "看", "叫", "哭"}
HONORIFIC_SUFFIXES = (
    "儿",
    "姑娘",
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
EXACT_NOISE_NAMES = {
    "众人",
    "众人都",
    "大家",
    "有人",
    "那人",
    "此人",
    "我们",
    "你们",
    "他们",
    "自己",
    "便说",
    "因说",
    "因笑",
    "都笑",
    "便问",
    "不知",
}
NARRATIVE_FRAGMENT_PATTERN = re.compile(r"^(便|因|都|又|只|且|遂|方|忽|仍|还).{0,1}(说|笑|问|答|道)$")


def _is_noise_like(name: str) -> bool:
    if is_noise_like_character_name(name):
        return True
    if not name:
        return True
    if name in EXACT_NOISE_NAMES:
        return True
    if NARRATIVE_FRAGMENT_PATTERN.match(name):
        return True
    if name.startswith("第") and ("章" in name or "回" in name):
        return True
    if len(name) >= 3 and name[-1] in SPEECH_SUFFIXES:
        return True
    if name.endswith("们") and len(name) <= 3:
        return True
    return False


def _strip_speech_suffix(name: str) -> str:
    if len(name) >= 3 and name[-1] in SPEECH_SUFFIXES:
        return name[:-1]
    return name


def _canonical_forms(name: str) -> list[str]:
    forms = [name]
    forms.append(_strip_speech_suffix(name))
    if len(name) == 3:
        forms.append(name[1:])
    for suf in HONORIFIC_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf) + 1:
            forms.append(name[: -len(suf)])
    if name.endswith("儿") and len(name) >= 3:
        forms.append(name[:-1])
    return list(dict.fromkeys([f for f in forms if f]))


def _merge_character(source: Character, target: Character, db: Session) -> tuple[int, int]:
    alias_added = 0
    state_dropped = 0

    existing_aliases = {a.alias for a in target.aliases}
    if source.canonical_name not in existing_aliases:
        db.add(CharacterAlias(character_id=target.id, alias=source.canonical_name, source="refinement"))
        existing_aliases.add(source.canonical_name)
        alias_added += 1

    for alias in source.aliases:
        if alias.alias in existing_aliases:
            continue
        db.add(CharacterAlias(character_id=target.id, alias=alias.alias, source="refinement"))
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


def _find_merge_target(source: Character, by_name: dict[str, Character]) -> Character | None:
    forms = _canonical_forms(source.canonical_name)
    for alias in source.aliases:
        forms.extend(_canonical_forms(alias.alias))
    forms = list(dict.fromkeys(forms))

    candidates: list[Character] = []
    for f in forms:
        target = by_name.get(f)
        if not target or target.id == source.id:
            continue
        if _is_noise_like(target.canonical_name):
            continue
        candidates.append(target)
    if not candidates:
        return None

    candidates.sort(key=lambda c: (c.mention_count, c.confidence), reverse=True)
    top = candidates[0]
    threshold = max(3, int(source.mention_count * settings.skill_refine_merge_ratio))
    if top.mention_count < threshold:
        return None
    return top


class CharacterRefinementSkill:
    name = "character_refinement_build"

    def run(self, db: Session, *, book_id: str, **_: object) -> SkillResult:
        characters = list(
            db.execute(
                select(Character)
                .where(Character.book_id == book_id)
                .options(selectinload(Character.aliases), selectinload(Character.card), selectinload(Character.states))
                .order_by(Character.mention_count.asc(), Character.canonical_name.asc())
            ).scalars()
        )
        if not characters:
            return SkillResult(self.name, status="failed", message="no characters")

        by_name = {c.canonical_name: c for c in characters}
        deleted_ids: set[str] = set()
        merge_count = 0
        alias_added = 0
        state_dropped = 0

        for source in characters:
            if source.id in deleted_ids:
                continue
            target = _find_merge_target(source, by_name)
            if not target:
                continue
            if source.id == target.id:
                continue
            a_count, s_count = _merge_character(source, target, db)
            alias_added += a_count
            state_dropped += s_count
            deleted_ids.add(source.id)
            by_name.pop(source.canonical_name, None)
            merge_count += 1

        refreshed = list(db.execute(select(Character).where(Character.book_id == book_id)).scalars())

        llm_checked_count = 0
        llm_rejected_count = 0
        llm_rejections: set[str] = set()
        if settings.skill_refine_llm_enabled:
            suspicious = [
                c.canonical_name
                for c in refreshed
                if c.mention_count <= 8 and not _is_noise_like(c.canonical_name)
            ][: settings.skill_refine_llm_max_candidates]
            if suspicious:
                try:
                    verdict = verify_character_candidates(suspicious)
                    llm_checked_count = len(suspicious)
                    llm_rejections = {name for name, ok in verdict.items() if not ok}
                    llm_rejected_count = len(llm_rejections)
                except Exception:
                    llm_checked_count = 0
                    llm_rejected_count = 0
                    llm_rejections = set()

        verified_count = 0
        unverified_count = 0
        noise_unverified_count = 0
        llm_unverified_count = 0
        for character in refreshed:
            if _is_noise_like(character.canonical_name):
                character.is_verified = False
                character.confidence = min(character.confidence, 0.19)
                noise_unverified_count += 1
                unverified_count += 1
                continue
            if character.canonical_name in llm_rejections:
                character.is_verified = False
                character.confidence = min(character.confidence, 0.19)
                llm_unverified_count += 1
                unverified_count += 1
                continue
            character.is_verified = bool(
                character.confidence >= 0.2 and character.mention_count >= settings.skill_character_min_mentions
            )
            if character.is_verified:
                verified_count += 1
            else:
                unverified_count += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "merge_count": merge_count,
                "alias_added": alias_added,
                "state_dropped": state_dropped,
                "llm_checked_count": llm_checked_count,
                "llm_rejected_count": llm_rejected_count,
                "verified_count": verified_count,
                "unverified_count": unverified_count,
                "noise_unverified_count": noise_unverified_count,
                "llm_unverified_count": llm_unverified_count,
            },
        )
