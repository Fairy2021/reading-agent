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


class VisualJobCreateResponse(BaseModel):
    task_id: str
    job_id: str
    book_id: str
    status: str = "queued"


class VisualJobCreateRequest(BaseModel):
    asset_type: str = "portrait"
    character_id: str | None = None
    chapter_index: int | None = None
    style_prompt: str | None = None
    priority: int = 5


class VisualJobStatusResponse(BaseModel):
    job_id: str
    book_id: str
    asset_type: str
    status: str
    task_id: str
    result_asset_id: str | None = None
    error_message: str = ""


class MediaAssetResponse(BaseModel):
    id: str
    book_id: str
    character_id: str | None = None
    asset_type: str
    chapter_index: int | None = None
    status: str
    style_prompt: str
    storage_url: str
    generator: str
    version: int


class VisualStyleProfileResponse(BaseModel):
    id: str
    book_id: str
    style_name: str
    palette: str
    brush: str
    mood: str
    negative_prompt: str
    locked: str


class VisualStyleProfileUpdateRequest(BaseModel):
    style_name: str | None = None
    palette: str | None = None
    brush: str | None = None
    mood: str | None = None
    negative_prompt: str | None = None
    locked: str | None = None


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
