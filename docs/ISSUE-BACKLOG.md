# StoryVerse-Agent 初始 Issue Backlog（可直接用于 GitHub）

创建日期：2026-04-21  
用法：每一条可作为一张 GitHub Issue，标签建议 `mvp`、`backend`、`frontend`、`agent`、`data`、`infra`。

## Epic A: 项目初始化

1. `init: scaffold monorepo structure`
- 目标：建立 `frontend/`、`backend/`、`docs/`、`scripts/` 基础结构。
- 验收：目录创建完毕，README 可启动说明可读。

2. `init: environment configuration and .env.example`
- 目标：定义模型、数据库、存储相关环境变量。
- 验收：`backend` 可读取配置并启动。

## Epic B: 书籍导入与解析

3. `feat: upload txt book api`
- 目标：实现 `POST /books/upload`，支持 txt 文件上传。
- 验收：上传成功返回 `book_id` 与解析状态。

4. `feat: chapter splitter`
- 目标：实现章节切分与段落编号。
- 验收：输出标准化章节 JSON，顺序正确。

5. `feat: ingestion persistence`
- 目标：写入 Book、Chapter 到关系型数据库。
- 验收：可根据 `book_id` 查询章节列表。

## Epic C: 知识抽取与图谱

6. `feat: entity extraction pipeline`
- 目标：抽取人物、地点、事件实体。
- 验收：实体入库并可按类型筛选。

7. `feat: relation extraction pipeline`
- 目标：构建人物关系与证据引用。
- 验收：图数据库存在节点/边并可查询。

8. `feat: graph query api`
- 目标：实现 `GET /graph` 返回关系图数据。
- 验收：前端可渲染基础关系图。

## Epic D: RAG 检索层

9. `feat: paragraph embedding indexer`
- 目标：章节段落向量化并写入向量库。
- 验收：可基于问题召回相关段落。

10. `feat: hybrid retrieval service`
- 目标：组合向量召回与关系约束检索。
- 验收：返回带章节引用的证据集。

## Epic E: Agent 与 Skills

11. `feat: director agent router`
- 目标：按请求类型路由到 chat/rewrite/unlock。
- 验收：路由决策可追踪和记录日志。

12. `feat: skill character_chat`
- 目标：实现角色人设对话能力。
- 验收：10 轮对话语气稳定，带引用信息。

13. `feat: skill chapter_rewrite`
- 目标：实现角色视角章节重写。
- 验收：保留关键事件，不明显偏离剧情。

14. `feat: skill consistency_guard`
- 目标：实现事实一致性与反剧透检查。
- 验收：可阻断明显未来剧情泄露。

## Epic F: 角色解锁与立绘

15. `feat: unlock detection service`
- 目标：基于章节首次出现检测新角色。
- 验收：首次触发成功，重复不重复触发。

16. `feat: portrait prompt builder`
- 目标：根据角色标签生成人设绘图提示词。
- 验收：输出结构化 prompt，可审查。

17. `feat: portrait generation integration`
- 目标：接入图像生成能力并缓存结果。
- 验收：角色卡包含可访问立绘 URL。

## Epic G: 前端体验

18. `feat: reader page with chapter navigation`
- 目标：章节阅读主界面。
- 验收：支持切章、显示正文与基础信息。

19. `feat: graph panel integration`
- 目标：前端关系图组件集成。
- 验收：展示节点与边，支持点击实体详情。

20. `feat: role chat panel integration`
- 目标：侧边聊天面板与后端 API 联通。
- 验收：可发起角色对话并展示引用。

21. `feat: unlock cards and portrait display`
- 目标：展示角色解锁记录与立绘。
- 验收：新角色解锁有明显 UI 提示。

## Epic H: 稳定性与上线

22. `feat: structured logging and request tracing`
- 目标：统一日志格式，关联请求链路。
- 验收：可按 `request_id` 追踪一次完整调用。

23. `feat: basic eval scripts for persona and consistency`
- 目标：添加最小评测脚本。
- 验收：输出人设稳定性与一致性指标。

24. `chore: deployment configuration`
- 目标：前后端部署配置完善。
- 验收：外网可访问 demo。

25. `docs: quickstart + architecture + demo walkthrough`
- 目标：补齐开发、部署、演示文档。
- 验收：新开发者可在 30 分钟内启动项目。
