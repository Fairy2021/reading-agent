from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PlanIntent = Literal["narrative_only", "visual_only", "hybrid"]


@dataclass
class PlanStep:
    agent: Literal["narrative", "visual"]
    goal: str
    priority: int
    depends_on: int | None = None


@dataclass
class PlanningResult:
    intent: PlanIntent
    steps: list[PlanStep]
    merge_policy: str
    rationale: str

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "steps": [
                {
                    "agent": s.agent,
                    "goal": s.goal,
                    "priority": s.priority,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
            "merge_policy": self.merge_policy,
            "rationale": self.rationale,
        }


def build_execution_plan(*, message: str, visual_asset_type: str | None, role_name: str | None = None) -> PlanningResult:
    msg = (message or "").lower()
    if visual_asset_type and (message or "").strip():
        return PlanningResult(
            intent="hybrid",
            steps=[
                PlanStep(agent="narrative", goal="生成文本证据与解释", priority=1),
                PlanStep(agent="visual", goal="提交视觉任务并返回状态", priority=2, depends_on=1),
            ],
            merge_policy="text_first",
            rationale="显式传入 visual_asset_type 且包含文本消息，按混合模式执行。",
        )

    wants_visual = bool(visual_asset_type) or any(
        key in msg for key in ["立绘", "配图", "场景图", "角色卡", "draw", "image"]
    )
    wants_narrative = any(
        key in msg for key in ["关系", "怎么看", "剧情", "对话", "chapter", "为什么", "解释"]
    ) or not wants_visual or (role_name is not None and role_name != "Narrator")

    if wants_visual and wants_narrative:
        return PlanningResult(
            intent="hybrid",
            steps=[
                PlanStep(agent="narrative", goal="生成文本证据与解释", priority=1),
                PlanStep(agent="visual", goal="提交视觉任务并返回状态", priority=2, depends_on=1),
            ],
            merge_policy="text_first",
            rationale="请求同时包含文本理解与视觉生成意图，采用混合执行。",
        )
    if wants_visual:
        return PlanningResult(
            intent="visual_only",
            steps=[PlanStep(agent="visual", goal="提交视觉任务并返回状态", priority=1)],
            merge_policy="visual_first",
            rationale="请求主要为视觉生成意图。",
        )
    return PlanningResult(
        intent="narrative_only",
        steps=[PlanStep(agent="narrative", goal="生成角色化文本回答", priority=1)],
        merge_policy="text_first",
        rationale="请求主要为文本问答与关系解释。",
    )
