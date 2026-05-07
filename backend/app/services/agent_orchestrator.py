from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.tools import graph_query_tool, retrieval_tool


PlanIntent = Literal["character_roleplay", "graph_explain", "chapter_qa", "general"]


@dataclass
class AgentPlan:
    intent: PlanIntent
    actions: list[str]
    rationale: str


@dataclass
class ToolObservation:
    tool: str
    summary: str
    payload: dict = field(default_factory=dict)


@dataclass
class AgentExecutionResult:
    plan: AgentPlan
    observations: list[ToolObservation]
    evidence_snippets: list[str]
    citations: list[dict]


def _intent_from_message(message: str, role_name: str) -> PlanIntent:
    msg = (message or "").lower()
    if any(k in msg for k in ["关系", "图谱", "network", "graph"]):
        return "graph_explain"
    if role_name and role_name != "Narrator":
        return "character_roleplay"
    if any(k in msg for k in ["第", "章节", "chapter"]):
        return "chapter_qa"
    return "general"


def build_plan(message: str, role_name: str) -> AgentPlan:
    intent = _intent_from_message(message, role_name)
    if intent == "graph_explain":
        return AgentPlan(
            intent=intent,
            actions=["retrieve_evidence", "query_graph_snapshot", "compose_response"],
            rationale="问题包含关系图谱意图，需要图结构与原文证据双支撑。",
        )
    return AgentPlan(
        intent=intent,
        actions=["retrieve_evidence", "compose_response"],
        rationale="标准剧情/角色问答流程，先检索证据再生成回答。",
    )


def execute_react(
    db: Session,
    *,
    book_id: str,
    message: str,
    progress_index: int,
    plan: AgentPlan,
) -> AgentExecutionResult:
    observations: list[ToolObservation] = []

    evidences = retrieval_tool(
        db,
        book_id=book_id,
        query=message,
        max_chapter_index=progress_index,
        top_k=6,
    )
    evidence_snippets = [f"第{e.chapter_index}章《{e.chapter_title}》：{e.content[:120]}..." for e in evidences]
    citations = [
        {
            "chapter_index": e.chapter_index,
            "chapter_title": e.chapter_title,
            "chunk_id": e.chunk_id,
            "chunk_index": e.chunk_index,
            "score": round(e.score, 4),
            "preview": e.content[:180],
        }
        for e in evidences
    ]
    observations.append(
        ToolObservation(
            tool="retrieve_evidence",
            summary=f"召回 {len(evidences)} 条证据，进度约束 <= 第{progress_index}章。",
            payload={"count": len(evidences)},
        )
    )

    if "query_graph_snapshot" in plan.actions:
        snapshot = graph_query_tool(db, book_id=book_id, limit_nodes=10)
        observations.append(
            ToolObservation(
                tool="query_graph_snapshot",
                summary=(
                    f"图谱节点 {snapshot.node_count}，边 {snapshot.edge_count}，"
                    f"关系类型 {len(snapshot.relation_types)} 种。"
                ),
                payload={
                    "node_count": snapshot.node_count,
                    "edge_count": snapshot.edge_count,
                    "relation_types": snapshot.relation_types,
                    "top_nodes": snapshot.top_nodes,
                },
            )
        )

    return AgentExecutionResult(
        plan=plan,
        observations=observations,
        evidence_snippets=evidence_snippets,
        citations=citations,
    )
