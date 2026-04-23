from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Character, RelationshipEdge, RelationshipGraphNodeMetric
from app.skills.base import SkillResult


class RelationshipGraphSkill:
    name = "relationship_graph_build"

    def run(
        self,
        db: Session,
        *,
        book_id: str,
        max_chapter_index: int | None = None,
        **_: object,
    ) -> SkillResult:
        characters = list(
            db.execute(
                select(Character).where(Character.book_id == book_id, Character.is_verified.is_(True))
            ).scalars()
        )
        if not characters:
            return SkillResult(self.name, status="failed", message="no verified characters")

        by_id = {c.id: c for c in characters}
        edges_stmt = select(RelationshipEdge).where(RelationshipEdge.book_id == book_id)
        if max_chapter_index is not None:
            edges_stmt = edges_stmt.where(RelationshipEdge.last_chapter_index <= max_chapter_index)
        edges = list(db.execute(edges_stmt).scalars())

        neighbors: dict[str, set[str]] = defaultdict(set)
        weighted_degree: dict[str, float] = defaultdict(float)
        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)
        relation_types: dict[str, set[str]] = defaultdict(set)
        last_seen: dict[str, int] = defaultdict(int)

        for edge in edges:
            s_id = edge.source_character_id
            t_id = edge.target_character_id
            if s_id not in by_id or t_id not in by_id:
                continue
            neighbors[s_id].add(t_id)
            neighbors[t_id].add(s_id)
            weighted_degree[s_id] += float(edge.strength or 0.0)
            weighted_degree[t_id] += float(edge.strength or 0.0)
            out_degree[s_id] += 1
            in_degree[t_id] += 1
            relation_types[s_id].add(edge.relation_type or "other")
            relation_types[t_id].add(edge.relation_type or "other")

            edge_last = int(edge.last_chapter_index or 0)
            if edge_last > last_seen[s_id]:
                last_seen[s_id] = edge_last
            if edge_last > last_seen[t_id]:
                last_seen[t_id] = edge_last

        existing_rows = {
            row.character_id: row
            for row in db.execute(
                select(RelationshipGraphNodeMetric).where(RelationshipGraphNodeMetric.book_id == book_id)
            ).scalars()
        }

        stale_ids = [char_id for char_id in existing_rows.keys() if char_id not in by_id]
        if stale_ids:
            db.execute(
                delete(RelationshipGraphNodeMetric).where(
                    RelationshipGraphNodeMetric.book_id == book_id,
                    RelationshipGraphNodeMetric.character_id.in_(stale_ids),
                )
            )

        upsert_count = 0
        for char_id in by_id:
            degree = len(neighbors[char_id])
            metric = existing_rows.get(char_id)
            if metric is None:
                metric = RelationshipGraphNodeMetric(book_id=book_id, character_id=char_id)
                db.add(metric)
            metric.degree = degree
            metric.in_degree = in_degree[char_id]
            metric.out_degree = out_degree[char_id]
            metric.weighted_degree = round(weighted_degree[char_id], 4)
            metric.relation_diversity = len(relation_types[char_id])
            metric.last_chapter_index = last_seen[char_id] if last_seen[char_id] > 0 else None
            upsert_count += 1

        db.commit()
        return SkillResult(
            self.name,
            metrics={
                "node_count": len(by_id),
                "edge_count": len(edges),
                "upsert_count": upsert_count,
                "stale_removed": len(stale_ids),
            },
        )

