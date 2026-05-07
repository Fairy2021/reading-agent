from __future__ import annotations

from app.skills.base import BookSkill, SkillResult
from app.skills.character_card import CharacterCardSkill
from app.skills.character_discovery import CharacterDiscoverySkill
from app.skills.character_normalization import CharacterNormalizationSkill
from app.skills.character_portrait_unlock import CharacterPortraitUnlockSkill
from app.skills.character_refinement import CharacterRefinementSkill
from app.skills.dialogue_constraint import DialogueConstraintSkill
from app.skills.relationship_graph import RelationshipGraphSkill
from app.skills.relationship_state import RelationshipStateSkill
from app.skills.story_progression import StoryProgressionSkill

SKILL_REGISTRY: dict[str, BookSkill] = {
    "character_discovery": CharacterDiscoverySkill(),
    "character_normalization_build": CharacterNormalizationSkill(),
    "character_refinement_build": CharacterRefinementSkill(),
    "character_card_build": CharacterCardSkill(),
    "relationship_state_build": RelationshipStateSkill(),
    "relationship_graph_build": RelationshipGraphSkill(),
    "story_progression_build": StoryProgressionSkill(),
    "dialogue_constraint_build": DialogueConstraintSkill(),
    "character_portrait_unlock_build": CharacterPortraitUnlockSkill(),
}

DEFAULT_SKILLS = [
    "character_discovery",
    "character_normalization_build",
    "character_refinement_build",
    "character_card_build",
    "relationship_state_build",
    "relationship_graph_build",
    "story_progression_build",
    "dialogue_constraint_build",
    "character_portrait_unlock_build",
]


def run_book_skill_pipeline(
    db,
    *,
    book_id: str,
    skill_names: list[str] | None = None,
    min_chapter_index: int = 1,
    max_chapter_index: int | None = None,
    incremental: bool = True,
) -> list[SkillResult]:
    names = skill_names or DEFAULT_SKILLS
    results: list[SkillResult] = []

    for name in names:
        skill = SKILL_REGISTRY.get(name)
        if not skill:
            results.append(
                SkillResult(
                    skill_name=name,
                    status="failed",
                    message="unknown skill name",
                )
            )
            continue

        try:
            result = skill.run(
                db,
                book_id=book_id,
                min_chapter_index=min_chapter_index,
                max_chapter_index=max_chapter_index,
                incremental=incremental,
            )
        except Exception as exc:  # noqa: PERF203
            db.rollback()
            result = SkillResult(
                skill_name=name,
                status="failed",
                message=str(exc),
            )
        results.append(result)

    return results


def serialize_skill_results(results: list[SkillResult]) -> list[dict]:
    payload: list[dict] = []
    for result in results:
        payload.append(
            {
                "skill_name": result.skill_name,
                "status": result.status,
                "metrics": result.metrics,
                "message": result.message,
            }
        )
    return payload
