# DB 与 Agent 技术栈总览（简版）
更新时间：2026-05-06

## 1. 数据组件
1. `PostgreSQL`：主业务库。
2. `pgvector`：PostgreSQL 扩展，存向量字段（非独立向量库）。
3. `Redis`：Celery broker/result backend（非主事实存储）。
4. 本地文件系统：上传文本、生成图片缓存。

## 2. 核心表（RAG + Agent）
### RAG / 人物 / 关系
1. `books`
2. `chapters`
3. `chapter_chunks`（含 `embedding`）
4. `characters`
5. `character_aliases`
6. `character_cards`
7. `character_states`
8. `relationship_edges`
9. `relationship_graph_node_metrics`
10. `session_memories`

### Visual
1. `asset_jobs`
2. `media_assets`
3. `visual_style_profiles`

### Agent Runtime
1. `agent_runs`
2. `agent_tasks`（`depends_on_task_id`）
3. `agent_messages`（`correlation_task_id`）
4. `agent_memories`

## 3. 三 Agent 协同
1. Main Controller：Plan + 分发 + 执行循环 + 汇总。
2. Narrative Agent：文本与关系问答。
3. Visual Agent：立绘/角色卡/场景图任务。

关键实现：
1. [main_controller_agent.py](/d:/Code/26workpre/agent/backend/app/agents/main_controller_agent.py)
2. [planning_agent.py](/d:/Code/26workpre/agent/backend/app/agents/planning_agent.py)
3. [narrative_agent.py](/d:/Code/26workpre/agent/backend/app/agents/narrative_agent.py)
4. [visual_agent.py](/d:/Code/26workpre/agent/backend/app/agents/visual_agent.py)
5. [agent_runtime.py](/d:/Code/26workpre/agent/backend/app/models/agent_runtime.py)

## 4. 图关系评测 SOP（一页版）
目标：快速验证“关系数据库是否可用 + 三代理任务消息链路是否可用”。

### Step 1. 环境健康
```powershell
docker compose ps
docker compose logs api --tail 80
```

### Step 2. 结构检查（关键列）
```powershell
docker compose exec postgres psql -U storyverse -d storyverse -c "\d agent_tasks"
docker compose exec postgres psql -U storyverse -d storyverse -c "\d agent_messages"
```
预期：
1. `agent_tasks` 存在 `depends_on_task_id`
2. `agent_messages` 存在 `correlation_task_id`

### Step 3. 若缺列，执行修复
```powershell
docker compose exec postgres psql -U storyverse -d storyverse -c "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS depends_on_task_id VARCHAR(36); ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS correlation_task_id VARCHAR(36);"
docker compose exec postgres psql -U storyverse -d storyverse -c "CREATE INDEX IF NOT EXISTS idx_agent_tasks_depends_on_task_id ON agent_tasks(depends_on_task_id); CREATE INDEX IF NOT EXISTS idx_agent_messages_correlation_task_id ON agent_messages(correlation_task_id);"
```

### Step 4. 三代理执行烟测
```powershell
$body = @{
  book_id='bf3ede4a-2f74-4248-b853-f83cc2dae339'
  message='请总结宝玉与黛玉在前五回的关系，并生成一张场景图'
  role_name='贾宝玉'
  chapter_index=5
  visual_asset_type='scene'
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri 'http://localhost:8000/api/agent/execute' -Method Post -ContentType 'application/json' -Body $body
```

### Step 5. 任务与消息观测
```powershell
$run='替换成上一步 run_id'
Invoke-RestMethod -Uri ("http://localhost:8000/api/agent/runs/{0}" -f $run)
Invoke-RestMethod -Uri ("http://localhost:8000/api/agent/runs/{0}/tasks" -f $run)
Invoke-RestMethod -Uri ("http://localhost:8000/api/agent/runs/{0}/messages?limit=50" -f $run)
```
检查点：
1. `tasks` 中 visual 任务 `depends_on_task_id` 指向 narrative 任务。
2. `messages` 中含 `correlation_task_id`。
3. message 状态出现 `queued/read/acked` 流转。

## 5. 本次实测结论（2026-05-06）
1. 导入校验通过：`agent_import_ok`。
2. 触发失败根因：数据库旧表缺列（不是代码逻辑问题）。
3. 补列后 `/api/agent/execute` 可返回 `run_id` 并落地任务。
4. DAG 生效：narrative 失败时，依赖它的 visual 任务保持 `queued`（未误执行）。
