from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    book_id: str | None = None
    role_name: str = Field(default="Narrator", min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    chapter_index: int | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=128)


class Citation(BaseModel):
    chapter_index: int
    chapter_title: str
    chunk_id: str
    chunk_index: int
    score: float
    preview: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    spoiler_risk: str = "low"
    llm_used: bool = False
    llm_model: str = ""
    llm_error: str = ""
    guard_applied: bool = False
    session_id: str | None = None
