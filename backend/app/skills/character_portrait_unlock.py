from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Character, CharacterPortrait
from app.skills.base import SkillResult


def _select_evidence_excerpt(character: Character, keywords: list[str], limit: int = 2) -> list[str]:
    matches: list[str] = []
    for evidence in sorted(character.evidences, key=lambda x: x.chapter_index):
        excerpt = (evidence.excerpt or "").strip()
        if not excerpt:
            continue
        if any(keyword in excerpt for keyword in keywords):
            matches.append(excerpt)
        if len(matches) >= limit:
            break
    return matches


def build_style_prompt(character: Character) -> str:
    appearance_keywords = [
        "容貌",
        "相貌",
        "眉",
        "眼",
        "衣",
        "服",
        "身形",
        "气质",
        "神态",
    ]
    personality_keywords = [
        "性格",
        "脾气",
        "心性",
        "温柔",
        "刚烈",
        "聪慧",
        "谨慎",
        "机敏",
        "善良",
    ]
    appearance_evidence = _select_evidence_excerpt(character, appearance_keywords)
    personality_evidence = _select_evidence_excerpt(character, personality_keywords)

    if character.card:
        pieces = [
            f"角色名：{character.canonical_name}",
            f"身份：{character.card.identity_summary or '未知'}",
            f"性格：{character.card.personality_summary or '未知'}",
            f"说话风格：{character.card.speaking_style or '未知'}",
            f"价值观与禁忌：{character.card.values_and_taboo or '未知'}",
            (
                "外貌线索："
                + ("；".join(appearance_evidence) if appearance_evidence else "依据章节证据推断古典人物外貌")
            ),
            (
                "性格线索："
                + ("；".join(personality_evidence) if personality_evidence else "依据章节证据还原人物气质")
            ),
            "画风要求：中文古典文学人物立绘，半身像，细节真实，服饰符合时代背景，避免现代元素，电影级光影，背景干净。",
        ]
    else:
        pieces = [
            f"角色名：{character.canonical_name}",
            "身份：未知",
            "性格：基于原著首次登场设定",
            (
                "外貌线索："
                + ("；".join(appearance_evidence) if appearance_evidence else "依据章节证据推断古典人物外貌")
            ),
            "画风要求：中文古典文学人物立绘，半身像，细节真实，服饰符合时代背景，避免现代元素，电影级光影，背景干净。",
        ]
    return "\n".join(pieces).strip()


class CharacterPortraitUnlockSkill:
    name = "character_portrait_unlock_build"

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
        stmt = (
            select(Character)
            .where(Character.book_id == book_id, Character.is_verified.is_(True))
            .options(selectinload(Character.card), selectinload(Character.evidences))
            .order_by(Character.first_chapter_index.asc().nullslast(), Character.mention_count.desc())
        )
        if max_chapter_index is not None:
            stmt = stmt.where(
                Character.first_chapter_index.is_not(None),
                Character.first_chapter_index <= max_chapter_index,
            )
        characters = list(db.execute(stmt).scalars())
        if not characters:
            return SkillResult(self.name, metrics={"candidate_count": 0, "portrait_count": 0})

        existing = {
            row.character_id: row
            for row in db.execute(
                select(CharacterPortrait).where(CharacterPortrait.book_id == book_id)
            ).scalars()
        }

        created_count = 0
        updated_count = 0
        skipped_existing_count = 0
        queued_count = 0
        processed_count = 0

        for character in characters:
            first_seen = character.first_chapter_index
            if first_seen is None:
                continue
            if first_seen < min_chapter_index:
                # Incremental mode: only unlock newly seen characters in this chapter window.
                if incremental:
                    continue
            if max_chapter_index is not None and first_seen > max_chapter_index:
                continue

            processed_count += 1
            style_prompt = build_style_prompt(character)
            row = existing.get(character.id)

            if row is None:
                row = CharacterPortrait(
                    book_id=book_id,
                    character_id=character.id,
                    unlocked_chapter_index=first_seen,
                    status="queued",
                    style_prompt=style_prompt,
                    generator="pending",
                )
                db.add(row)
                existing[character.id] = row
                created_count += 1
                queued_count += 1
                continue

            # Keep earliest unlock chapter stable.
            row.unlocked_chapter_index = min(row.unlocked_chapter_index, first_seen)

            # Refresh prompt so character card updates can flow to next render run.
            if row.style_prompt != style_prompt:
                row.style_prompt = style_prompt
                updated_count += 1

            # Requeue only when portrait is not ready yet.
            if row.status in {"pending", "failed"}:
                row.status = "queued"
                queued_count += 1
                updated_count += 1
            else:
                skipped_existing_count += 1

        db.commit()
        portrait_count = db.execute(
            select(CharacterPortrait.id).where(CharacterPortrait.book_id == book_id)
        ).scalars().all()
        return SkillResult(
            self.name,
            metrics={
                "candidate_count": len(characters),
                "processed_count": processed_count,
                "portrait_count": len(portrait_count),
                "created_count": created_count,
                "updated_count": updated_count,
                "queued_count": queued_count,
                "skipped_existing_count": skipped_existing_count,
                "range_min": min_chapter_index,
                "range_max": max_chapter_index or 0,
            },
        )
