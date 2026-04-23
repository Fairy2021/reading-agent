from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Chapter, ChapterChunk
from app.services.rag import retrieve_story_evidence

SENTENCE_SPLIT = re.compile(r"[\u3002\uFF01\uFF1F!?;\uFF1B\n]")


@dataclass
class QuerySample:
    chapter_index: int
    chapter_title: str
    query: str
    mode: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pick_query_from_chapter_text(title: str, text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return title or ""

    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if lines and title and lines[0] == title.strip():
        normalized = "\n".join(lines[1:]).strip()
    if not normalized:
        normalized = text.strip()

    for sentence in SENTENCE_SPLIT.split(normalized):
        s = sentence.strip()
        if 16 <= len(s) <= 120:
            return s
    return normalized[:80]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (k - lower)


def _build_samples(
    chapters: list[Chapter],
    *,
    mode: str,
) -> list[QuerySample]:
    samples: list[QuerySample] = []
    for ch in chapters:
        if mode == "chapter_title":
            query = (ch.title or "").strip()
        elif mode == "content_sentence":
            query = _pick_query_from_chapter_text(ch.title or "", ch.raw_text or "")
        else:
            raise ValueError(f"unsupported mode: {mode}")
        query = query.strip()
        if not query:
            continue
        samples.append(
            QuerySample(
                chapter_index=ch.chapter_index,
                chapter_title=ch.title or "",
                query=query,
                mode=mode,
            )
        )
    return samples


def _evaluate_mode(
    *,
    book_id: str,
    samples: list[QuerySample],
    top_k_list: list[int],
) -> dict:
    max_k = max(top_k_list)
    if not samples:
        return {
            "mode": "unknown",
            "sample_count": 0,
            "recall_at_k": {str(k): 0.0 for k in top_k_list},
            "mrr": 0.0,
            "latency_ms": {"mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0},
            "throughput_qps": 0.0,
        }

    rank_list: list[int] = []
    latency_ms: list[float] = []
    top1_scores: list[float] = []
    recall_hits = {k: 0 for k in top_k_list}
    no_result = 0
    spoiler_violation_count = 0

    db = SessionLocal()
    try:
        start_total = time.perf_counter()
        for sample in samples:
            t0 = time.perf_counter()
            evidences = retrieve_story_evidence(
                db,
                book_id=book_id,
                query=sample.query,
                max_chapter_index=sample.chapter_index,
                top_k=max_k,
            )
            t1 = time.perf_counter()
            latency_ms.append((t1 - t0) * 1000.0)

            if not evidences:
                no_result += 1
                rank_list.append(0)
                continue

            if any(ev.chapter_index > sample.chapter_index for ev in evidences):
                spoiler_violation_count += 1

            top1_scores.append(evidences[0].score)
            rank = 0
            for idx, ev in enumerate(evidences, start=1):
                if ev.chapter_index == sample.chapter_index:
                    rank = idx
                    break
            rank_list.append(rank)
            if rank <= 0:
                continue
            for k in top_k_list:
                if rank <= k:
                    recall_hits[k] += 1
        total_seconds = max(1e-9, time.perf_counter() - start_total)
    finally:
        db.close()

    sample_count = len(samples)
    recall_at_k = {
        str(k): round(recall_hits[k] / sample_count, 4) for k in top_k_list
    }
    mrr = round(
        sum((1.0 / r) for r in rank_list if r > 0) / sample_count,
        4,
    )
    sorted_latency = sorted(latency_ms)
    latency = {
        "mean": round(statistics.fmean(latency_ms), 3),
        "p50": round(_percentile(sorted_latency, 0.50), 3),
        "p90": round(_percentile(sorted_latency, 0.90), 3),
        "p95": round(_percentile(sorted_latency, 0.95), 3),
        "max": round(max(latency_ms), 3),
    }
    result = {
        "mode": samples[0].mode,
        "sample_count": sample_count,
        "no_result_count": no_result,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "top1_score_mean": round(statistics.fmean(top1_scores), 4) if top1_scores else 0.0,
        "spoiler_violation_count": spoiler_violation_count,
        "spoiler_violation_rate": round(spoiler_violation_count / sample_count, 4),
        "latency_ms": latency,
        "throughput_qps": round(sample_count / total_seconds, 3),
    }
    return result


def run_benchmark(
    *,
    book_id: str,
    max_chapter_index: int | None,
    sample_limit: int,
    top_k_list: list[int],
) -> dict:
    db = SessionLocal()
    try:
        stmt = select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
        if max_chapter_index is not None and max_chapter_index > 0:
            stmt = stmt.where(Chapter.chapter_index <= max_chapter_index)
        chapters = list(db.execute(stmt).scalars())
        if not chapters:
            raise RuntimeError("No chapters found for this book_id.")

        if sample_limit > 0:
            chapters = chapters[:sample_limit]

        chunk_stat = db.execute(
            select(
                func.count(ChapterChunk.id),
                func.avg(func.length(ChapterChunk.content)),
            )
            .join(Chapter, Chapter.id == ChapterChunk.chapter_id)
            .where(Chapter.book_id == book_id)
        ).one()
        chunk_count = int(chunk_stat[0] or 0)
        avg_chunk_chars = float(chunk_stat[1] or 0.0)
    finally:
        db.close()

    content_samples = _build_samples(chapters, mode="content_sentence")
    title_samples = _build_samples(chapters, mode="chapter_title")

    content_result = _evaluate_mode(
        book_id=book_id,
        samples=content_samples,
        top_k_list=top_k_list,
    )
    title_result = _evaluate_mode(
        book_id=book_id,
        samples=title_samples,
        top_k_list=top_k_list,
    )

    report = {
        "generated_at_utc": _now_iso(),
        "book_id": book_id,
        "chapter_count_evaluated": len(chapters),
        "chunk_count_total": chunk_count,
        "avg_chunk_chars": round(avg_chunk_chars, 2),
        "top_k_list": top_k_list,
        "results": [content_result, title_result],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG retrieval benchmark for StoryVerse.")
    parser.add_argument("--book-id", required=True, help="Target book id.")
    parser.add_argument("--max-chapter-index", type=int, default=0, help="Optional upper chapter bound.")
    parser.add_argument("--sample-limit", type=int, default=0, help="Only evaluate first N chapters if > 0.")
    parser.add_argument(
        "--top-k-list",
        default="1,3,5,10",
        help="Comma-separated K values, e.g. 1,3,5,10",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Write detailed benchmark json to file path.",
    )
    args = parser.parse_args()

    top_k_list = [int(x.strip()) for x in args.top_k_list.split(",") if x.strip()]
    top_k_list = sorted({k for k in top_k_list if k > 0})
    if not top_k_list:
        raise RuntimeError("top_k_list is empty")

    report = run_benchmark(
        book_id=args.book_id,
        max_chapter_index=args.max_chapter_index if args.max_chapter_index > 0 else None,
        sample_limit=max(0, args.sample_limit),
        top_k_list=top_k_list,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
