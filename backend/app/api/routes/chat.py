from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import Book, Character, CharacterAlias, CharacterState, DialogueConstraint, SessionMemory
from app.schemas.chat import ChatRequest, ChatResponse, Citation
from app.services.agent_orchestrator import build_plan, execute_react
from app.services.llm_chat import guard_and_rewrite_answer, request_roleplay_completion
from app.services.rag import get_book_max_chapter_index

router = APIRouter()

DEFAULT_ROLE_STYLE = {
    "贾宝玉": "语气温柔细腻，重情重义，先接住对方情绪再表达看法。",
    "林黛玉": "语气敏感聪慧，含蓄而锋利，情绪真切但不失自尊。",
    "薛宝钗": "语气稳重得体，讲分寸与体面，倾向理性安抚。",
    "Narrator": "叙述客观清晰，兼顾共情，不脱离证据。",
}


def _fallback_persona_answer(
    *,
    role_name: str,
    role_style: str,
    user_message: str,
    evidence_snippets: list[str],
) -> str:
    opening = "我在这儿，我们慢慢聊。"
    if any(k in user_message for k in ["难受", "痛苦", "伤心", "孤独", "害怕"]):
        opening = "我听见你的难受了，先别急，我们慢慢说。"
    elif any(k in user_message for k in ["开心", "高兴", "激动", "喜欢"]):
        opening = "我能感到你的喜悦，这份心意很珍贵。"

    if not evidence_snippets:
        return (
            f"{opening}\n\n"
            f"以 {role_name} 的立场，我愿意继续陪你聊。"
            "但当前可用证据不足，我不想编造超出文本的信息。"
        )

    bullet = "\n".join(f"- {snippet}" for snippet in evidence_snippets[:3])
    return (
        f"{opening}\n\n"
        f"角色风格约束：{role_style}\n\n"
        "基于你已读章节中的证据，我这样回应你：\n"
        f"{bullet}\n\n"
        "如果你愿意，我们可以沿着这条情节继续聊下去。"
    )


def _build_persona_state_text(role_state: CharacterState | None) -> str:
    if role_state is None:
        return "暂无角色状态快照。"
    return (
        f"章节={role_state.chapter_index}; "
        f"情绪={role_state.emotional_state}; "
        f"立场={role_state.stance}; "
        f"目标={role_state.current_goal}; "
        f"关系={role_state.relation_snapshot}"
    )


def _update_session_memory(
    *,
    db: Session,
    book_id: str,
    role_name: str,
    session_id: str,
    chapter_index: int,
    user_message: str,
    assistant_message: str,
) -> None:
    row = db.execute(
        select(SessionMemory)
        .where(
            SessionMemory.book_id == book_id,
            SessionMemory.session_id == session_id,
            SessionMemory.role_name == role_name,
        )
        .limit(1)
    ).scalars().first()

    emotion_tag = "neutral"
    if any(k in user_message for k in ["难受", "痛苦", "伤心", "孤独", "害怕"]):
        emotion_tag = "sad"
    elif any(k in user_message for k in ["开心", "高兴", "激动", "喜欢"]):
        emotion_tag = "positive"

    summary_piece = (
        f"用户:{user_message[:120]} | 角色:{assistant_message[:120]} | 情绪:{emotion_tag} | 章:{chapter_index}"
    )
    if row is None:
        row = SessionMemory(
            book_id=book_id,
            session_id=session_id,
            role_name=role_name,
            emotion_tag=emotion_tag,
            memory_summary=summary_piece[: settings.chat_session_memory_max_chars],
            last_user_message=user_message[:500],
            last_assistant_message=assistant_message[:500],
            last_chapter_index=chapter_index,
        )
        db.add(row)
    else:
        merged = (row.memory_summary + "\n" + summary_piece).strip()
        row.emotion_tag = emotion_tag
        row.memory_summary = merged[-settings.chat_session_memory_max_chars :]
        row.last_user_message = user_message[:500]
        row.last_assistant_message = assistant_message[:500]
        row.last_chapter_index = chapter_index


@router.post("", response_model=ChatResponse)
def role_chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if not payload.book_id:
        raise HTTPException(status_code=400, detail="book_id is required for roleplay RAG")

    book = db.get(Book, payload.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    max_available = get_book_max_chapter_index(db, payload.book_id)
    if max_available <= 0:
        raise HTTPException(status_code=400, detail="Book has no chapter data")

    progress_index = payload.chapter_index or max_available
    if progress_index > max_available:
        progress_index = max_available

    plan = build_plan(payload.message, payload.role_name)
    exec_result = execute_react(
        db,
        book_id=payload.book_id,
        message=payload.message,
        progress_index=progress_index,
        plan=plan,
    )
    citations = [
        Citation(
            chapter_index=e["chapter_index"],
            chapter_title=e["chapter_title"],
            chunk_id=e["chunk_id"],
            chunk_index=e["chunk_index"],
            score=float(e["score"]),
            preview=e["preview"],
        )
        for e in exec_result.citations
    ]
    evidence_snippets = exec_result.evidence_snippets

    role_style_hint = DEFAULT_ROLE_STYLE.get(payload.role_name, DEFAULT_ROLE_STYLE["Narrator"])
    role_character = None
    if payload.role_name != "Narrator":
        role_character = db.execute(
            select(Character)
            .where(
                Character.book_id == payload.book_id,
                Character.canonical_name == payload.role_name,
                Character.is_verified.is_(True),
            )
            .options(selectinload(Character.card))
            .limit(1)
        ).scalars().first()
        if not role_character:
            role_character = db.execute(
                select(Character)
                .join(CharacterAlias, CharacterAlias.character_id == Character.id)
                .where(
                    Character.book_id == payload.book_id,
                    Character.is_verified.is_(True),
                    CharacterAlias.alias == payload.role_name,
                )
                .options(selectinload(Character.card))
                .limit(1)
            ).scalars().first()
        if not role_character:
            raise HTTPException(status_code=404, detail="Role not found or not verified")

    if role_character and role_character.card:
        role_style_hint = (
            f"{role_character.card.identity_summary} "
            f"{role_character.card.personality_summary} "
            f"{role_character.card.speaking_style} "
            f"{role_character.card.values_and_taboo}"
        ).strip()

    role_state = None
    if role_character:
        role_state = db.execute(
            select(CharacterState)
            .where(
                CharacterState.character_id == role_character.id,
                CharacterState.chapter_index <= progress_index,
            )
            .order_by(CharacterState.chapter_index.desc())
            .limit(1)
        ).scalars().first()
    persona_state_text = _build_persona_state_text(role_state)

    dialog_constraint = db.execute(
        select(DialogueConstraint)
        .where(
            DialogueConstraint.book_id == payload.book_id,
            DialogueConstraint.chapter_index <= progress_index,
        )
        .order_by(DialogueConstraint.chapter_index.desc())
        .limit(1)
    ).scalars().first()
    if dialog_constraint:
        role_style_hint = (
            f"{role_style_hint}\n"
            f"对话约束:{dialog_constraint.allowed_scope} "
            f"{dialog_constraint.blocked_topics} "
            f"{dialog_constraint.roleplay_policy}"
        ).strip()

    session_id = payload.session_id or str(uuid.uuid4())
    memory_row = db.execute(
        select(SessionMemory)
        .where(
            SessionMemory.book_id == payload.book_id,
            SessionMemory.session_id == session_id,
            SessionMemory.role_name == payload.role_name,
        )
        .limit(1)
    ).scalars().first()
    session_memory_text = memory_row.memory_summary if memory_row else ""

    llm_used = False
    llm_error = ""
    try:
        answer = request_roleplay_completion(
            role_name=payload.role_name,
            role_style=role_style_hint,
            persona_state=persona_state_text,
            session_memory=session_memory_text,
            user_message=payload.message,
            chapter_index=progress_index,
            evidence_snippets=evidence_snippets,
        )
        llm_used = True
    except Exception:
        llm_error = "llm_unreachable_or_failed"
        answer = _fallback_persona_answer(
            role_name=payload.role_name,
            role_style=role_style_hint,
            user_message=payload.message,
            evidence_snippets=evidence_snippets,
        )

    guarded_answer = answer
    guard_applied = False
    guard_reason = "not_checked"
    if llm_used or settings.chat_guard_enabled:
        guarded_answer, guard_applied, guard_reason = guard_and_rewrite_answer(
            role_name=payload.role_name,
            answer=answer,
            chapter_index=progress_index,
            evidence_snippets=evidence_snippets,
        )

    _update_session_memory(
        db=db,
        book_id=payload.book_id,
        role_name=payload.role_name,
        session_id=session_id,
        chapter_index=progress_index,
        user_message=payload.message,
        assistant_message=guarded_answer,
    )
    db.commit()

    spoiler_risk = f"low (progress-guarded) | agent={plan.intent}"
    if guard_applied:
        spoiler_risk = f"guarded ({guard_reason})"

    return ChatResponse(
        answer=guarded_answer,
        citations=citations,
        spoiler_risk=spoiler_risk,
        llm_used=llm_used,
        llm_model=settings.openai_model,
        llm_error=llm_error,
        guard_applied=guard_applied,
        session_id=session_id,
    )
