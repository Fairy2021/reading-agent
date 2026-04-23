# StoryVerse-Agent 技术架构（文本版）

版本：v0.1  
创建日期：2026-04-21  
适用范围：MVP 与后续可扩展版本

## 1. 架构目标

1. 先保证端到端可跑通（上传 -> 解析 -> 阅读 -> 对话 -> 解锁）。
2. 核心能力模块化：LLM/VLM、RAG、Skills、MCP、Tools 可替换。
3. 支持“先单体、后拆分”演进路径，降低初期复杂度。

## 2. 总体分层

```text
[Web Frontend]
  |- Reader UI (章节阅读/视角切换)
  |- Graph UI (人物关系图)
  |- Chat UI (角色对话)
  |- Unlock UI (角色解锁与立绘)
          |
          v
[Backend API Gateway / BFF]
  |- Auth (MVP可简化)
  |- Book APIs
  |- Chat APIs
  |- Rewrite APIs
  |- Graph APIs
          |
          v
[Agent Orchestrator]
  |- Director Agent
  |- Roleplay Agent
  |- Rewrite Agent
  |- Lore Guard Agent
  |- Portrait Agent
          |
          +----------------------------+
          |                            |
          v                            v
[Tools/Skills Runtime]           [RAG + Knowledge Layer]
  |- parse_book_tool              |- Vector DB (chunks/personas/dialogues)
  |- extract_entities_tool        |- Graph DB (entities/relations/timeline)
  |- graph_query_tool             |- Relational DB (books/users/progress)
  |- vector_retrieve_tool
  |- image_generate_tool
          |
          v
[MCP Connectors]
  |- Image Model Provider
  |- Graph Query Provider
  |- External Parsing / Utility Providers
```

## 3. 核心组件职责

### 3.1 Frontend

1. 阅读页渲染：原文/视角重写文本切换。
2. 关系图展示：按当前章节高亮人物关系。
3. 聊天面板：展示角色对话和引用证据。
4. 解锁展示：首次出现角色的卡片与立绘。

### 3.2 Backend API（FastAPI 建议）

1. `POST /books/upload`：上传书籍并触发解析任务。
2. `GET /books/{id}/chapters/{idx}`：获取章节与辅助信息。
3. `POST /chat`：角色对话请求。
4. `POST /rewrite`：角色视角重写请求。
5. `GET /graph`：获取图谱节点与边。
6. `POST /unlock/check`：检查并触发角色解锁。

### 3.3 Agent Orchestrator（LangGraph 建议）

1. 根据请求类型路由到对应 Agent 流程。
2. 控制工具调用顺序（检索 -> 生成 -> 校验 -> 输出）。
3. 记录链路日志与模型消耗，便于评估和调优。

## 4. 四条关键流程（文本时序）

### 4.1 书籍导入流程

```text
User Upload
  -> API /books/upload
  -> parse_book_tool (切章/清洗)
  -> extract_entities_tool (人物地点事件)
  -> 写入 Relational DB (book/chapter/entity)
  -> 写入 Vector DB (paragraph embeddings)
  -> 写入 Graph DB (relations)
  -> 返回 book_id + 处理状态
```

### 4.2 阅读与图谱流程

```text
Reader Open Chapter
  -> API /books/{id}/chapters/{idx}
  -> 查询章节正文 + 当前已解锁角色
  -> 查询 Graph DB 返回章节相关关系
  -> 前端渲染正文 + 关系图
```

### 4.3 角色对话流程

```text
User Ask Role
  -> API /chat
  -> Director Agent
  -> vector_retrieve_tool (剧情证据检索)
  -> graph_query_tool (角色关系补充)
  -> Roleplay Agent 生成候选回复
  -> Lore Guard Agent 做一致性检查/反剧透
  -> 返回回复 + 引用证据
```

### 4.4 角色解锁与立绘流程

```text
User Enter Chapter
  -> unlock/check
  -> 判断新角色是否首次出现
  -> Portrait Agent 组装形象提示词
  -> image_generate_tool (经 MCP 调用图像服务)
  -> 存储图片 URL + 角色卡元数据
  -> 前端展示“新角色解锁”
```

## 5. 数据存储设计（MVP）

1. Relational DB（SQLite/Postgres）：
  - 用户、书籍、章节、进度、角色卡元数据。
2. Vector DB（Chroma/Milvus）：
  - 章节 chunk、角色设定、典型对白。
3. Graph DB（Neo4j）：
  - 实体节点、关系边、关系证据引用。
4. Object Storage（本地目录/云对象存储）：
  - 角色立绘与衍生素材。

## 6. Prompt 与约束策略

1. 系统提示词拆层：
  - 任务层（对话/重写/解锁）；
  - 世界观层（书籍事实）；
  - 角色层（人格、语气、知识边界）。
2. 强约束：
  - 回答必须优先使用检索证据；
  - 未检索到时给出保守表达；
  - 默认禁剧透（限制到当前阅读进度）。
3. 输出结构化：
  - `answer`, `citations`, `confidence`, `spoiler_risk`。

## 7. Skills 与 Tools 的工程组织建议

```text
backend/
  app/
    api/
    agents/
    tools/
    skills/
    services/
    repositories/
  tests/
frontend/
docs/
```

建议职责：
1. `tools/`：纯功能函数（解析、检索、查询、绘图调用）。
2. `skills/`：带业务策略的复用能力（角色对话、重写、解锁）。
3. `agents/`：决策和编排（何时调用哪个 skill/tool）。

## 8. 可观测与评估

1. 每次请求记录：
  - `request_id`, `book_id`, `chapter_idx`, `selected_role`。
  - 模型名、token 消耗、耗时、错误类型。
2. 质量评估日志：
  - 人设稳定性分；
  - 一致性检查结果；
  - 用户反馈（like/dislike）。
3. 监控告警：
  - 高频失败工具调用；
  - 超时与成本异常。

## 9. 安全与合规

1. 上传白名单与大小限制，防止恶意文件。
2. Prompt 注入防护：分离用户输入与系统规则。
3. 版权策略：
  - 公版书优先用于公开演示；
  - 用户上传内容仅用户可见。

## 10. 演进路线（MVP -> v1.0）

1. MVP：单体服务 + 单工作队列。
2. v0.5：抽取任务异步化、缓存增强、可回放评测。
3. v1.0：多 Agent 协作稳定化、A/B Prompt 实验、多人共读能力。

## 11. 最小落地技术选型（建议）

1. Frontend：`Next.js + Tailwind + Cytoscape.js`
2. Backend：`FastAPI + LangGraph`
3. DB：`Postgres + Neo4j + Chroma`
4. 队列：`RQ/Celery`（后续引入）
5. 部署：`Vercel(前端) + Railway/Render(后端)`

## 12. 架构验收清单

1. 上传一本书后，数据可同时进入三层存储（关系型、向量、图）。
2. 角色对话路径可检索证据并返回引用。
3. 角色重写路径带一致性校验环节。
4. 解锁流程可触发图像生成且有缓存。
5. API、Agent、Tools、Skills 在代码结构上清晰分层。
