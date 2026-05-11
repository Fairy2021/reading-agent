from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Character
from app.services.character_name_filter import is_noise_like_character_name, sanitize_character_name
from app.services.llm_extract import verify_character_candidates
from app.skills.base import SkillResult


class CharacterDenoiseSkill:
    name = "character_denoise_build"

    def run(self, db: Session, *, book_id: str, **_: object) -> SkillResult:
        characters = list(
            db.execute(
                select(Character)
                .where(Character.book_id == book_id)
                .options(selectinload(Character.aliases))
                .order_by(Character.mention_count.desc(), Character.canonical_name.asc())
            ).scalars()
        )
        if not characters:
            return SkillResult(self.name, status="failed", message="no characters")

        alias_deleted = 0
        canonical_sanitized = 0
        heuristic_unverified = 0
        llm_checked = 0
        llm_unverified = 0

        # 1) Rule-based alias cleanup (always on)
        for character in characters:
            sanitized_canonical = sanitize_character_name(character.canonical_name)
            if sanitized_canonical and sanitized_canonical != character.canonical_name:
                # Rename when safe; otherwise keep source but downgrade verification below.
                conflict = db.execute(
                    select(Character)
                    .where(
                        Character.book_id == book_id,
                        Character.canonical_name == sanitized_canonical,
                        Character.id != character.id,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if not conflict:
                    character.canonical_name = sanitized_canonical
                    canonical_sanitized += 1
            for alias in list(character.aliases):
                if alias.alias == character.canonical_name:
                    continue
                sanitized_alias = sanitize_character_name(alias.alias)
                if not sanitized_alias or is_noise_like_character_name(alias.alias):
                    db.delete(alias)
                    alias_deleted += 1
                elif sanitized_alias != alias.alias:
                    alias.alias = sanitized_alias

        # 2) LLM verify canonical names (prioritize suspicious + low confidence)
        llm_verdict: dict[str, bool] = {}
        if settings.skill_denoise_llm_enabled:
            suspicious = [c.canonical_name for c in characters if is_noise_like_character_name(c.canonical_name)]
            rest = [c for c in characters if c.canonical_name not in suspicious]
            rest.sort(key=lambda c: (c.confidence, c.mention_count, c.canonical_name))
            ordered = suspicious + [c.canonical_name for c in rest]

            # Deduplicate while preserving order.
            seen: set[str] = set()
            candidates: list[str] = []
            for name in ordered:
                if name in seen:
                    continue
                seen.add(name)
                candidates.append(name)
                if len(candidates) >= settings.skill_denoise_llm_max_candidates:
                    break

            if candidates:
                try:
                    llm_verdict = verify_character_candidates(candidates)
                    llm_checked = len(candidates)
                except Exception:
                    llm_verdict = {}
                    llm_checked = 0

        # 3) Apply final verification status
        for character in characters:
            heuristic_noise = is_noise_like_character_name(character.canonical_name)
            llm_value = llm_verdict.get(character.canonical_name)
            rejected_by_llm = llm_value is False

            if heuristic_noise and llm_value is not True:
                character.is_verified = False
                character.confidence = min(character.confidence, 0.19)
                heuristic_unverified += 1
                continue

            if rejected_by_llm:
                character.is_verified = False
                character.confidence = min(character.confidence, 0.19)
                llm_unverified += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "character_count": len(characters),
                "canonical_sanitized": canonical_sanitized,
                "alias_deleted": alias_deleted,
                "heuristic_unverified": heuristic_unverified,
                "llm_checked": llm_checked,
                "llm_unverified": llm_unverified,
            },
        )
