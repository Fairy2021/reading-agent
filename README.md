# StoryVerse Agent

Immersive reading product scaffold for your "book -> interactive role story" idea.

Main stack:
- Backend: `Python + FastAPI`
- Data: `PostgreSQL + pgvector`
- Cache/Queue: `Redis + Celery`
- Frontend: `Next.js`

## Project Layout

```text
backend/                FastAPI API + SQLAlchemy models + Celery tasks
frontend/               Next.js app scaffold
infra/postgres/         pgvector init SQL
docs/                   PRD, architecture, and issue backlog
docker-compose.yml      Local full-stack orchestration
```

## Quick Start

1. Copy environment template:
```bash
cp .env.example .env
```

For roleplay LLM (OpenAI-compatible endpoint), set in `.env`:
```bash
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://open.xiaojingai.com/v1
OPENAI_MODEL=gpt-4o
```

2. Start all services:
```bash
docker compose up --build
```

3. Open:
- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/healthz`
- LLM connectivity check: `http://localhost:8000/api/healthz/llm`

## Current API Skeleton

- `GET /api/healthz`
- `POST /api/books/upload` (`multipart/form-data`, supports `.txt`)
- `POST /api/books`
- `GET /api/books`
- `POST /api/books/{book_id}/ingest?file_path=...`
- `POST /api/books/{book_id}/embed`
- `POST /api/books/{book_id}/skills/run`
- `POST /api/chat`
- `GET /api/books/tasks/{task_id}`
- `GET /api/books/{book_id}/chapters`
- `GET /api/books/{book_id}/chapters/{chapter_index}`
- `GET /api/books/{book_id}/characters`
- `GET /api/books/{book_id}/characters/{character_id}`
- `GET /api/books/{book_id}/graph`

## Quick Smoke Test with Hongloumeng

PowerShell:

```powershell
$resp = curl.exe -s -X POST "http://localhost:8000/api/books/upload" `
  -F "title=红楼梦" `
  -F "file=@D:/Code/26workpre/agent/booktxt/hongloumeng.txt"

$resp
```

The response includes `task_id` and `book_id`.

Check task status:

```powershell
curl.exe -s "http://localhost:8000/api/books/tasks/<task_id>"
```

List chapters:

```powershell
curl.exe -s "http://localhost:8000/api/books/<book_id>/chapters"
```

Read chapter 1:

```powershell
curl.exe -s "http://localhost:8000/api/books/<book_id>/chapters/1"
```

## Notes for Personal Laptop

- Celery worker is configured with low concurrency (`--concurrency=1`).
- Redis uses max memory guard (`256mb`).
- LLM/VLM should be called via cloud API in early stages.

## Product Planning Docs

- [MVP PRD](docs/MVP-PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Issue Backlog](docs/ISSUE-BACKLOG.md)
- [RAG Guide (ZH)](docs/RAG-GUIDE-ZH.md)
- [Skills Pipeline (ZH)](docs/SKILLS-PIPELINE-ZH.md)
