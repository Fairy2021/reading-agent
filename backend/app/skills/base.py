from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session


@dataclass
class SkillResult:
    skill_name: str
    status: str = "success"
    metrics: dict[str, int | float | str] = field(default_factory=dict)
    message: str = ""


class BookSkill(Protocol):
    name: str

    def run(self, db: Session, *, book_id: str, **kwargs) -> SkillResult:
        ...
