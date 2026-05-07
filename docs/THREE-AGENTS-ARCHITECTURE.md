# Three-Agent 架构说明（Main Controller + Narrative + Visual）
更新时间：2026-05-06

## 1. 目标
将系统拆分为 3 个可独立演进的 Agent：
1. `Main Controller Agent`：规划、分发、编排、收敛结果。
2. `Narrative Agent`：文本/RAG/角色化回复。
3. `Visual Agent`：立绘/角色卡/场景图任务提交与资产管理。

## 2. 职责边界
### Main Controller
1. 入口：`POST /api/agent/execute`
2. 调用 Planning 生成执行计划（intent + steps + merge_policy）
3. 把步骤落为持久化任务，并投递消息到子 Agent inbox
4. 轮询执行可运行任务，收集结果并回写 run 状态

关键代码：
1. [main_controller_agent.py](/d:/Code/26workpre/agent/backend/app/agents/main_controller_agent.py)
2. [planning_agent.py](/d:/Code/26workpre/agent/backend/app/agents/planning_agent.py)

### Narrative Agent
1. 承接文本问答任务
2. 走既有 RAG + 角色约束链路
3. 返回 answer/citations/risk 等结构化结果

关键代码：
1. [narrative_agent.py](/d:/Code/26workpre/agent/backend/app/agents/narrative_agent.py)

### Visual Agent
1. 承接视觉任务：`portrait | character_card | scene`
2. 调用 visual tools/queue 提交作图任务
3. 返回 `job_id/status/asset_type`

关键代码：
1. [visual_agent.py](/d:/Code/26workpre/agent/backend/app/agents/visual_agent.py)

## 3. 任务与消息模型（持久化）
数据表定义：
1. [agent_runtime.py](/d:/Code/26workpre/agent/backend/app/models/agent_runtime.py)

### agent_runs
1. 一次主流程执行（run）实例。

### agent_tasks
1. 每个子任务一行。
2. `depends_on_task_id`：任务依赖（DAG 边）。
3. `status`：`queued/running/completed/failed`

### agent_messages
1. Agent 间消息（inbox/outbox）。
2. `correlation_task_id`：消息与任务关联。
3. `status`：`queued/read/acked`

### agent_memories
1. 按 `agent_name + book_id` 保存长期摘要记忆。

## 4. Agent Loop 语义
Main Controller 每轮执行顺序：
1. 先读取 `to_agent=main_controller` 且 `status=queued` 的结果消息。
2. 标记消息状态（当前实现为 `read -> acked` 同轮完成）。
3. 查询 `queued` 任务，筛选“依赖已完成”的第一个任务执行。
4. 执行后写回 `result message` 给 `main_controller` inbox。
5. 无可执行任务时结束循环并收敛 run 状态（`completed/partial`）。

## 5. API
1. `POST /api/agent/execute`
2. `GET /api/agent/runs/{run_id}`
3. `GET /api/agent/runs/{run_id}/tasks`
4. `GET /api/agent/runs/{run_id}/messages?limit=200`

路由与 schema：
1. [agent.py](/d:/Code/26workpre/agent/backend/app/api/routes/agent.py)
2. [agent.py](/d:/Code/26workpre/agent/backend/app/schemas/agent.py)

## 6. 运行注意事项（本次踩坑）
1. 代码新增列后，`create_all` 不会自动给旧表 `ALTER TABLE`。
2. 本次修复需要手工补列：
`agent_tasks.depends_on_task_id`、`agent_messages.correlation_task_id`。
3. 若缺列会报错：`psycopg.errors.UndefinedColumn`。
