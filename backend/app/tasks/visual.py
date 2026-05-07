from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AssetJob, Character, MediaAsset
from app.services import generate_character_portrait
from app.services.image_service import cache_remote_portrait
from app.skills.character_portrait_unlock import build_style_prompt
from app.tools import (
    build_visual_style_clause,
    ensure_visual_style_profile,
    get_scene_evidence_snippets,
)
from app.worker.celery_app import celery_app


@celery_app.task(name="visual.generate_asset", queue="visual")
def generate_visual_asset_task(job_id: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        job = db.get(AssetJob, job_id)
        if not job:
            return {"job_id": job_id, "status": "failed", "reason": "job not found"}
        supported_types = {"portrait", "character_card", "scene"}
        if job.asset_type not in supported_types:
            job.status = "failed"
            job.error_message = "unsupported asset_type"
            db.commit()
            return {"job_id": job_id, "status": "failed", "reason": "unsupported asset_type"}
        if job.asset_type in {"portrait", "character_card"} and not job.character_id:
            job.status = "failed"
            job.error_message = "character_id is required for portrait/character_card"
            db.commit()
            return {"job_id": job_id, "status": "failed", "reason": "missing character_id"}

        character = None
        if job.character_id:
            character = db.get(Character, job.character_id)
            if not character and job.asset_type in {"portrait", "character_card"}:
                job.status = "failed"
                job.error_message = "character not found"
                db.commit()
                return {"job_id": job_id, "status": "failed", "reason": "character not found"}

        profile = ensure_visual_style_profile(db, book_id=job.book_id)
        style_clause = build_visual_style_clause(profile)

        if not job.style_prompt and job.asset_type in {"portrait", "character_card"}:
            db.refresh(character, attribute_names=["card", "evidences"])
            job.style_prompt = build_style_prompt(character)
            db.commit()
        if job.asset_type == "character_card":
            name = character.canonical_name if character else "角色"
            job.style_prompt = (
                f"{job.style_prompt}\n"
                f"请绘制古风角色卡，主体是{name}，竖版构图，留有标题与简介区域，"
                f"整体风格统一为国风水墨，不要出现现代元素。\n{style_clause}"
            ).strip()
            db.commit()
        if job.asset_type == "portrait":
            job.style_prompt = f"{job.style_prompt}\n{style_clause}".strip()
            db.commit()
        if job.asset_type == "scene" and not job.style_prompt:
            chapter_part = f"第{job.chapter_index}章" if job.chapter_index else "当前剧情"
            evidence_lines = get_scene_evidence_snippets(
                db,
                book_id=job.book_id,
                chapter_index=job.chapter_index,
                max_items=3,
            )
            evidence_block = "\n".join(f"- {line}" for line in evidence_lines) if evidence_lines else "- 无可用章节片段"
            job.style_prompt = (
                f"请绘制古风小说场景概念图，基于{chapter_part}，水墨写意风格，避免现代元素。\n"
                f"章节证据：\n{evidence_block}\n{style_clause}"
            )
            db.commit()

        job.status = "running"
        db.commit()

        try:
            image_url, generator = generate_character_portrait(
                book_id=job.book_id,
                character_id=job.character_id or "scene",
                prompt=job.style_prompt,
            )
            cached_url = cache_remote_portrait(
                image_url=image_url,
                book_id=job.book_id,
                character_id=job.character_id or "scene",
            )
            if cached_url:
                image_url = cached_url
        except Exception as exc:  # noqa: PERF203
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

        latest = db.execute(
            select(MediaAsset.version)
            .where(
                MediaAsset.book_id == job.book_id,
                MediaAsset.character_id == job.character_id,
                MediaAsset.asset_type == job.asset_type,
            )
            .order_by(MediaAsset.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        next_version = int(latest or 0) + 1

        asset = MediaAsset(
            book_id=job.book_id,
            character_id=job.character_id,
            asset_type=job.asset_type,
            chapter_index=job.chapter_index,
            style_prompt=job.style_prompt,
            storage_url=image_url,
            generator=generator or settings.portrait_generator_name,
            status="ready",
            version=next_version,
            created_by_agent="visual-agent",
        )
        db.add(asset)
        db.flush()

        job.status = "completed"
        job.result_asset_id = asset.id
        job.error_message = ""
        db.commit()
        return {
            "job_id": job_id,
            "book_id": job.book_id,
            "status": "completed",
            "asset_id": asset.id,
            "storage_url": image_url,
        }
    finally:
        db.close()
