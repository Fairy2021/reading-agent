from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Chapter, ChapterChunk, Character, RelationshipEdge
from app.services.embedding import embed_text
from app.services.rag import Evidence, retrieve_story_evidence

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
SENTENCE_SPLIT = re.compile(r"[\u3002\uFF01\uFF1F!?;\uFF1B\n]")
GENERIC_SENTENCE_TOKENS = {
    "根据证据",
    "相关章节",
    "可以看出",
    "综上",
    "无法确定",
    "信息不足",
}

RELATION_LABEL_MAP = {
    "kinship": "亲属",
    "friend": "朋友",
    "conflict": "对立",
    "master_servant": "主仆",
    "romance": "情感",
    "alliance": "同盟",
    "co_occurrence": "同场",
    "other": "关联",
}


@dataclass
class ChunkDoc:
    chunk_id: str
    chapter_index: int
    chapter_title: str
    chunk_index: int
    content: str
    tokens: list[str]
    tf: Counter[str]
    length: int


@dataclass
class QAItem:
    qid: str
    question: str
    chapter_index: int
    support_chapters: list[int]
    reference_answer: str = ""
    answer_keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalHit:
    chunk_id: str
    chapter_index: int
    chapter_title: str
    chunk_index: int
    content: str
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [m.group(0) for m in TOKEN_PATTERN.finditer(lowered) if m.group(0)]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _cn_numeral_to_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    has_unit = False
    for ch in token:
        if ch in digits:
            current = digits[ch]
        elif ch in units:
            has_unit = True
            u = units[ch]
            if current == 0:
                current = 1
            total += current * u
            current = 0
        else:
            return None
    total += current
    if total == 0 and not has_unit:
        return None
    return total


def _extract_chapter_hint(query: str) -> int | None:
    for m in re.finditer(r"第([零〇一二两三四五六七八九十百千0-9]+)(?:章|回)", query):
        maybe = _cn_numeral_to_int(m.group(1))
        if maybe is not None:
            return maybe
    return None


def _resolve_chat_url() -> str:
    base = (settings.openai_base_url or "").strip()
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return f"{base.rstrip('/')}/chat/completions"


def _post_llm(payload: dict) -> dict:
    api_url = _resolve_chat_url()
    if not api_url:
        raise RuntimeError("OPENAI_BASE_URL is empty")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }
    session = requests.Session()
    session.trust_env = False
    resp = session.post(api_url, headers=headers, json=payload, timeout=settings.llm_timeout_seconds)
    resp.raise_for_status()
    return resp.json()


def _extract_llm_text(data: dict) -> str:
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts).strip()
    return ""


def _parse_json_from_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", candidate)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


class BM25Index:
    def __init__(self, docs: list[ChunkDoc], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.doc_count = len(docs)
        self.avgdl = statistics.fmean([max(1, d.length) for d in docs]) if docs else 1.0
        self.df: Counter[str] = Counter()
        self.idf: dict[str, float] = {}
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._build()

    def _build(self) -> None:
        for idx, doc in enumerate(self.docs):
            seen: set[str] = set()
            for term, tf in doc.tf.items():
                self.postings[term].append((idx, tf))
                if term not in seen:
                    self.df[term] += 1
                    seen.add(term)
        n = self.doc_count
        for term, df in self.df.items():
            # BM25+ style idf stabilization.
            self.idf[term] = math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        *,
        max_chapter_index: int,
        top_k: int,
    ) -> list[RetrievalHit]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_terms = list(dict.fromkeys(q_tokens))
        scores: dict[int, float] = defaultdict(float)

        for term in q_terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_idx, tf in self.postings.get(term, []):
                doc = self.docs[doc_idx]
                if doc.chapter_index > max_chapter_index:
                    continue
                dl = max(1, doc.length)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                score = idf * ((tf * (self.k1 + 1.0)) / max(1e-9, denom))
                scores[doc_idx] += score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        hits: list[RetrievalHit] = []
        for doc_idx, score in ranked:
            doc = self.docs[doc_idx]
            hits.append(
                RetrievalHit(
                    chunk_id=doc.chunk_id,
                    chapter_index=doc.chapter_index,
                    chapter_title=doc.chapter_title,
                    chunk_index=doc.chunk_index,
                    content=doc.content,
                    bm25_score=float(score),
                )
            )
        return hits


def _load_chunk_docs(book_id: str) -> tuple[list[ChunkDoc], dict[str, ChunkDoc]]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(ChapterChunk, Chapter.chapter_index, Chapter.title)
            .join(Chapter, Chapter.id == ChapterChunk.chapter_id)
            .where(Chapter.book_id == book_id, ChapterChunk.embedding.is_not(None))
            .order_by(Chapter.chapter_index.asc(), ChapterChunk.chunk_index.asc())
        ).all()
    finally:
        db.close()

    docs: list[ChunkDoc] = []
    by_id: dict[str, ChunkDoc] = {}
    for chunk, chapter_index, chapter_title in rows:
        tokens = _tokenize(chunk.content or "")
        tf = Counter(tokens)
        doc = ChunkDoc(
            chunk_id=chunk.id,
            chapter_index=int(chapter_index),
            chapter_title=(chapter_title or "").strip(),
            chunk_index=int(chunk.chunk_index),
            content=chunk.content or "",
            tokens=tokens,
            tf=tf,
            length=max(1, len(tokens)),
        )
        docs.append(doc)
        by_id[doc.chunk_id] = doc
    return docs, by_id


def _retrieve_dense(book_id: str, query: str, max_chapter_index: int, top_k: int) -> list[RetrievalHit]:
    db = SessionLocal()
    try:
        evidences = retrieve_story_evidence(
            db,
            book_id=book_id,
            query=query,
            max_chapter_index=max_chapter_index,
            top_k=top_k,
        )
    finally:
        db.close()

    hits: list[RetrievalHit] = []
    for ev in evidences:
        hits.append(
            RetrievalHit(
                chunk_id=ev.chunk_id,
                chapter_index=ev.chapter_index,
                chapter_title=ev.chapter_title,
                chunk_index=ev.chunk_index,
                content=ev.content,
                dense_score=ev.score,
            )
        )
    return hits


def _rrf_fuse(
    dense_hits: list[RetrievalHit],
    bm25_hits: list[RetrievalHit],
    *,
    rrf_k: int = 60,
) -> list[RetrievalHit]:
    score_by_id: dict[str, float] = defaultdict(float)
    by_id: dict[str, RetrievalHit] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        score_by_id[hit.chunk_id] += 1.0 / (rrf_k + rank)
        by_id.setdefault(hit.chunk_id, hit)
    for rank, hit in enumerate(bm25_hits, start=1):
        score_by_id[hit.chunk_id] += 1.0 / (rrf_k + rank)
        existing = by_id.get(hit.chunk_id)
        if existing is None:
            by_id[hit.chunk_id] = hit
        else:
            if hit.bm25_score > 0:
                existing.bm25_score = hit.bm25_score
    for hit in by_id.values():
        hit.rrf_score = score_by_id[hit.chunk_id]

    return sorted(by_id.values(), key=lambda h: h.rrf_score, reverse=True)


def _heuristic_rerank(
    candidates: list[RetrievalHit],
    *,
    query: str,
    by_chunk_id: dict[str, ChunkDoc],
    top_k: int,
) -> list[RetrievalHit]:
    if not candidates:
        return []
    q_tokens = set(_tokenize(query))
    chapter_hint = _extract_chapter_hint(query)
    max_rrf = max((h.rrf_score for h in candidates), default=1.0) or 1.0
    max_dense = max((h.dense_score for h in candidates), default=1.0) or 1.0
    max_bm25 = max((h.bm25_score for h in candidates), default=1.0) or 1.0

    for hit in candidates:
        doc = by_chunk_id.get(hit.chunk_id)
        overlap = 0.0
        if q_tokens and doc:
            doc_tokens = set(doc.tokens)
            overlap = len(q_tokens & doc_tokens) / max(1, len(q_tokens))

        title_bonus = 0.0
        if hit.chapter_title and hit.chapter_title in query:
            title_bonus += 0.5
        if chapter_hint is not None and hit.chapter_index == chapter_hint:
            title_bonus += 0.5

        score = (
            0.50 * (hit.rrf_score / max_rrf)
            + 0.20 * (hit.dense_score / max_dense)
            + 0.15 * (hit.bm25_score / max_bm25)
            + 0.10 * overlap
            + 0.05 * title_bonus
        )
        hit.rerank_score = score

    ranked = sorted(candidates, key=lambda h: h.rerank_score, reverse=True)
    return ranked[:top_k]


def _dedupe_hits_by_chapter(hits: list[RetrievalHit], max_items: int) -> list[RetrievalHit]:
    deduped: list[RetrievalHit] = []
    seen: set[int] = set()
    for hit in hits:
        if hit.chapter_index in seen:
            continue
        seen.add(hit.chapter_index)
        deduped.append(hit)
        if len(deduped) >= max_items:
            break
    return deduped


def _dcg(rels: list[int], k: int) -> float:
    total = 0.0
    for i, rel in enumerate(rels[:k], start=1):
        total += (2**rel - 1) / math.log2(i + 1)
    return total


def _format_latency(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    return {
        "avg": round(statistics.fmean(values), 3),
        "p50": round(_percentile(sorted_vals, 0.50), 3),
        "p95": round(_percentile(sorted_vals, 0.95), 3),
    }


def _generate_answer(question: str, hits: list[RetrievalHit], *, citation_k: int) -> tuple[str, list[RetrievalHit]]:
    citations = hits[: max(1, citation_k)]
    if not citations:
        return "当前检索不到可用证据，无法给出可靠回答。", []

    question_text = question.strip()
    if "关系" in question_text or "互动" in question_text:
        # Try a relation-style answer first so generation eval can reflect relation QA capability.
        name_candidates = re.findall(r"[\u4e00-\u9fff]{2,4}", question_text)
        stop_names = {"第章", "第回", "关系", "剧情", "线索", "证据", "标题", "主要", "包含"}
        names = [n for n in name_candidates if n not in stop_names]
        top = citations[0]
        snippet = top.content.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "..."
        pair = ""
        if len(names) >= 2:
            pair = f"{names[0]}与{names[1]}"
        elif len(names) == 1:
            pair = names[0]
        else:
            pair = "相关人物"

        relation_hint = "关联"
        if any(tok in snippet for tok in ["争", "恨", "骂", "怒", "冲突", "怨"]):
            relation_hint = "冲突/对立"
        elif any(tok in snippet for tok in ["亲", "母", "父", "兄", "姐", "妹", "夫人"]):
            relation_hint = "亲属/家族"
        elif any(tok in snippet for tok in ["侍", "丫鬟", "主子", "伺候", "奴"]):
            relation_hint = "主仆"
        elif any(tok in snippet for tok in ["情", "爱", "心", "思"]):
            relation_hint = "情感"

        answer = (
            f"根据检索证据，在第{top.chapter_index}章《{top.chapter_title}》中，"
            f"{pair}存在明显互动，关系更接近“{relation_hint}”。"
            f"可见证据：{snippet}"
        )
        return answer, citations

    top = citations[0]
    snippet = top.content.strip().replace("\n", " ")
    if len(snippet) > 120:
        snippet = snippet[:120] + "..."
    answer = (
        f"根据检索证据，最相关的是第{top.chapter_index}章《{top.chapter_title}》。"
        f"结合证据内容：{snippet}"
    )
    return answer, citations


def _evaluate_accuracy_keyword(answer: str, qa: QAItem, *, min_ratio: float = 0.6) -> bool:
    answer_text = answer.strip()
    if not answer_text:
        return False

    chapter_hit = any(
        f"第{idx}章" in answer_text or f"第{idx}回" in answer_text
        for idx in qa.support_chapters
    )

    if qa.answer_keywords:
        hit = sum(1 for kw in qa.answer_keywords if kw and kw in answer_text)
        ratio = hit / max(1, len(qa.answer_keywords))
        keyword_ok = ratio >= min_ratio
    elif qa.reference_answer:
        keyword_ok = qa.reference_answer[:20] in answer_text or qa.reference_answer in answer_text
    else:
        keyword_ok = chapter_hit

    return chapter_hit and keyword_ok


def _evaluate_accuracy_llm(question: str, answer: str, qa: QAItem) -> tuple[bool, str]:
    prompt = (
        "你是严格的阅读问答评测器。请判断预测答案是否正确。\n"
        "输出JSON: {\"correct\":true/false,\"reason\":\"\"}\n"
        f"问题: {question}\n"
        f"参考答案: {qa.reference_answer}\n"
        f"关键词: {qa.answer_keywords}\n"
        f"标准支持章节: {qa.support_chapters}\n"
        f"预测答案: {answer}\n"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    data = _post_llm(payload)
    text = _extract_llm_text(data)
    parsed = _parse_json_from_text(text)
    correct = bool(parsed.get("correct", False))
    reason = str(parsed.get("reason", "")).strip()
    return correct, reason


def _sentence_tokens(sentence: str) -> set[str]:
    return set(_tokenize(sentence))


def _evaluate_grounding_heuristic(answer: str, citations: list[RetrievalHit]) -> float:
    if not answer.strip():
        return 0.0
    evidence_text = " ".join(c.content for c in citations)
    evidence_tokens = _sentence_tokens(evidence_text)
    if not evidence_tokens:
        return 1.0

    claims = [s.strip() for s in SENTENCE_SPLIT.split(answer) if s.strip()]
    if not claims:
        return 0.0

    unsupported = 0
    considered = 0
    for sentence in claims:
        if len(sentence) < 6:
            continue
        if any(tok in sentence for tok in GENERIC_SENTENCE_TOKENS):
            continue
        considered += 1
        stoks = _sentence_tokens(sentence)
        if not stoks:
            unsupported += 1
            continue
        overlap = len(stoks & evidence_tokens) / max(1, len(stoks))
        if overlap < 0.20:
            unsupported += 1

    if considered == 0:
        return 0.0
    return unsupported / considered


def _evaluate_grounding_llm(answer: str, citations: list[RetrievalHit]) -> tuple[float, str]:
    citation_text = "\n".join(
        f"- 第{c.chapter_index}章《{c.chapter_title}》: {c.content[:220]}"
        for c in citations
    )
    prompt = (
        "你是grounding评测器。请判断回答里有多少比例的陈述无法被引用证据支持。\n"
        "输出JSON: {\"unsupported_claim_rate\":0.0-1.0,\"reason\":\"\"}\n"
        f"回答: {answer}\n"
        f"引用证据:\n{citation_text}\n"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    data = _post_llm(payload)
    text = _extract_llm_text(data)
    parsed = _parse_json_from_text(text)
    rate = float(parsed.get("unsupported_claim_rate", 1.0))
    rate = min(1.0, max(0.0, rate))
    reason = str(parsed.get("reason", "")).strip()
    return rate, reason


def load_qa_file(path: Path) -> list[QAItem]:
    items: list[QAItem] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            qid = str(row.get("id") or f"q-{line_no:03d}")
            question = str(row.get("question") or "").strip()
            if not question:
                continue
            support = [int(x) for x in (row.get("support_chapters") or []) if int(x) > 0]
            if not support:
                continue
            chapter_index = int(row.get("chapter_index") or max(support))
            items.append(
                QAItem(
                    qid=qid,
                    question=question,
                    chapter_index=chapter_index,
                    support_chapters=sorted(set(support)),
                    reference_answer=str(row.get("reference_answer") or "").strip(),
                    answer_keywords=[str(x).strip() for x in (row.get("answer_keywords") or []) if str(x).strip()],
                    metadata=row.get("metadata") or {},
                )
            )
    return items


def bootstrap_qa_files(book_id: str, eval_dir: Path) -> dict[str, str]:
    db = SessionLocal()
    try:
        chapters = list(
            db.execute(
                select(Chapter.chapter_index, Chapter.title, Chapter.raw_text)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_index.asc())
            ).all()
        )

        source_char = aliased(Character)
        target_char = aliased(Character)
        relation_rows = list(
            db.execute(
                select(
                    RelationshipEdge.relation_type,
                    RelationshipEdge.strength,
                    RelationshipEdge.first_chapter_index,
                    RelationshipEdge.last_chapter_index,
                    source_char.canonical_name,
                    target_char.canonical_name,
                )
                .join(source_char, source_char.id == RelationshipEdge.source_character_id)
                .join(target_char, target_char.id == RelationshipEdge.target_character_id)
                .where(RelationshipEdge.book_id == book_id)
                .order_by(RelationshipEdge.strength.desc(), RelationshipEdge.last_chapter_index.desc())
            ).all()
        )
    finally:
        db.close()
    if not chapters:
        raise RuntimeError("Cannot bootstrap QA because no chapters found.")

    eval_dir.mkdir(parents=True, exist_ok=True)
    demo_path = eval_dir / "demo_qa.jsonl"
    qa50_path = eval_dir / "qa_50.jsonl"
    qa200_path = eval_dir / "qa_200.jsonl"

    def _build_row(ch_idx: int, title: str) -> dict[str, Any]:
        title = (title or "").strip()
        keyword_parts = [p for p in re.split(r"[ 　]", title) if p]
        kws = keyword_parts[:2] if keyword_parts else [f"第{ch_idx}回"]
        return {
            "id": f"qa-{ch_idx:03d}",
            "question": f"第{ch_idx}回的标题是什么？",
            "chapter_index": ch_idx,
            "support_chapters": [ch_idx],
            "reference_answer": title,
            "answer_keywords": kws,
            "metadata": {"type": "title_qa"},
        }

    def _pick_sentence(raw_text: str) -> str:
        cleaned = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not cleaned:
            return ""
        for sentence in SENTENCE_SPLIT.split(cleaned):
            s = sentence.strip()
            if 14 <= len(s) <= 40:
                return s
        return cleaned[:30]

    def _build_row_variant(ch_idx: int, title: str, raw_text: str, variant: int) -> dict[str, Any]:
        title = (title or "").strip()
        keyword_parts = [p for p in re.split(r"[ 　]", title) if p]
        kws = keyword_parts[:3] if keyword_parts else [f"第{ch_idx}回"]
        if variant == 1:
            anchor = kws[1] if len(kws) > 1 else kws[0]
            question = f"包含“{anchor}”这个线索的是哪一回？"
        elif variant == 2:
            snippet = _pick_sentence(raw_text)
            question = f"“{snippet}”这句内容出自哪一回？" if snippet else f"第{ch_idx}回发生了什么？"
        elif variant == 3:
            hint = kws[0] if kws else f"第{ch_idx}回"
            question = f"包含“{hint}”这一关键词的是哪一回？"
        else:
            question = f"第{ch_idx}回的标题是什么？"
        return {
            "id": f"qa{variant}-{ch_idx:03d}",
            "question": question,
            "chapter_index": ch_idx,
            "support_chapters": [ch_idx],
            "reference_answer": title,
            "answer_keywords": kws,
            "metadata": {"type": "title_qa_variant", "variant": variant},
        }

    def _build_relation_row(
        *,
        idx: int,
        source_name: str,
        target_name: str,
        relation_type: str,
        first_ch: int | None,
        last_ch: int | None,
        variant: int,
    ) -> dict[str, Any]:
        rel_cn = RELATION_LABEL_MAP.get((relation_type or "").strip(), "关联")
        source_name = (source_name or "").strip()
        target_name = (target_name or "").strip()
        first_seen = int(first_ch or 1)
        last_seen = int(last_ch or first_seen)
        focus_chapter = max(first_seen, last_seen)
        support = sorted(set([first_seen, last_seen]))

        if variant == 1:
            question = f"在第{focus_chapter}章之前，{source_name}和{target_name}更接近哪种关系？"
        elif variant == 2:
            question = f"{source_name}与{target_name}是否存在“{rel_cn}”关系？请结合情节判断。"
        else:
            question = f"{source_name}和{target_name}在前{focus_chapter}章的互动更像什么关系？"

        return {
            "id": f"rel{variant}-{idx:03d}",
            "question": question,
            "chapter_index": focus_chapter,
            "support_chapters": support,
            "reference_answer": f"{source_name}与{target_name}是{rel_cn}关系",
            "answer_keywords": [source_name, target_name, rel_cn],
            "metadata": {
                "type": "relation_qa",
                "variant": variant,
                "relation_type": relation_type,
                "relation_label": rel_cn,
                "first_chapter_index": first_seen,
                "last_chapter_index": last_seen,
            },
        }

    with demo_path.open("w", encoding="utf-8") as f:
        for ch_idx, title, _raw in chapters[:10]:
            f.write(json.dumps(_build_row(int(ch_idx), str(title)), ensure_ascii=False) + "\n")

    chapter_rows = [(int(ch_idx), str(title), str(raw_text or "")) for ch_idx, title, raw_text in chapters]
    base_title_rows: list[dict[str, Any]] = []
    for ch_idx, title, _raw_text in chapter_rows[:50]:
        base_title_rows.append(_build_row(ch_idx, title))
    title_rows: list[dict[str, Any]] = []
    for variant in (1, 2, 3, 4):
        for ch_idx, title, raw_text in chapter_rows:
            title_rows.append(_build_row_variant(ch_idx, title, raw_text, variant))
            if len(title_rows) >= 140:
                break
        if len(title_rows) >= 140:
            break

    relation_rows_out: list[dict[str, Any]] = []
    relation_cursor = 1
    for variant in (1, 2, 3):
        for rel_type, _strength, first_ch, last_ch, source_name, target_name in relation_rows:
            if not source_name or not target_name:
                continue
            relation_rows_out.append(
                _build_relation_row(
                    idx=relation_cursor,
                    source_name=str(source_name),
                    target_name=str(target_name),
                    relation_type=str(rel_type or "other"),
                    first_ch=int(first_ch or 1) if first_ch is not None else 1,
                    last_ch=int(last_ch or first_ch or 1) if last_ch is not None else int(first_ch or 1),
                    variant=variant,
                )
            )
            relation_cursor += 1
            if len(relation_rows_out) >= 120:
                break
        if len(relation_rows_out) >= 120:
            break

    # Keep qa_50 mixed so small eval runs cover different query types.
    rows_50: list[dict[str, Any]] = []
    rows_50.extend(base_title_rows[:20])
    rows_50.extend(title_rows[:15])
    rows_50.extend(relation_rows_out[:15])
    if len(rows_50) < 50:
        rows_50.extend(base_title_rows[20 : 20 + (50 - len(rows_50))])
    rows_50 = rows_50[:50]

    with qa50_path.open("w", encoding="utf-8") as f:
        for row in rows_50:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    rows_200: list[dict[str, Any]] = []
    rows_200.extend(title_rows[:120])
    rows_200.extend(relation_rows_out[:80])
    if len(rows_200) < 200:
        rows_200.extend(title_rows[120 : 120 + (200 - len(rows_200))])
    rows_200 = rows_200[:200]

    with qa200_path.open("w", encoding="utf-8") as f:
        for row in rows_200:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"demo_qa": str(demo_path), "qa_50": str(qa50_path), "qa_200": str(qa200_path)}


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    eval_dir = Path(args.eval_dir).resolve()
    eval_dir.mkdir(parents=True, exist_ok=True)
    qa_path = Path(args.qa_file).resolve()

    if args.bootstrap_qa:
        created = bootstrap_qa_files(args.book_id, eval_dir)
        print(f"[bootstrap] generated: {created}")
        if not qa_path.exists():
            if qa_path.name == "qa_50.jsonl":
                qa_path = Path(created["qa_50"])
            elif qa_path.name == "demo_qa.jsonl":
                qa_path = Path(created["demo_qa"])
            elif qa_path.name == "qa_200.jsonl":
                qa_path = Path(created["qa_200"])

    if not qa_path.exists():
        raise FileNotFoundError(f"QA file not found: {qa_path}")

    qa_items = load_qa_file(qa_path)
    if args.max_samples > 0:
        qa_items = qa_items[: args.max_samples]
    if not qa_items:
        raise RuntimeError("No valid QA items loaded.")
    total_samples = len(qa_items)
    llm_judge_budget = total_samples if args.llm_judge_max_samples <= 0 else min(total_samples, args.llm_judge_max_samples)
    llm_ground_budget = (
        total_samples if args.llm_grounding_max_samples <= 0 else min(total_samples, args.llm_grounding_max_samples)
    )

    docs, by_chunk_id = _load_chunk_docs(args.book_id)
    if not docs:
        raise RuntimeError("No chunk docs loaded for this book_id.")
    bm25 = BM25Index(docs)

    ks = [int(k.strip()) for k in args.ks.split(",") if k.strip()]
    ks = sorted({k for k in ks if k > 0})
    if not ks:
        ks = [1, 3, 5, 10]
    max_k = max(ks)

    recall_hits = {k: 0 for k in ks}
    mrr_sum = 0.0
    ndcg_sums = {k: 0.0 for k in ks}

    total_retrieval_ms: list[float] = []
    dense_ms_list: list[float] = []
    bm25_ms_list: list[float] = []
    fusion_ms_list: list[float] = []
    rerank_ms_list: list[float] = []

    generation_acc_hits = 0
    generation_llm_hits = 0
    generation_llm_count = 0

    citation_acc_values: list[float] = []
    unsupported_rates: list[float] = []
    grounding_llm_rates: list[float] = []

    per_query: list[dict[str, Any]] = []

    for qa in qa_items:
        t_total_0 = time.perf_counter()

        t0 = time.perf_counter()
        dense_hits = _retrieve_dense(args.book_id, qa.question, qa.chapter_index, args.dense_top_k)
        t1 = time.perf_counter()

        bm25_hits = bm25.search(qa.question, max_chapter_index=qa.chapter_index, top_k=args.bm25_top_k)
        t2 = time.perf_counter()

        fused = _rrf_fuse(dense_hits, bm25_hits, rrf_k=args.rrf_k)
        t3 = time.perf_counter()

        final_hits = _heuristic_rerank(
            fused,
            query=qa.question,
            by_chunk_id=by_chunk_id,
            top_k=max(args.final_top_k, max_k),
        )
        t4 = time.perf_counter()

        dense_ms = (t1 - t0) * 1000.0
        bm25_ms = (t2 - t1) * 1000.0
        fusion_ms = (t3 - t2) * 1000.0
        rerank_ms = (t4 - t3) * 1000.0
        total_ms = (t4 - t_total_0) * 1000.0
        dense_ms_list.append(dense_ms)
        bm25_ms_list.append(bm25_ms)
        fusion_ms_list.append(fusion_ms)
        rerank_ms_list.append(rerank_ms)
        total_retrieval_ms.append(total_ms)

        chapter_hits = _dedupe_hits_by_chapter(final_hits, max(args.final_top_k, max_k))
        rels = [1 if h.chapter_index in qa.support_chapters else 0 for h in chapter_hits[:max_k]]
        first_rel_rank = 0
        for idx, rel in enumerate(rels, start=1):
            if rel == 1:
                first_rel_rank = idx
                break

        for k in ks:
            if any(rel == 1 for rel in rels[:k]):
                recall_hits[k] += 1
            dcg = _dcg(rels, k)
            ideal = _dcg([1] * min(len(qa.support_chapters), k), k)
            ndcg_sums[k] += (dcg / ideal) if ideal > 0 else 0.0

        if first_rel_rank > 0:
            mrr_sum += 1.0 / first_rel_rank

        answer, citations = _generate_answer(qa.question, chapter_hits, citation_k=args.citation_k)
        gen_ok = _evaluate_accuracy_keyword(answer, qa, min_ratio=args.keyword_min_ratio)
        if gen_ok:
            generation_acc_hits += 1

        llm_gen_reason = ""
        if args.use_llm_judge and generation_llm_count < llm_judge_budget:
            try:
                llm_ok, llm_gen_reason = _evaluate_accuracy_llm(qa.question, answer, qa)
                generation_llm_count += 1
                if llm_ok:
                    generation_llm_hits += 1
            except Exception as exc:  # noqa: PERF203
                llm_gen_reason = f"llm_judge_error: {exc}"
        elif args.use_llm_judge:
            llm_gen_reason = "llm_judge_skipped_by_budget"

        if citations:
            citation_acc = sum(1 for c in citations if c.chapter_index in qa.support_chapters) / len(citations)
        else:
            citation_acc = 0.0
        citation_acc_values.append(citation_acc)

        unsupported_rate = _evaluate_grounding_heuristic(answer, citations)
        unsupported_rates.append(unsupported_rate)

        llm_ground_reason = ""
        if args.use_llm_grounding and len(grounding_llm_rates) < llm_ground_budget:
            try:
                llm_rate, llm_ground_reason = _evaluate_grounding_llm(answer, citations)
                grounding_llm_rates.append(llm_rate)
            except Exception as exc:  # noqa: PERF203
                llm_ground_reason = f"llm_ground_error: {exc}"
        elif args.use_llm_grounding:
            llm_ground_reason = "llm_grounding_skipped_by_budget"

        per_query.append(
            {
                "id": qa.qid,
                "question": qa.question,
                "support_chapters": qa.support_chapters,
                "retrieved_chapters": [h.chapter_index for h in chapter_hits[:max_k]],
                "first_rel_rank": first_rel_rank,
                "recall_at": {str(k): int(any(rel == 1 for rel in rels[:k])) for k in ks},
                "answer": answer,
                "citations": [
                    {
                        "chapter_index": c.chapter_index,
                        "chapter_title": c.chapter_title,
                        "chunk_id": c.chunk_id,
                        "score": round(c.rerank_score, 6),
                    }
                    for c in citations
                ],
                "generation_accuracy_keyword": gen_ok,
                "generation_accuracy_llm_reason": llm_gen_reason,
                "citation_accuracy": round(citation_acc, 4),
                "unsupported_claim_rate": round(unsupported_rate, 4),
                "grounding_llm_reason": llm_ground_reason,
                "latency_ms": {
                    "dense": round(dense_ms, 3),
                    "bm25": round(bm25_ms, 3),
                    "fusion": round(fusion_ms, 3),
                    "rerank": round(rerank_ms, 3),
                    "total": round(total_ms, 3),
                },
            }
        )

    qn = len(qa_items)
    retrieval = {
        "sample_count": qn,
        "recall_at_k": {str(k): round(recall_hits[k] / qn, 4) for k in ks},
        "mrr": round(mrr_sum / qn, 4),
        "ndcg_at_k": {str(k): round(ndcg_sums[k] / qn, 4) for k in ks},
        "latency_ms": {
            "total": _format_latency(total_retrieval_ms),
            "dense": _format_latency(dense_ms_list),
            "bm25": _format_latency(bm25_ms_list),
            "fusion": _format_latency(fusion_ms_list),
            "rerank": _format_latency(rerank_ms_list),
        },
    }
    generation = {
        "accuracy_keyword": round(generation_acc_hits / qn, 4),
        "accuracy_llm_judge": (
            round(generation_llm_hits / generation_llm_count, 4) if generation_llm_count else None
        ),
        "llm_judge_count": generation_llm_count,
    }
    grounding = {
        "citation_accuracy": round(statistics.fmean(citation_acc_values), 4) if citation_acc_values else 0.0,
        "unsupported_claim_rate": round(statistics.fmean(unsupported_rates), 4) if unsupported_rates else 1.0,
        "unsupported_claim_rate_llm": (
            round(statistics.fmean(grounding_llm_rates), 4) if grounding_llm_rates else None
        ),
        "llm_grounding_count": len(grounding_llm_rates),
    }

    failed = sorted(
        per_query,
        key=lambda x: (x["generation_accuracy_keyword"], x["first_rel_rank"] if x["first_rel_rank"] > 0 else 9999),
    )[:8]

    report = {
        "generated_at_utc": _now_iso(),
        "book_id": args.book_id,
        "qa_file": str(qa_path),
        "config": {
            "dense_top_k": args.dense_top_k,
            "bm25_top_k": args.bm25_top_k,
            "rrf_k": args.rrf_k,
            "final_top_k": args.final_top_k,
            "citation_k": args.citation_k,
            "ks": ks,
            "keyword_min_ratio": args.keyword_min_ratio,
            "use_llm_judge": args.use_llm_judge,
            "use_llm_grounding": args.use_llm_grounding,
            "llm_judge_max_samples": args.llm_judge_max_samples,
            "llm_grounding_max_samples": args.llm_grounding_max_samples,
        },
        "retrieval": retrieval,
        "generation": generation,
        "grounding": grounding,
        "failure_samples": failed,
        "per_query": per_query,
    }
    return report


def write_outputs(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    retrieval = report["retrieval"]
    generation = report["generation"]
    grounding = report["grounding"]
    ks = report["config"]["ks"]
    recall_cols = " | ".join([f"Recall@{k}" for k in ks])
    recall_vals = " | ".join([str(retrieval["recall_at_k"][str(k)]) for k in ks])
    ndcg_cols = " | ".join([f"nDCG@{k}" for k in ks])
    ndcg_vals = " | ".join([str(retrieval["ndcg_at_k"][str(k)]) for k in ks])

    lines: list[str] = []
    lines.append("# RAG Eval Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- book_id: `{report['book_id']}`")
    lines.append(f"- qa_file: `{report['qa_file']}`")
    lines.append("")
    lines.append("## Retrieval")
    lines.append("")
    lines.append(f"| {recall_cols} | MRR |")
    lines.append(f"| {' | '.join(['---' for _ in ks])} | --- |")
    lines.append(f"| {recall_vals} | {retrieval['mrr']} |")
    lines.append("")
    lines.append(f"| {ndcg_cols} |")
    lines.append(f"| {' | '.join(['---' for _ in ks])} |")
    lines.append(f"| {ndcg_vals} |")
    lines.append("")
    lines.append("Latency(ms):")
    lines.append("")
    lines.append(
        f"- total: avg={retrieval['latency_ms']['total']['avg']} "
        f"p50={retrieval['latency_ms']['total']['p50']} p95={retrieval['latency_ms']['total']['p95']}"
    )
    lines.append(
        f"- dense: avg={retrieval['latency_ms']['dense']['avg']} "
        f"p50={retrieval['latency_ms']['dense']['p50']} p95={retrieval['latency_ms']['dense']['p95']}"
    )
    lines.append(
        f"- bm25: avg={retrieval['latency_ms']['bm25']['avg']} "
        f"p50={retrieval['latency_ms']['bm25']['p50']} p95={retrieval['latency_ms']['bm25']['p95']}"
    )
    lines.append(
        f"- fusion: avg={retrieval['latency_ms']['fusion']['avg']} "
        f"p50={retrieval['latency_ms']['fusion']['p50']} p95={retrieval['latency_ms']['fusion']['p95']}"
    )
    lines.append(
        f"- rerank: avg={retrieval['latency_ms']['rerank']['avg']} "
        f"p50={retrieval['latency_ms']['rerank']['p50']} p95={retrieval['latency_ms']['rerank']['p95']}"
    )
    lines.append("")
    lines.append("## Generation")
    lines.append("")
    lines.append(f"- accuracy(keyword): `{generation['accuracy_keyword']}`")
    lines.append(f"- accuracy(llm_judge): `{generation['accuracy_llm_judge']}`")
    lines.append(f"- llm_judge_count: `{generation['llm_judge_count']}`")
    lines.append("")
    lines.append("## Grounding")
    lines.append("")
    lines.append(f"- citation_accuracy: `{grounding['citation_accuracy']}`")
    lines.append(f"- unsupported_claim_rate(heuristic): `{grounding['unsupported_claim_rate']}`")
    lines.append(f"- unsupported_claim_rate(llm): `{grounding['unsupported_claim_rate_llm']}`")
    lines.append(f"- llm_grounding_count: `{grounding['llm_grounding_count']}`")
    lines.append("")
    lines.append("## Failure Samples")
    lines.append("")
    for row in report.get("failure_samples", []):
        lines.append(f"- `{row['id']}` q={row['question']}")
        lines.append(
            f"  - support={row['support_chapters']} retrieved={row['retrieved_chapters'][:5]} "
            f"first_rel_rank={row['first_rel_rank']} gen_ok={row['generation_accuracy_keyword']}"
        )
        lines.append(f"  - answer={row['answer'][:180]}")
    lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 3-layer RAG eval (retrieval/generation/grounding).")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--qa-file", default="eval/demo_qa.jsonl")
    parser.add_argument("--eval-dir", default="eval")
    parser.add_argument("--out-json", default="eval/eval_report.json")
    parser.add_argument("--out-md", default="eval/eval_report.md")
    parser.add_argument("--dense-top-k", type=int, default=20)
    parser.add_argument("--bm25-top-k", type=int, default=20)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--final-top-k", type=int, default=10)
    parser.add_argument("--citation-k", type=int, default=3)
    parser.add_argument("--ks", default="1,3,5,10")
    parser.add_argument("--keyword-min-ratio", type=float, default=0.6)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--bootstrap-qa", action="store_true")
    parser.add_argument("--use-llm-judge", action="store_true")
    parser.add_argument("--use-llm-grounding", action="store_true")
    parser.add_argument(
        "--llm-judge-max-samples",
        type=int,
        default=40,
        help="Max samples for LLM generation judge (0 means all).",
    )
    parser.add_argument(
        "--llm-grounding-max-samples",
        type=int,
        default=40,
        help="Max samples for LLM grounding judge (0 means all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate(args)
    write_outputs(report, Path(args.out_json), Path(args.out_md))
    print(json.dumps(
        {
            "generated_at_utc": report["generated_at_utc"],
            "qa_file": report["qa_file"],
            "retrieval": report["retrieval"],
            "generation": report["generation"],
            "grounding": report["grounding"],
            "out_json": str(Path(args.out_json).resolve()),
            "out_md": str(Path(args.out_md).resolve()),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
