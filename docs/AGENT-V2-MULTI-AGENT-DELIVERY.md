# StoryVerse Agent V2 交付说明（Multi-Agent）

更新时间：2026-05-06  
版本：V2（在 V1.5 基础上）

## 1. 目标

在既有 `Plan-Execute + ReAct` 主链路上，完成 Visual Agent 的 V2 升级：

1. `scene` 任务注入章节证据（避免空泛场景描述）
2. `character_card` 固定版式参数（便于稳定产出“卡片感”）
3. 引入“风格锁定 profile”（同一本书视觉统一）

---

## 2. Agent Loop（编排循环）

## 2.1 总体循环（Orchestrator）

1. `Plan`：识别请求类型（text / visual / hybrid）
2. `Route`：
   - text -> Narrative Agent
   - visual -> Visual Agent
   - hybrid -> Narrative 先产证据，再交 Visual
3. `Execute`：
   - Narrative：检索 + 生成 + guard
   - Visual：入队 `visual`，异步消费
4. `Observe`：收集 task/job 状态、引用、风险
5. `Respond`：返回文本结果与视觉任务状态

## 2.2 Visual Agent 循环

1. 创建 `asset_job`
2. Celery 消费 `visual.generate_asset`
3. 组装 prompt（基础设定 + 风格 profile + 证据片段）
4. 调用图像模型 -> 缓存图片
5. 写入 `media_assets`（版本化）
6. 回写 `asset_jobs.status`

---

## 3. Tools（V2）

新增工具文件：

- [visual_tools.py](D:\Code\26workpre\agent\backend\app\tools\visual_tools.py)

### 3.1 `ensure_visual_style_profile`

作用：确保指定 `book_id` 一定有风格配置行（不存在则创建默认）。

### 3.2 `build_visual_style_clause`

作用：将 profile 字段拼成可注入 prompt 的风格约束段。

### 3.3 `get_scene_evidence_snippets`

作用：从指定章节抽取可读片段（最多 N 条），注入 scene prompt，减少“空画面”。

---

## 4. Skills（V2 对齐）

V2 没有新增独立 skill 名称，而是在视觉链路中强化了“技能行为”：

1. 视觉风格管理技能：按书锁定风格 profile
2. 场景证据拼装技能：scene 任务时自动注入章节证据
3. 角色卡版式技能：character_card 任务自动附加版式指令

说明：这些行为运行在 Visual Agent 的 task 侧（`visual.generate_asset`）。

---

## 5. 数据库（V2）

## 5.1 新增表

1. `visual_style_profiles`
   - 每本书一个风格 profile（唯一约束：`book_id`）
   - 字段：`style_name / palette / brush / mood / negative_prompt / locked`
2. `asset_jobs`（V1.5 已有）
   - 视觉任务状态流转
3. `media_assets`（V1.5 已有）
   - 最终资产记录，支持版本

模型文件：

- [visual_style.py](D:\Code\26workpre\agent\backend\app\models\visual_style.py)
- [media.py](D:\Code\26workpre\agent\backend\app\models\media.py)

---

## 6. 消息与队列（V2）

## 6.1 队列

- Visual Agent 使用 Celery 队列：`visual`
- Worker 启动队列需包含：`default,ingest,embed,image,visual`

## 6.2 状态机

`asset_jobs.status`：

1. `queued`
2. `running`
3. `completed`
4. `failed`

前端通过 job 状态轮询驱动 UI 更新。

---

## 7. API（V2）

## 7.1 通用视觉任务

`POST /api/books/{book_id}/visual/jobs`

请求体：

```json
{
  "asset_type": "portrait | character_card | scene",
  "character_id": "optional-for-scene",
  "chapter_index": 1,
  "style_prompt": "optional",
  "priority": 5
}
```

## 7.2 任务状态

`GET /api/books/{book_id}/visual/jobs/{job_id}`

## 7.3 资产列表

`GET /api/books/{book_id}/visual/assets?asset_type=&character_id=`

## 7.4 风格配置

1. `GET /api/books/{book_id}/visual/style-profile`
2. `PUT /api/books/{book_id}/visual/style-profile`

---

## 8. 本次代码改动清单

1. 新增模型：
   - [visual_style.py](D:\Code\26workpre\agent\backend\app\models\visual_style.py)
2. 新增工具：
   - [visual_tools.py](D:\Code\26workpre\agent\backend\app\tools\visual_tools.py)
3. 任务增强：
   - [visual.py](D:\Code\26workpre\agent\backend\app\tasks\visual.py)
4. API 扩展：
   - [books.py](D:\Code\26workpre\agent\backend\app\api\routes\books.py)
5. Schema 扩展：
   - [book.py](D:\Code\26workpre\agent\backend\app\schemas\book.py)
6. 前端接入：
   - [api.ts](D:\Code\26workpre\agent\frontend\lib\api.ts)
   - [page.tsx](D:\Code\26workpre\agent\frontend\app\page.tsx)

---

## 9. V2 验收口径

1. `portrait` 任务可成功完成
2. `character_card` 任务可成功完成
3. `scene` 任务可成功完成
4. `scene` 的 `style_prompt` 中包含章节证据片段
5. 同一本书重复出图风格稳定（profile 锁定）

