# Step 052：Chunk 级语义图与检索邻居扩展

## 目标

在 Step 049 Chunk 结构化摘要和 Step 050 文档级图谱基础上，为每个 Chunk 的
`short_summary` 建立语义向量图。检索命中某个 Chunk 时，除现有的同 heading 段落
扩展外，额外召回该 Chunk 在语义图中的邻居节点，提升跨文档、跨段落的主题关联性。

## 实现

- 新增 `chunk_summary_embeddings`，缓存 Chunk short_summary 的向量化结果、
  embedding 模型和摘要 hash。
- 新增 `chunk_relations`，保存同知识库内 Chunk 间的无向语义边和相似度分数。
- 使用现有 Embedding 配置对 short_summary 向量化，使用余弦相似度并按阈值和
  每 Chunk Top-K 选择关系；默认阈值 0.50、每 Chunk 最多 4 条边。
- 图谱构建集成到知识图谱 worker：在文档级图谱构建完成后，为每个有文档的知识库
  增量构建 Chunk 级图谱。Embedding 缓存机制避免重复计算。
- 新增 `expand_context_to_graph_neighbors()`，在现有 `expand_context_to_section_chunks()`
  之后执行。邻居分数 = 命中分数 × 相似度 × score_decay（默认 0.8）。
- 邻居扩展在 streaming 和 non-streaming 两条路径中均已接入。
- 新增回填命令：`python -m app.dev.backfill_chunk_graph`，支持 `--knowledge-base-id`。
- 新增配置项：
  - `CHUNK_GRAPH_SIMILARITY_THRESHOLD=0.50`
  - `CHUNK_GRAPH_MAX_RELATIONS_PER_CHUNK=4`
  - `CHUNK_GRAPH_EMBEDDING_BATCH_SIZE=32`
  - `CHUNK_GRAPH_MAX_NEIGHBORS_AT_RETRIEVAL=3`
  - `CHUNK_GRAPH_SCORE_DECAY=0.8`

## 边界

- 图谱仅限同知识库内 Chunk；不建跨库边。
- 图谱邻居不参与 Reranker 打分，仅在 section 扩展之后追加。
- 图谱构建失败不影响文件 indexed 状态和现有检索。
- 不改变现有 `document_summary` 检索路径。

## 验证

- 后端完整测试：`125 passed`（新增 12 个 chunk_graph 专项测试）。
- 余弦相似度、阈值、Top-K、同库/跨库过滤和完整构建流水线测试通过。
- Embedding 缓存机制验证通过（相同 hash 和 model 不重复调用）。
- Ruff：通过。
- Alembic 已升级至 `0017_chunk_knowledge_graph (head)`。
