# Auto Skill Pipeline（导入即自动构建）

本文件描述当前已实现的自动化 skill 流水线。

## 流程

当你上传一本 `.txt` 后，后台会自动执行：

1. `books.ingest`
2. `character_discovery`
3. `character_card_build`
4. `relationship_state_build`

也可以单独手动重跑：

- `POST /api/books/{book_id}/skills/run`

## 已实现 Skill

### 1) `character_discovery`
- 输入：章节正文
- 输出：`characters`、`character_aliases`、`character_evidences`
- 方式：基于叙事对话模式的启发式抽取 + 提及次数阈值

### 2) `character_card_build`
- 输入：发现的人物 + 证据片段
- 输出：`character_cards`
- 方式：基于证据片段自动生成身份摘要、性格摘要、说话风格、价值观/禁忌

### 3) `relationship_state_build`
- 输入：人物集合 + 全书章节
- 输出：`relationship_edges`
- 方式：按章节共现构建关系边，记录强度与首末出现章节

## 查询接口

- `GET /api/books/{book_id}/characters`
- `GET /api/books/{book_id}/characters/{character_id}`
- `GET /api/books/{book_id}/graph`

## 说明

- 当前是 MVP 启发式实现，目标是先打通“自动发现 -> 自动建卡 -> 自动建关系”主链路。
- 后续可以替换为 LLM 抽取与图谱更新策略，不改 API。
