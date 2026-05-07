from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.narrative_agent import execute_narrative_agent
from app.agents.planning_agent import build_execution_plan
from app.agents.visual_agent import execute_visual_agent
from app.models import AgentMemory, AgentMessage, AgentRun, AgentTask
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentMessageListResponse,
    AgentRunStatusResponse,
    AgentSubtaskResult,
    AgentTaskListResponse,
)


def _upsert_memory(db: Session, *, agent_name: str, book_id: str, run_id: str, delta: str) -> None:
    row = db.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_name == agent_name, AgentMemory.book_id == book_id)
        .limit(1)
    ).scalars().first()
    if not row:
        row = AgentMemory(
            agent_name=agent_name,
            book_id=book_id,
            memory_summary=delta[:1200],
            last_run_id=run_id,
        )
        db.add(row)
    else:
        merged = (row.memory_summary + "\n" + delta).strip()
        row.memory_summary = merged[-2400:]
        row.last_run_id = run_id


def execute_multi_agent(db: Session, payload: AgentExecuteRequest) -> AgentExecuteResponse:
    run_id = str(uuid.uuid4())
    plan = build_execution_plan(
        message=payload.message,
        visual_asset_type=payload.visual_asset_type,
        role_name=payload.role_name,
    )

    run = AgentRun(
        id=run_id,
        book_id=payload.book_id,
        trigger_message=payload.message,
        planner_intent=plan.intent,
        merge_policy=plan.merge_policy,
        plan_json=json.dumps(plan.to_dict(), ensure_ascii=False),
        status="running",
    )
    db.add(run)
    db.flush()

    created_task_id_by_priority: dict[int, str] = {}
    for step in sorted(plan.steps, key=lambda s: s.priority):
        task_payload = {
            "book_id": payload.book_id,
            "message": payload.message,
            "role_name": payload.role_name,
            "chapter_index": payload.chapter_index,
            "visual_asset_type": payload.visual_asset_type,
            "visual_character_id": payload.visual_character_id,
            "session_id": payload.session_id,
        }
        task = AgentTask(
            run_id=run_id,
            target_agent=step.agent,
            depends_on_task_id=(
                created_task_id_by_priority.get(step.depends_on)
                if step.depends_on is not None
                else None
            ),
            goal=step.goal,
            payload_json=json.dumps(task_payload, ensure_ascii=False),
            priority=step.priority,
            status="queued",
        )
        db.add(task)
        db.flush()
        created_task_id_by_priority[step.priority] = task.id
        db.add(
            AgentMessage(
                run_id=run_id,
                from_agent="main_controller",
                to_agent=step.agent,
                correlation_task_id=task.id,
                message_type="task",
                payload_json=json.dumps({"task_id": task.id, "goal": step.goal}, ensure_ascii=False),
                status="queued",
            )
        )
    db.commit()

    results: list[AgentSubtaskResult] = []
    # loop: each cycle reads inbox, executes one queued task
    for _ in range(12):
        # Main controller reads result inbox at the beginning of each cycle.
        main_inbox = db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.run_id == run_id,
                AgentMessage.to_agent == "main_controller",
                AgentMessage.status == "queued",
            )
            .order_by(AgentMessage.created_at.asc())
        ).scalars().all()
        for msg in main_inbox:
            msg.status = "read"
            msg.status = "acked"

        queued_tasks = db.execute(
            select(AgentTask)
            .where(
                AgentTask.run_id == run_id,
                AgentTask.status == "queued",
            )
            .order_by(AgentTask.priority.asc(), AgentTask.created_at.asc())
        ).scalars().all()
        task = None
        for candidate in queued_tasks:
            if not candidate.depends_on_task_id:
                task = candidate
                break
            dep = db.get(AgentTask, candidate.depends_on_task_id)
            if dep and dep.status == "completed":
                task = candidate
                break
        db.commit()
        if not task:
            break

        inbox_rows = db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.run_id == run_id,
                AgentMessage.to_agent == task.target_agent,
                AgentMessage.status == "queued",
            )
            .order_by(AgentMessage.created_at.asc())
        ).scalars().all()
        for msg in inbox_rows:
            msg.status = "read"
            msg.status = "acked"
        task.status = "running"
        db.commit()

        data = json.loads(task.payload_json or "{}")
        try:
            if task.target_agent == "narrative":
                resp = execute_narrative_agent(
                    db,
                    book_id=data["book_id"],
                    message=data["message"],
                    role_name=data.get("role_name", "Narrator"),
                    chapter_index=data.get("chapter_index"),
                    session_id=data.get("session_id"),
                )
                payload_result = resp.model_dump()
                task.status = "completed"
                task.result_json = json.dumps(payload_result, ensure_ascii=False)
                results.append(AgentSubtaskResult(agent="narrative", status="completed", payload=payload_result))
                _upsert_memory(
                    db,
                    agent_name="narrative",
                    book_id=data["book_id"],
                    run_id=run_id,
                    delta=f"Q:{data.get('message','')[:160]} | A:{payload_result.get('answer','')[:180]}",
                )
            elif task.target_agent == "visual":
                asset_type = data.get("visual_asset_type") or "scene"
                visual = execute_visual_agent(
                    db,
                    book_id=data["book_id"],
                    asset_type=asset_type,
                    chapter_index=data.get("chapter_index"),
                    character_id=data.get("visual_character_id"),
                )
                task.status = "completed" if visual.get("status") in {"queued", "running", "completed"} else "failed"
                task.result_json = json.dumps(visual, ensure_ascii=False)
                if task.status == "failed":
                    task.error_message = visual.get("reason", "")
                results.append(AgentSubtaskResult(agent="visual", status=task.status, payload=visual))
                _upsert_memory(
                    db,
                    agent_name="visual",
                    book_id=data["book_id"],
                    run_id=run_id,
                    delta=f"asset={asset_type} status={visual.get('status')} job={visual.get('job_id','')}",
                )
            else:
                task.status = "failed"
                task.error_message = "unknown target_agent"
                results.append(AgentSubtaskResult(agent=task.target_agent, status="failed", payload={"error": "unknown target_agent"}))
        except Exception as exc:  # noqa: PERF203
            task.status = "failed"
            task.error_message = str(exc)
            results.append(AgentSubtaskResult(agent=task.target_agent, status="failed", payload={"error": str(exc)}))

        db.add(
            AgentMessage(
                run_id=run_id,
                from_agent=task.target_agent,
                to_agent="main_controller",
                correlation_task_id=task.id,
                message_type="result",
                payload_json=task.result_json or json.dumps({"error": task.error_message}, ensure_ascii=False),
                status="queued",
            )
        )
        db.commit()

    remaining = db.execute(
        select(AgentTask).where(AgentTask.run_id == run_id, AgentTask.status.in_(["queued", "running"]))
    ).scalars().all()
    run.status = "completed" if not remaining else "partial"
    db.commit()

    return AgentExecuteResponse(
        run_id=run_id,
        plan=plan.to_dict(),
        merge_policy=plan.merge_policy,
        results=results,
    )


def get_run_status(db: Session, run_id: str) -> AgentRunStatusResponse | None:
    run = db.get(AgentRun, run_id)
    if not run:
        return None
    tasks = db.execute(
        select(AgentTask).where(AgentTask.run_id == run_id).order_by(AgentTask.priority.asc())
    ).scalars().all()
    inbox = db.execute(
        select(AgentMessage)
        .where(AgentMessage.run_id == run_id, AgentMessage.status == "queued")
        .order_by(AgentMessage.created_at.asc())
        .limit(50)
    ).scalars().all()
    return AgentRunStatusResponse(
        run_id=run.id,
        status=run.status,
        planner_intent=run.planner_intent,
        merge_policy=run.merge_policy,
        task_statuses=[
            {
                "task_id": t.id,
                "target_agent": t.target_agent,
                "depends_on_task_id": t.depends_on_task_id,
                "goal": t.goal,
                "status": t.status,
                "priority": t.priority,
                "error_message": t.error_message,
            }
            for t in tasks
        ],
        inbox_messages=[
            {
                "id": m.id,
                "from_agent": m.from_agent,
                "to_agent": m.to_agent,
                "message_type": m.message_type,
                "correlation_task_id": m.correlation_task_id,
                "status": m.status,
            }
            for m in inbox
        ],
    )


def get_run_tasks(db: Session, run_id: str) -> AgentTaskListResponse | None:
    run = db.get(AgentRun, run_id)
    if not run:
        return None
    tasks = db.execute(
        select(AgentTask).where(AgentTask.run_id == run_id).order_by(AgentTask.priority.asc(), AgentTask.created_at.asc())
    ).scalars().all()
    return AgentTaskListResponse(
        run_id=run_id,
        items=[
            {
                "task_id": t.id,
                "target_agent": t.target_agent,
                "depends_on_task_id": t.depends_on_task_id,
                "goal": t.goal,
                "status": t.status,
                "priority": t.priority,
                "result_json": t.result_json,
                "error_message": t.error_message,
            }
            for t in tasks
        ],
    )


def get_run_messages(db: Session, run_id: str, limit: int = 200) -> AgentMessageListResponse | None:
    run = db.get(AgentRun, run_id)
    if not run:
        return None
    rows = db.execute(
        select(AgentMessage)
        .where(AgentMessage.run_id == run_id)
        .order_by(AgentMessage.created_at.asc())
        .limit(limit)
    ).scalars().all()
    return AgentMessageListResponse(
        run_id=run_id,
        items=[
            {
                "message_id": m.id,
                "from_agent": m.from_agent,
                "to_agent": m.to_agent,
                "message_type": m.message_type,
                "correlation_task_id": m.correlation_task_id,
                "status": m.status,
                "payload_json": m.payload_json,
                "created_at": str(m.created_at),
            }
            for m in rows
        ],
    )
