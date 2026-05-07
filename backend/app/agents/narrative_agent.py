from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.routes.chat import role_chat
from app.schemas.chat import ChatRequest, ChatResponse


def execute_narrative_agent(
    db: Session,
    *,
    book_id: str,
    message: str,
    role_name: str,
    chapter_index: int | None,
    session_id: str | None,
) -> ChatResponse:
    payload = ChatRequest(
        book_id=book_id,
        message=message,
        role_name=role_name,
        chapter_index=chapter_index,
        session_id=session_id,
    )
    return role_chat(payload, db)
