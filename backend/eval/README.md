# RAG Eval (3-Layer)

This folder contains a reproducible 3-layer RAG evaluation pipeline:

1. Retrieval layer
2. Generation layer
3. Grounding layer

## Files

- `run_eval.py`: one-click evaluation entry
- `demo_qa.jsonl`: small QA set for fast sanity check
- `qa_50.jsonl`: 50-sample QA set for regression comparison
- `qa_200.jsonl`: larger mixed QA set for stronger regression comparison

## Metrics

### Retrieval

- `Recall@K`
- `MRR`
- `nDCG@K`
- latency (`avg / p50 / p95`) for:
  - dense retrieval
  - BM25 retrieval
  - RRF fusion
  - heuristic rerank
  - total retrieval path

### Generation

- `accuracy(keyword)` (default)
- `accuracy(llm_judge)` (optional)

### Grounding

- `citation_accuracy`
- `unsupported_claim_rate` (heuristic)
- `unsupported_claim_rate(llm)` (optional)

## Retrieval chain under test

- Dense retrieval (pgvector cosine distance)
- BM25 lexical retrieval
- RRF fusion
- heuristic rerank

## QA schema (`.jsonl`)

Each line:

```json
{
  "id": "qa-001",
  "question": "第1回的标题是什么？",
  "chapter_index": 1,
  "support_chapters": [1],
  "reference_answer": "",
  "answer_keywords": ["第1回"],
  "metadata": {"type": "title_qa_synthetic"}
}
```

## Run

From `/app` in api container:

```bash
PYTHONPATH=/app python eval/run_eval.py \
  --book-id <BOOK_ID> \
  --qa-file eval/qa_50.jsonl \
  --out-json eval/eval_report.json \
  --out-md eval/eval_report.md
```

Optional flags:

- `--bootstrap-qa` to generate `demo_qa.jsonl`, `qa_50.jsonl`, `qa_200.jsonl` from current book chapters
- `--use-llm-judge` to enable LLM generation judge
- `--use-llm-grounding` to enable LLM grounding judge
- `--llm-judge-max-samples N` to cap LLM judge samples (default 40)
- `--llm-grounding-max-samples N` to cap LLM grounding samples (default 40)
- `--max-samples N` for quick dry run

## Outputs

- `eval/eval_report.json`
- `eval/eval_report.md`
