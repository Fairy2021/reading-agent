from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssetJob, Book, Character
from app.tasks.visual import generate_visual_asset_task


def execute_visual_agent(
    db: Session,
    *,
    book_id: str,
    asset_type: str,
    chapter_index: int | None,
    character_id: str | None,
    style_prompt: str = "",
) -> dict:
    book = db.get(Book, book_id)
    if not book:
        return {"status": "failed", "reason": "book_not_found"}
    if asset_type not in {"portrait", "character_card", "scene"}:
        return {"status": "failed", "reason": "asset_type_not_supported"}
    if asset_type in {"portrait", "character_card"}:
        if not character_id:
            return {"status": "failed", "reason": "character_id_required"}
        c = db.get(Character, character_id)
        if not c or c.book_id != book_id:
            return {"status": "failed", "reason": "character_not_found"}

    idem = f"{asset_type}:{book_id}:{character_id or 'none'}:{chapter_index or 1}:{hash(style_prompt)}"
    job = db.execute(
        select(AssetJob).where(AssetJob.book_id == book_id, AssetJob.idempotency_key == idem)
    ).scalars().first()
    if not job:
        job = AssetJob(
            book_id=book_id,
            character_id=character_id,
            asset_type=asset_type,
            chapter_index=chapter_index or 1,
            style_prompt=style_prompt,
            status="queued",
            idempotency_key=idem,
            priority=5,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    task = generate_visual_asset_task.delay(job_id=job.id)
    job.task_id = task.id
    if job.status not in {"running", "completed"}:
        job.status = "queued"
    db.commit()
    db.refresh(job)
    return {"status": job.status, "job_id": job.id, "task_id": job.task_id}
