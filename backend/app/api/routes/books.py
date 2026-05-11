import os
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AssetJob,
    Book,
    Chapter,
    Character,
    MediaAsset,
    CharacterPortrait,
    CharacterState,
    RelationshipEdge,
    RelationshipGraphNodeMetric,
)
from app.schemas.book import (
    BookCreateRequest,
    BookResponse,
    ChapterDetailResponse,
    ChapterSummaryResponse,
    EnqueueResponse,
    MediaAssetResponse,
    VisualJobCreateResponse,
    VisualJobCreateRequest,
    VisualJobStatusResponse,
    VisualStyleProfileResponse,
    VisualStyleProfileUpdateRequest,
)
from app.schemas.character import (
    CharacterCardResponse,
    CharacterDetailResponse,
    CharacterEvidenceResponse,
    CharacterPortraitResponse,
    CharacterStateResponse,
    CharacterSummaryResponse,
    RelationshipGraphNodeMetricResponse,
    RelationshipEdgeResponse,
    SkillRunRequest,
)
from app.tasks.ingest import (
    build_embeddings_task,
    generate_portrait_task,
    ingest_book_task,
    run_book_skills_task,
)
from app.tasks.visual import generate_visual_asset_task
from app.skills.character_portrait_unlock import build_style_prompt
from app.worker.celery_app import celery_app
from app.tools import ensure_visual_style_profile

router = APIRouter()


def _to_json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    return str(value)


@router.post("", response_model=BookResponse)
def create_book(payload: BookCreateRequest, db: Session = Depends(get_db)) -> Book:
    book = Book(title=payload.title)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.get("", response_model=list[BookResponse])
def list_books(db: Session = Depends(get_db)) -> list[Book]:
    stmt = select(Book).order_by(Book.created_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("/{book_id}/ingest", response_model=EnqueueResponse)
def enqueue_ingest(book_id: str, file_path: str, db: Session = Depends(get_db)) -> EnqueueResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not Path(file_path).exists():
        raise HTTPException(status_code=400, detail="file_path does not exist")

    task = ingest_book_task.delay(book_id=book_id, file_path=file_path)
    book.status = "processing"
    db.commit()
    return EnqueueResponse(task_id=task.id, book_id=book_id)


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    payload: dict = {"task_id": task_id, "status": result.status}
    if result.ready():
        payload["result"] = _to_json_safe(result.result)
    return payload


@router.post("/upload", response_model=EnqueueResponse)
async def upload_and_enqueue_ingest(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> EnqueueResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported in MVP")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower()
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = upload_dir / saved_name

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    saved_path.write_bytes(file_bytes)

    book_title = (title or os.path.splitext(file.filename)[0]).strip()
    if not book_title:
        book_title = "Untitled Book"

    book = Book(title=book_title, source_type="user_upload", status="processing")
    db.add(book)
    db.commit()
    db.refresh(book)

    task = ingest_book_task.delay(book_id=book.id, file_path=str(saved_path))
    return EnqueueResponse(task_id=task.id, book_id=book.id)


@router.post("/{book_id}/embed", response_model=EnqueueResponse)
def enqueue_embeddings(book_id: str, db: Session = Depends(get_db)) -> EnqueueResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    task = build_embeddings_task.delay(book_id=book_id)
    return EnqueueResponse(task_id=task.id, book_id=book_id)


@router.post("/{book_id}/skills/run", response_model=EnqueueResponse)
def enqueue_skill_pipeline(
    book_id: str,
    payload: SkillRunRequest | None = None,
    db: Session = Depends(get_db),
) -> EnqueueResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    task = run_book_skills_task.delay(
        book_id=book_id,
        skill_names=payload.skill_names if payload else None,
        max_chapter_index=payload.chapter_index if payload else None,
        incremental=payload.incremental if payload else settings.skill_default_incremental,
    )
    return EnqueueResponse(task_id=task.id, book_id=book_id)


@router.get("/{book_id}/chapters", response_model=list[ChapterSummaryResponse])
def list_chapters(book_id: str, db: Session = Depends(get_db)) -> list[Chapter]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stmt = select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
    return list(db.execute(stmt).scalars().all())


@router.get("/{book_id}/chapters/{chapter_index}", response_model=ChapterDetailResponse)
def get_chapter(book_id: str, chapter_index: int, db: Session = Depends(get_db)) -> Chapter:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stmt = (
        select(Chapter)
        .where(Chapter.book_id == book_id, Chapter.chapter_index == chapter_index)
        .limit(1)
    )
    chapter = db.execute(stmt).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.get("/{book_id}/characters", response_model=list[CharacterSummaryResponse])
def list_characters(
    book_id: str,
    include_unverified: bool = False,
    db: Session = Depends(get_db),
) -> list[CharacterSummaryResponse]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stmt = (
        select(Character)
        .where(Character.book_id == book_id)
        .options(selectinload(Character.aliases), selectinload(Character.card))
        .order_by(Character.mention_count.desc(), Character.canonical_name.asc())
    )
    if not include_unverified:
        stmt = stmt.where(Character.is_verified.is_(True))
    characters = list(db.execute(stmt).scalars())

    payload: list[CharacterSummaryResponse] = []
    for character in characters:
        payload.append(
            CharacterSummaryResponse(
                id=character.id,
                canonical_name=character.canonical_name,
                first_chapter_index=character.first_chapter_index,
                mention_count=character.mention_count,
                confidence=character.confidence,
                is_verified=character.is_verified,
                aliases=[a.alias for a in character.aliases],
                card_preview=(
                    character.card.personality_summary[:160] if character.card else None
                ),
            )
        )
    return payload


@router.get("/{book_id}/characters/{character_id}", response_model=CharacterDetailResponse)
def get_character_detail(
    book_id: str,
    character_id: str,
    db: Session = Depends(get_db),
) -> CharacterDetailResponse:
    character = db.get(Character, character_id)
    if not character or character.book_id != book_id:
        raise HTTPException(status_code=404, detail="Character not found")

    db.refresh(character, attribute_names=["aliases", "card", "evidences", "states"])
    card_payload = None
    if character.card:
        card_payload = CharacterCardResponse(
            identity_summary=character.card.identity_summary,
            personality_summary=character.card.personality_summary,
            speaking_style=character.card.speaking_style,
            values_and_taboo=character.card.values_and_taboo,
        )

    latest_state = db.execute(
        select(CharacterState)
        .where(CharacterState.character_id == character.id)
        .order_by(CharacterState.chapter_index.desc())
        .limit(1)
    ).scalars().first()

    evidences = sorted(character.evidences, key=lambda x: x.chapter_index)[:12]
    evidence_payload = [
        CharacterEvidenceResponse(
            chapter_index=e.chapter_index,
            excerpt=e.excerpt,
            evidence_type=e.evidence_type,
        )
        for e in evidences
    ]

    return CharacterDetailResponse(
        id=character.id,
        canonical_name=character.canonical_name,
        first_chapter_index=character.first_chapter_index,
        mention_count=character.mention_count,
        confidence=character.confidence,
        is_verified=character.is_verified,
        aliases=[a.alias for a in character.aliases],
        card=card_payload,
        latest_state=(
            CharacterStateResponse(
                chapter_index=latest_state.chapter_index,
                emotional_state=latest_state.emotional_state,
                stance=latest_state.stance,
                current_goal=latest_state.current_goal,
                relation_snapshot=latest_state.relation_snapshot,
            )
            if latest_state
            else None
        ),
        evidences=evidence_payload,
    )


@router.get("/{book_id}/graph", response_model=list[RelationshipEdgeResponse])
def get_relationship_graph(book_id: str, db: Session = Depends(get_db)) -> list[RelationshipEdgeResponse]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    source_char = aliased(Character)
    target_char = aliased(Character)
    rows = db.execute(
        select(RelationshipEdge, source_char.canonical_name, target_char.canonical_name)
        .join(source_char, source_char.id == RelationshipEdge.source_character_id)
        .join(target_char, target_char.id == RelationshipEdge.target_character_id)
        .where(RelationshipEdge.book_id == book_id)
        .order_by(RelationshipEdge.strength.desc(), RelationshipEdge.relation_type.asc())
    ).all()

    payload: list[RelationshipEdgeResponse] = []
    for edge, source_name, target_name in rows:
        payload.append(
            RelationshipEdgeResponse(
                id=edge.id,
                source_character_id=edge.source_character_id,
                source_name=source_name,
                target_character_id=edge.target_character_id,
                target_name=target_name,
                relation_type=edge.relation_type,
                strength=edge.strength,
                first_chapter_index=edge.first_chapter_index,
                last_chapter_index=edge.last_chapter_index,
                evidence_excerpt=edge.evidence_excerpt,
            )
        )
    return payload


@router.get("/{book_id}/graph/nodes", response_model=list[RelationshipGraphNodeMetricResponse])
def get_relationship_graph_nodes(
    book_id: str,
    db: Session = Depends(get_db),
) -> list[RelationshipGraphNodeMetricResponse]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    rows = db.execute(
        select(RelationshipGraphNodeMetric, Character.canonical_name)
        .join(Character, Character.id == RelationshipGraphNodeMetric.character_id)
        .where(RelationshipGraphNodeMetric.book_id == book_id)
        .order_by(
            RelationshipGraphNodeMetric.weighted_degree.desc(),
            RelationshipGraphNodeMetric.degree.desc(),
            Character.canonical_name.asc(),
        )
    ).all()

    payload: list[RelationshipGraphNodeMetricResponse] = []
    for metric, name in rows:
        payload.append(
            RelationshipGraphNodeMetricResponse(
                character_id=metric.character_id,
                canonical_name=name,
                degree=metric.degree,
                in_degree=metric.in_degree,
                out_degree=metric.out_degree,
                weighted_degree=metric.weighted_degree,
                relation_diversity=metric.relation_diversity,
                last_chapter_index=metric.last_chapter_index,
            )
        )
    return payload


@router.get("/{book_id}/portraits", response_model=list[CharacterPortraitResponse])
def list_character_portraits(
    book_id: str,
    status: str | None = None,
    character_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[CharacterPortraitResponse]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stmt = (
        select(CharacterPortrait, Character.canonical_name)
        .join(Character, Character.id == CharacterPortrait.character_id)
        .where(CharacterPortrait.book_id == book_id)
    )
    if status:
        stmt = stmt.where(CharacterPortrait.status == status)
    if character_id:
        stmt = stmt.where(CharacterPortrait.character_id == character_id)
    rows = db.execute(
        stmt.order_by(
            CharacterPortrait.unlocked_chapter_index.asc(),
            CharacterPortrait.updated_at.desc(),
            Character.canonical_name.asc(),
        )
    ).all()

    payload: list[CharacterPortraitResponse] = []
    for portrait, name in rows:
        payload.append(
            CharacterPortraitResponse(
                id=portrait.id,
                character_id=portrait.character_id,
                canonical_name=name,
                unlocked_chapter_index=portrait.unlocked_chapter_index,
                status=portrait.status,
                style_prompt=portrait.style_prompt,
                image_url=portrait.image_url,
                generator=portrait.generator,
            )
        )
    return payload


@router.post("/{book_id}/characters/{character_id}/portrait/generate", response_model=EnqueueResponse)
def enqueue_character_portrait_generation(
    book_id: str,
    character_id: str,
    db: Session = Depends(get_db),
) -> EnqueueResponse:
    character = db.get(Character, character_id)
    if not character or character.book_id != book_id:
        raise HTTPException(status_code=404, detail="Character not found")

    db.refresh(character, attribute_names=["card", "evidences"])
    style_prompt = build_style_prompt(character)

    portrait = db.execute(
        select(CharacterPortrait).where(
            CharacterPortrait.book_id == book_id,
            CharacterPortrait.character_id == character_id,
        )
    ).scalars().first()

    unlock_index = character.first_chapter_index or 1
    if portrait is None:
        portrait = CharacterPortrait(
            book_id=book_id,
            character_id=character_id,
            unlocked_chapter_index=unlock_index,
            status="queued",
            style_prompt=style_prompt,
            generator="pending",
        )
        db.add(portrait)
        db.commit()
        db.refresh(portrait)
    else:
        portrait.unlocked_chapter_index = min(portrait.unlocked_chapter_index, unlock_index)
        portrait.style_prompt = style_prompt
        if portrait.status not in {"queued", "generating"}:
            portrait.status = "queued"
        db.commit()
        db.refresh(portrait)

    task = generate_portrait_task.delay(portrait_id=portrait.id)
    return EnqueueResponse(task_id=task.id, book_id=book_id, status="queued")


@router.post("/{book_id}/visual/portrait/jobs/{character_id}", response_model=VisualJobCreateResponse)
def enqueue_visual_portrait_job(
    book_id: str,
    character_id: str,
    chapter_index: int | None = None,
    progress_chapter: int | None = None,
    db: Session = Depends(get_db),
) -> VisualJobCreateResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    character = db.get(Character, character_id)
    if not character or character.book_id != book_id:
        raise HTTPException(status_code=404, detail="Character not found")
    unlock_chapter = character.first_chapter_index or 1
    if progress_chapter is not None and progress_chapter < unlock_chapter:
        raise HTTPException(
            status_code=403,
            detail=f"Character is locked until chapter {unlock_chapter}",
        )

    requested_chapter = chapter_index or unlock_chapter
    idempotency_key = f"portrait:{book_id}:{character_id}:{requested_chapter}"
    existing = db.execute(
        select(AssetJob).where(
            AssetJob.book_id == book_id,
            AssetJob.idempotency_key == idempotency_key,
        )
    ).scalars().first()
    if existing and existing.status in {"queued", "running", "completed"}:
        return VisualJobCreateResponse(
            task_id=existing.task_id,
            job_id=existing.id,
            book_id=book_id,
            status=existing.status,
        )

    db.refresh(character, attribute_names=["card", "evidences"])
    prompt = build_style_prompt(character)
    if existing:
        existing.asset_type = "portrait"
        existing.character_id = character_id
        existing.chapter_index = requested_chapter
        existing.style_prompt = prompt
        existing.status = "queued"
        existing.error_message = ""
        job = existing
    else:
        job = AssetJob(
            book_id=book_id,
            character_id=character_id,
            asset_type="portrait",
            chapter_index=requested_chapter,
            style_prompt=prompt,
            status="queued",
            priority=5,
            idempotency_key=idempotency_key,
        )
        db.add(job)
    db.commit()
    db.refresh(job)

    task = generate_visual_asset_task.delay(job_id=job.id)
    job.task_id = task.id
    db.commit()
    db.refresh(job)
    return VisualJobCreateResponse(task_id=task.id, job_id=job.id, book_id=book_id, status=job.status)


@router.post("/{book_id}/visual/jobs", response_model=VisualJobCreateResponse)
def enqueue_visual_job(
    book_id: str,
    payload: VisualJobCreateRequest,
    db: Session = Depends(get_db),
) -> VisualJobCreateResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if payload.asset_type not in {"portrait", "character_card", "scene"}:
        raise HTTPException(status_code=400, detail="asset_type not supported")
    if payload.asset_type in {"portrait", "character_card"} and not payload.character_id:
        raise HTTPException(status_code=400, detail="character_id is required")

    character = None
    if payload.character_id:
        character = db.get(Character, payload.character_id)
        if not character or character.book_id != book_id:
            raise HTTPException(status_code=404, detail="Character not found")

    chapter_index = payload.chapter_index or (character.first_chapter_index if character else 1) or 1
    style_prompt = (payload.style_prompt or "").strip()
    if not style_prompt and character and payload.asset_type in {"portrait", "character_card"}:
        db.refresh(character, attribute_names=["card", "evidences"])
        style_prompt = build_style_prompt(character)

    idem_character = payload.character_id or "none"
    idempotency_key = f"{payload.asset_type}:{book_id}:{idem_character}:{chapter_index}:{hash(style_prompt)}"
    existing = db.execute(
        select(AssetJob).where(
            AssetJob.book_id == book_id,
            AssetJob.idempotency_key == idempotency_key,
        )
    ).scalars().first()
    if existing and existing.status in {"queued", "running", "completed"}:
        return VisualJobCreateResponse(
            task_id=existing.task_id,
            job_id=existing.id,
            book_id=book_id,
            status=existing.status,
        )

    if existing:
        job = existing
        job.asset_type = payload.asset_type
        job.character_id = payload.character_id
        job.chapter_index = chapter_index
        job.style_prompt = style_prompt
        job.status = "queued"
        job.priority = payload.priority
        job.error_message = ""
    else:
        job = AssetJob(
            book_id=book_id,
            character_id=payload.character_id,
            asset_type=payload.asset_type,
            chapter_index=chapter_index,
            style_prompt=style_prompt,
            status="queued",
            priority=payload.priority,
            idempotency_key=idempotency_key,
        )
        db.add(job)
    db.commit()
    db.refresh(job)

    task = generate_visual_asset_task.delay(job_id=job.id)
    job.task_id = task.id
    db.commit()
    db.refresh(job)
    return VisualJobCreateResponse(task_id=task.id, job_id=job.id, book_id=book_id, status=job.status)


@router.post("/{book_id}/visual/portraits/bootstrap")
def bootstrap_top_portraits(
    book_id: str, limit: int = 5, db: Session = Depends(get_db)
) -> dict[str, str | int]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stmt = (
        select(Character)
        .where(Character.book_id == book_id, Character.is_verified.is_(True))
        .order_by(Character.mention_count.desc(), Character.first_chapter_index.asc().nullslast(), Character.canonical_name.asc())
        .limit(max(1, min(limit, 20)))
    )
    characters = list(db.execute(stmt).scalars().all())
    enqueued = 0
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    for character in characters:
        requested_chapter = character.first_chapter_index or 1
        idempotency_key = f"portrait:{book_id}:{character.id}:{requested_chapter}"
        existing = db.execute(
            select(AssetJob).where(
                AssetJob.book_id == book_id,
                AssetJob.idempotency_key == idempotency_key,
            )
        ).scalars().first()
        if existing and existing.status in {"queued", "running", "completed"}:
            if existing.status == "completed":
                continue
            if existing.updated_at and existing.updated_at >= stale_cutoff:
                continue

        db.refresh(character, attribute_names=["card", "evidences"])
        prompt = build_style_prompt(character)
        if existing:
            job = existing
            job.asset_type = "portrait"
            job.character_id = character.id
            job.chapter_index = requested_chapter
            job.style_prompt = prompt
            job.status = "queued"
            job.error_message = ""
        else:
            job = AssetJob(
                book_id=book_id,
                character_id=character.id,
                asset_type="portrait",
                chapter_index=requested_chapter,
                style_prompt=prompt,
                status="queued",
                priority=5,
                idempotency_key=idempotency_key,
            )
            db.add(job)
        db.commit()
        db.refresh(job)
        task = generate_visual_asset_task.delay(job_id=job.id)
        job.task_id = task.id
        db.commit()
        enqueued += 1

    return {"book_id": book_id, "limit": limit, "enqueued": enqueued}


@router.get("/{book_id}/visual/jobs/{job_id}", response_model=VisualJobStatusResponse)
def get_visual_job_status(
    book_id: str,
    job_id: str,
    db: Session = Depends(get_db),
) -> VisualJobStatusResponse:
    job = db.get(AssetJob, job_id)
    if not job or job.book_id != book_id:
        raise HTTPException(status_code=404, detail="Visual job not found")

    if job.task_id and job.status in {"queued", "running"}:
        result = AsyncResult(job.task_id, app=celery_app)
        if result.ready() and job.status != "completed":
            refreshed = db.get(AssetJob, job_id)
            job = refreshed or job

    return VisualJobStatusResponse(
        job_id=job.id,
        book_id=job.book_id,
        asset_type=job.asset_type,
        status=job.status,
        task_id=job.task_id,
        result_asset_id=job.result_asset_id,
        error_message=job.error_message or "",
    )


@router.get("/{book_id}/visual/assets", response_model=list[MediaAssetResponse])
def list_media_assets(
    book_id: str,
    asset_type: str | None = None,
    character_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[MediaAssetResponse]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    stmt = select(MediaAsset).where(MediaAsset.book_id == book_id)
    if asset_type:
        stmt = stmt.where(MediaAsset.asset_type == asset_type)
    if character_id:
        stmt = stmt.where(MediaAsset.character_id == character_id)
    rows = db.execute(stmt.order_by(MediaAsset.updated_at.desc(), MediaAsset.version.desc())).scalars().all()
    return [
        MediaAssetResponse(
            id=item.id,
            book_id=item.book_id,
            character_id=item.character_id,
            asset_type=item.asset_type,
            chapter_index=item.chapter_index,
            status=item.status,
            style_prompt=item.style_prompt,
            storage_url=item.storage_url,
            generator=item.generator,
            version=item.version,
        )
        for item in rows
    ]


@router.get("/{book_id}/visual/style-profile", response_model=VisualStyleProfileResponse)
def get_visual_style_profile(book_id: str, db: Session = Depends(get_db)) -> VisualStyleProfileResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    profile = ensure_visual_style_profile(db, book_id=book_id)
    return VisualStyleProfileResponse(
        id=profile.id,
        book_id=profile.book_id,
        style_name=profile.style_name,
        palette=profile.palette,
        brush=profile.brush,
        mood=profile.mood,
        negative_prompt=profile.negative_prompt,
        locked=profile.locked,
    )


@router.put("/{book_id}/visual/style-profile", response_model=VisualStyleProfileResponse)
def update_visual_style_profile(
    book_id: str,
    payload: VisualStyleProfileUpdateRequest,
    db: Session = Depends(get_db),
) -> VisualStyleProfileResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    profile = ensure_visual_style_profile(db, book_id=book_id)
    if payload.style_name is not None:
        profile.style_name = payload.style_name
    if payload.palette is not None:
        profile.palette = payload.palette
    if payload.brush is not None:
        profile.brush = payload.brush
    if payload.mood is not None:
        profile.mood = payload.mood
    if payload.negative_prompt is not None:
        profile.negative_prompt = payload.negative_prompt
    if payload.locked is not None:
        profile.locked = payload.locked
    db.commit()
    db.refresh(profile)
    return VisualStyleProfileResponse(
        id=profile.id,
        book_id=profile.book_id,
        style_name=profile.style_name,
        palette=profile.palette,
        brush=profile.brush,
        mood=profile.mood,
        negative_prompt=profile.negative_prompt,
        locked=profile.locked,
    )
