# StoryVerse Bad Case 示例集

> 说明：以下 bad case 来自本项目的 RAG 评测报告、角色抽取噪声、以及在线交互中暴露的问题。  
> 目标不是“挑错”，而是把问题按模块归因，便于后续迭代。

## 1. RAG 检索类 Bad Case

### 1.1 关系问答漏召回
- 问题：`在第28章之前，宝玉和黛玉更接近哪种关系？`
- 现象：支持章节是 `[22, 28]`，但检索结果中首个相关章节排到第 8 位。
- 结果：`first_rel_rank=8`，`generation_accuracy_keyword=False`
- 归因：
  - 关系证据分散在多章
  - 单个 chunk 无法完整覆盖关系链路
  - Hybrid 检索仍然更偏向表层词匹配
- 迭代方向：
  - 增强关系证据召回
  - 引入 relation-aware rerank
  - 把关系边和角色状态纳入检索特征

### 1.2 人物关系误判
- 问题：`在第22章之前，贾琏和凤姐更接近哪种关系？`
- 现象：检索虽命中相关章节，但生成阶段把夫妻关系答成了`主仆`
- 结果：`first_rel_rank=2`，但 `gen_ok=False`
- 归因：
  - 生成阶段没有严格绑定证据
  - 关系类型表达不稳定
- 迭代方向：
  - 生成时强制引用 relation evidence
  - 关系类型做结构化约束输出

### 1.3 章节标题问答错章
- 问题：`第15回的标题是什么？`
- 现象：检索首个相关章节不是第15回，而是第13回。
- 结果：`first_rel_rank=3`，`generation_accuracy_keyword=False`
- 归因：
  - 标题类问答对章节定位要求更强
  - chunk 语义与章节标题不完全对齐
- 迭代方向：
  - 对标题类 query 做章节标题优先路由
  - 加入 chapter-title special rerank

### 1.4 章节标题问答错召回
- 问题：`第19回的标题是什么？`
- 现象：检索命中了第7回等早期章节，未能优先召回目标章节。
- 结果：`first_rel_rank=3`，`generation_accuracy_keyword=False`
- 归因：
  - 标题问答更依赖精确章节 ID
  - 纯文本相似度容易偏移
- 迭代方向：
  - 增加 chapter index 解析
  - 对明确章节号问题走规则检索

## 2. Grounding / 幻觉类 Bad Case

### 2.1 回答有证据但支撑不够
- 现象：回答里出现大量推断性表述，引用却无法完全支撑。
- 例子：`unsupported_claim_rate_llm=0.722`（50题 LLM grounding）
- 典型表现：
  - 回答写得像“总结”
  - 但证据只覆盖其中一小段
  - 其余部分属于扩展推测
- 迭代方向：
  - 生成前先做 claim 拆解
  - 引用粒度从“段落级”走向“句子级”
  - 对 unsupported claims 做重写

### 2.2 低质量引用堆叠
- 现象：回答虽然有 citations，但 citations 并没有真正支撑结论。
- 典型问题：
  - 引了相关章节，但没有引用到关键句
  - citations 数量足够，但证据密度不足
- 迭代方向：
  - 从“有引用”升级到“引用可证明结论”
  - 用 citation_accuracy 作为硬门禁

## 3. 角色抽取 / 知识构建类 Bad Case

### 3.1 噪声角色混入
- 问题：人物列表里出现了非人物项，例如：
  - `宝玉忙`
  - `笑说`
  - `忙说`
  - `我知`
  - `哪里知`
- 现象：这些其实是“人物名 + 动作词”或叙事碎片，却被当成角色。
- 归因：
  - 仅靠词频/局部正则不够
  - 别名归并和噪声判定不足
- 迭代方向：
  - 加入 `character_name_filter`
  - discovery 阶段先 sanitize，再入库
  - refinement 阶段再用 LLM 验证

### 3.2 角色别名归并不完整
- 现象：同一人物可能以多个称呼出现，但没有完全合并。
- 典型后果：
  - 角色数量虚高
  - mention_count 被拆散
  - 关系图边被分裂
- 迭代方向：
  - LLM 抽取别名
  - normalization + refinement 双阶段合并

## 4. 对话/状态类 Bad Case

### 4.1 角色上下文串话
- 现象：不同角色共用同一段对话缓存，切换后历史不一致。
- 归因：
  - session 还是全局态
  - 没有按 `book_id + role` 做隔离
- 迭代方向：
  - 会话记忆按角色分桶
  - 切换角色时恢复对应历史

### 4.2 好感度与立绘解锁条件不明确
- 现象：用户不知道为什么不能生成画像。
- 归因：
  - 规则存在，但 UI 没有把状态显示出来
- 迭代方向：
  - 显示 `排队中 / 生成中 / 已完成 / 失败`
  - 显示未解锁原因和好感度门槛

## 5. 评测层面的 Bad Case 信号

当前 `qa_50` + LLM judge 的典型坏信号：

| 指标 | 当前值 | 说明 |
| --- | --- | --- |
| `Recall@10` | `0.58` | 关系类 multi-hop 仍有召回瓶颈 |
| `accuracy(keyword)` | `0.40` | 仅靠关键词规则，覆盖不足 |
| `accuracy(llm_judge)` | `0.30` | 生成质量仍不稳定 |
| `citation_accuracy` | `0.1967` | 引用与结论一致性偏低 |
| `unsupported_claim_rate(heuristic)` | `0.1354` | 仍有部分无依据陈述 |
| `unsupported_claim_rate_llm` | `0.722` | LLM grounding 判定下问题更明显 |

## 6. 这类 Bad Case 怎么用

建议按下面方式打标签：

- `retrieval_miss`
- `relation_reasoning_failure`
- `chapter_title_mismatch`
- `grounding_weak`
- `character_noise`
- `persona_drift`
- `session_leak`
- `ui_state_invisible`

然后每次迭代只看三件事：

1. 哪类 bad case 数量下降了
2. 哪类 bad case 的严重度下降了
3. 哪类 bad case 新增了

