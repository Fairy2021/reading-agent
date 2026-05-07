from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.main_controller_agent import (
    execute_multi_agent,
    get_run_messages,
    get_run_status,
    get_run_tasks,
)
from app.db.session import get_db
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentMessageListResponse,
    AgentRunStatusResponse,
    AgentTaskListResponse,
)

router = APIRouter()


@router.post("/execute", response_model=AgentExecuteResponse)
def execute_agent(payload: AgentExecuteRequest, db: Session = Depends(get_db)) -> AgentExecuteResponse:
    return execute_multi_agent(db, payload)


@router.get("/runs/{run_id}", response_model=AgentRunStatusResponse)
def get_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunStatusResponse:
    status = get_run_status(db, run_id)
    if not status:
        raise HTTPException(status_code=404, detail="run not found")
    return status


@router.get("/runs/{run_id}/tasks", response_model=AgentTaskListResponse)
def get_agent_run_tasks(run_id: str, db: Session = Depends(get_db)) -> AgentTaskListResponse:
    status = get_run_tasks(db, run_id)
    if not status:
        raise HTTPException(status_code=404, detail="run not found")
    return status


@router.get("/runs/{run_id}/messages", response_model=AgentMessageListResponse)
def get_agent_run_messages(
    run_id: str,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> AgentMessageListResponse:
    status = get_run_messages(db, run_id, limit=limit)
    if not status:
        raise HTTPException(status_code=404, detail="run not found")
    return status
