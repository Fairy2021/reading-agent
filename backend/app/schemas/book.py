from datetime import datetime

from pydantic import BaseModel, Field


class BookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class BookResponse(BaseModel):
    id: str
    title: str
    source_type: str
    status: str
    skill_checkpoint_chapter: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class EnqueueResponse(BaseModel):
    task_id: str
    book_id: str
    status: str = "queued"


class ChapterSummaryResponse(BaseModel):
    id: str
    chapter_index: int
    title: str

    model_config = {"from_attributes": True}


class ChapterDetailResponse(BaseModel):
    id: str
    book_id: str
    chapter_index: int
    title: str
    raw_text: str

    model_config = {"from_attributes": True}
