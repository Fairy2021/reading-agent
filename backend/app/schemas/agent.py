from pydantic import BaseModel, Field


class AgentExecuteRequest(BaseModel):
    book_id: str
    message: str = Field(min_length=1, max_length=4000)
    role_name: str = Field(default="Narrator", min_length=1, max_length=100)
    chapter_index: int | None = None
    visual_asset_type: str | None = None
    visual_character_id: str | None = None
    session_id: str | None = None


class AgentSubtaskResult(BaseModel):
    agent: str
    status: str
    payload: dict = {}


class AgentExecuteResponse(BaseModel):
    run_id: str
    plan: dict
    merge_policy: str
    results: list[AgentSubtaskResult]


class AgentRunStatusResponse(BaseModel):
    run_id: str
    status: str
    planner_intent: str
    merge_policy: str
    task_statuses: list[dict]
    inbox_messages: list[dict]


class AgentTaskListResponse(BaseModel):
    run_id: str
    items: list[dict]


class AgentMessageListResponse(BaseModel):
    run_id: str
    items: list[dict]
