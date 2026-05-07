# StoryVerse RAG 知识文档（实现版）
更新时间：2026-05-07

## 1. 一句话总览
StoryVerse 的 RAG 是“单库承载 + 混合检索 + 章节进度约束”的实现：  
文本按章节切块后写入 PostgreSQL（`chapter_chunks`）并存 pgvector 向量；在线查询走 `Dense + BM25 + RRF + rerank`，再组装四层上下文（Canonical/Persona/State/Session），最后进入角色化生成与 guard。

---

## 2. 数据库存储到底怎么分
### 2.1 在 PostgreSQL 的事实数据
1. 内容与向量
- `books`
- `chapters`
- `chapter_chunks`（含 `embedding vector(1536)`）

2. 人物与关系
- `characters`
- `character_aliases`
- `character_cards`
- `character_states`
- `relationship_edges`
- `relationship_graph_node_metrics`

3. 会话与运行态
- `session_memories`
- `agent_runs`
- `agent_tasks`
- `agent_messages`
- `agent_memories`

4. 视觉任务与资产元数据
- `asset_jobs`（任务状态）
- `media_assets`（资产元数据，如 `storage_url`）

### 2.2 在本地文件系统的内容
1. 上传原始 txt 文件
2. 画像/场景图缓存文件（例如 `/app/data/uploads/portraits`）

结论：  
`session_memories`、消息系统、视觉任务状态都在 PostgreSQL，不在本地文件。

---

## 3. RAG 构建过程（离线）
## 3.1 入库主流程
入口任务：`books.ingest`（Celery queue=`ingest`）  
实现文件：[ingest.py](/d:/Code/26workpre/agent/backend/app/tasks/ingest.py)

流程：
1. 读取 txt（多编码兜底）
2. 章节切分
  - 先按章节标题正则切（如“第X回/章”）
  - 失败则按段落聚合 fallback 切分
3. 持久化 `chapters`
4. 每章调用 chunking 生成 `chapter_chunks`
5. 对每个 chunk 计算 embedding（1536 维）写入 `chapter_chunks.embedding`
6. 触发 skills pipeline（人物/关系/剧情约束等）

## 3.2 chunk 是怎么切的
实现文件：[chunking.py](/d:/Code/26workpre/agent/backend/app/services/chunking.py)

策略：
1. 段落优先（按空行）
2. 默认 `chunk_size=700` 字符
3. 默认 `chunk_overlap=120` 字符
4. 超长段落（>= 2*chunk_size）会直接按窗口切并带 overlap

结论：  
不是“按整章一个向量”，而是“按 chunk 一个向量”。

## 3.3 向量到底是什么
实现文件：[embedding.py](/d:/Code/26workpre/agent/backend/app/services/embedding.py)

当前实现是本地 deterministic embedding（MVP）：
1. 文本 token 化
2. hash 到 1536 维向量空间
3. L2 归一化

这保证了在无外部 embedding 服务时，检索链路仍可跑通。后续可替换为真实 embedding API，接口不变。

---

## 4. 人物提取与别名合并（你最关心）
## 4.1 人物姓名提取：LLM + 规则双轨
实现文件：[character_discovery.py](/d:/Code/26workpre/agent/backend/app/skills/character_discovery.py)

流程：
1. 先尝试 LLM 抽取（`extract_characters_from_text`）
2. 若 LLM 失败，走规则 fallback（基于“某某说道/笑道”等 hint）
3. 过滤噪声（“众人”“大家”等）
4. 统计 mention_count、首章出现、证据句

结论：  
不是纯规则，也不是纯 LLM，而是“LLM 主、规则兜底”。

## 4.2 小名/别名怎么合并
实现文件：
1. [character_normalization.py](/d:/Code/26workpre/agent/backend/app/skills/character_normalization.py)
2. [character_refinement.py](/d:/Code/26workpre/agent/backend/app/skills/character_refinement.py)

合并策略（多阶段）：
1. 规则 canonical 候选（去称谓、去“儿”、去叙事尾缀、三字名取后两字等）
2. mention_count/confidence 约束，防止误并
3. 合并 alias、evidence、state（冲突 state 按 chapter 去重）
4. 可选 LLM 复核 suspicious 候选，剔除伪人物

---

## 5. 增量构建怎么做到
核心字段：`books.skill_checkpoint_chapter`

机制（`books.skills_pipeline`）：
1. `incremental=true` 时：
  - `start_from = checkpoint + 1`
  - `target_max = min(requested, max_available)`
2. skills 只处理 `[start_from, target_max]` 章节区间
3. 全部成功后推进 checkpoint
4. 若失败，不推进 checkpoint，方便重跑

相关代码：[ingest.py](/d:/Code/26workpre/agent/backend/app/tasks/ingest.py)

补充：
1. `incremental=false` 可强制全量重建（1..max）
2. 人物关系图谱也支持按章节上限构建

---

## 6. 在线检索流程（Hybrid Retrieval）
离线评测链路文件：[run_eval.py](/d:/Code/26workpre/agent/backend/eval/run_eval.py)

步骤：
1. Dense（pgvector cosine）
2. BM25（lexical）
3. RRF 融合
4. heuristic rerank（RRF/dense/bm25/overlap/章节提示）
5. Top-K 进入上下文组装

RRF 公式（图中可用）：
`RRF(d) = Σ 1 / (k + rank_i(d))`，当前 `k=60`

rerank 当前权重：
1. 0.50 * rrf_norm
2. 0.20 * dense_norm
3. 0.15 * bm25_norm
4. 0.10 * token_overlap
5. 0.05 * title/chapter bonus

---

## 7. 两个端到端例子（执行路径 + 数据流）
## 7.1 例子A：用户和宝玉对话
请求：
`POST /api/chat`（book_id, role_name=贾宝玉, message, chapter_index）

执行路径：
1. API 校验书与章节上限
2. 生成 plan（偏 narrative）
3. 检索证据：`chapter_chunks`（且 `chapter_index <= user_progress`）
4. 读取角色卡/状态：`character_cards` + `character_states`
5. 读取会话记忆：`session_memories(book_id, session_id, role_name)`
6. 组装 prompt -> LLM 生成
7. guard 校验（防剧透）
8. 更新 `session_memories`
9. 返回 `answer + citations + spoiler_risk + session_id`

关键数据流：
1. 读：`chapter_chunks/characters/character_states/session_memories`
2. 写：`session_memories`

## 7.2 例子B：生成黛玉画像
请求：
`POST /api/books/{book_id}/visual/jobs`（asset_type=portrait, character_id=黛玉）

执行路径：
1. 创建/复用 `asset_jobs`（queued）
2. 投递 Celery `visual.generate_asset`（queue=`visual`）
3. worker 组装风格 prompt，调用图像生成
4. 文件缓存落地（本地目录）
5. 写 `media_assets`（storage_url、version、status）
6. 更新 `asset_jobs`（completed + result_asset_id）
7. 前端轮询 `GET /visual/jobs/{job_id}`

关键数据流：
1. 写：`asset_jobs`
2. 写：本地图片缓存文件
3. 写：`media_assets` + 回写 `asset_jobs.status`

---

## 8. 并行情况是怎么样的
## 8.1 Celery 队列并行
Worker 监听队列：`default, ingest, embed, image, visual`  
意义：
1. ingest/embed 与 visual 任务可并行排队
2. 同类任务在各自队列中按 worker 并发设置执行

## 8.2 Multi-agent 主控循环
当前主控是“任务级串行调度 + DAG 依赖”，并非所有子任务无脑并行：
1. 先执行无依赖任务
2. 依赖任务在 `depends_on_task_id` 完成后才执行

---

## 9. 评测指标是怎么计算的（简版）
评测入口：[run_eval.py](/d:/Code/26workpre/agent/backend/eval/run_eval.py)

Retrieval：
1. Recall@K
2. MRR
3. nDCG@K
4. latency（dense/bm25/fusion/rerank/total 的 avg/p50/p95）

Generation：
1. accuracy(keyword)
2. accuracy(llm_judge，可选)

Grounding：
1. citation_accuracy
2. unsupported_claim_rate（heuristic/llm）

## 9.1 指标计算：调用包还是手写公式？
结论：当前评测核心指标是**脚本内手写计算**，不是直接依赖 sklearn/ir-eval 包一键算。

实现特征：
1. 百分位函数 `_percentile(...)` 手写
2. BM25 索引与打分 `BM25Index` 手写
3. RRF 融合 `_rrf_fuse(...)` 手写
4. rerank 打分 `_heuristic_rerank(...)` 手写
5. Recall/MRR/nDCG 聚合逻辑在 `run_eval.py` 主循环中手写
6. latency 统计（avg/p50/p95）手写

这样做的好处：
1. 指标定义可控，便于和业务约束对齐（章节约束、引用策略）
2. 易于插入自定义字段（如 grounding 原因、每题阶段耗时）
3. 回归对比可复现，不依赖外部库版本差异

## 9.2 Hybrid Retrieval 评测标准流程（可直接复述）
Hybrid Retrieval 的评测是逐题跑一遍完整链路：

`Dense -> BM25 -> RRF -> heuristic rerank`

然后对每题排序结果计算：
1. `Recall@K`
2. `MRR`
3. `nDCG@K`

最后在全 QA 集上：
1. 对上述指标取均值
2. 统计各阶段 latency（`avg/p50/p95`），包括：
  - dense
  - bm25
  - fusion
  - rerank
  - total retrieval path

---

## 10. 常见查询“长什么样”（SQL/检索）
## 10.1 Dense 检索（示意）
```sql
SELECT cc.*, c.chapter_index, c.title,
       cosine_distance(cc.embedding, :query_embedding) AS distance
FROM chapter_chunks cc
JOIN chapters c ON c.id = cc.chapter_id
WHERE c.book_id = :book_id
  AND c.chapter_index <= :progress
  AND cc.embedding IS NOT NULL
ORDER BY distance ASC
LIMIT :top_k;
```

## 10.2 角色状态最新快照（示意）
```sql
SELECT *
FROM character_states
WHERE character_id = :char_id
  AND chapter_index <= :progress
ORDER BY chapter_index DESC
LIMIT 1;
```

## 10.3 会话记忆读取（示意）
```sql
SELECT *
FROM session_memories
WHERE book_id = :book_id
  AND session_id = :session_id
  AND role_name = :role_name
LIMIT 1;
```

---

## 11. 你可以在图里放的“最小关键标签”
1. `Chunking: 700 / overlap 120`
2. `Embedding: per-chunk, 1536-dim`
3. `Hybrid: Dense + BM25 + RRF + rerank`
4. `Guard: chapter_index <= user_progress`
5. `Character IE: LLM-first + rule fallback`
6. `Alias merge: normalization + refinement`
7. `Incremental build: checkpoint chapter`
