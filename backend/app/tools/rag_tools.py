from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, RelationshipEdge, RelationshipGraphNodeMetric
from app.services.embedding import embed_text
from app.services.rag import Evidence, retrieve_story_evidence


def embedding_tool(text: str) -> list[float]:
    return embed_text(text)


def retrieval_tool(
    db: Session,
    *,
    book_id: str,
    query: str,
    max_chapter_index: int,
    top_k: int = 6,
) -> list[Evidence]:
    return retrieve_story_evidence(
        db,
        book_id=book_id,
        query=query,
        max_chapter_index=max_chapter_index,
        top_k=top_k,
    )


@dataclass
class GraphSnapshot:
    node_count: int
    edge_count: int
    top_nodes: list[dict]
    relation_types: dict[str, int]


def graph_query_tool(
    db: Session,
    *,
    book_id: str,
    limit_nodes: int = 12,
) -> GraphSnapshot:
    rows = db.execute(
        select(RelationshipGraphNodeMetric, Character.canonical_name)
        .join(Character, Character.id == RelationshipGraphNodeMetric.character_id)
        .where(RelationshipGraphNodeMetric.book_id == book_id)
        .order_by(
            RelationshipGraphNodeMetric.weighted_degree.desc(),
            RelationshipGraphNodeMetric.degree.desc(),
        )
        .limit(limit_nodes)
    ).all()

    top_nodes: list[dict] = []
    for metric, name in rows:
        top_nodes.append(
            {
                "character_id": metric.character_id,
                "name": name,
                "degree": metric.degree,
                "weighted_degree": metric.weighted_degree,
                "relation_diversity": metric.relation_diversity,
            }
        )

    edge_rows = db.execute(
        select(RelationshipEdge.relation_type)
        .where(RelationshipEdge.book_id == book_id)
    ).all()
    relation_types: dict[str, int] = {}
    for (relation_type,) in edge_rows:
        key = (relation_type or "other").strip() or "other"
        relation_types[key] = relation_types.get(key, 0) + 1

    node_count = db.execute(
        select(RelationshipGraphNodeMetric.id).where(RelationshipGraphNodeMetric.book_id == book_id)
    ).scalars().all()
    edge_count = db.execute(
        select(RelationshipEdge.id).where(RelationshipEdge.book_id == book_id)
    ).scalars().all()

    return GraphSnapshot(
        node_count=len(node_count),
        edge_count=len(edge_count),
        top_nodes=top_nodes,
        relation_types=relation_types,
    )
