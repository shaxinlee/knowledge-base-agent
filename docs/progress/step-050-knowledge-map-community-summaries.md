# Step 050：知识地图、跨知识库文件关联与社区摘要

## 目标

在 Step 049 文档摘要之上，使用摘要向量连接相关文件，并为每个知识库维护社区
摘要。该能力面向普通用户和管理员展示，但不改变现有 RAG 召回链路。

## 实现

- 新增 `document_summary_embeddings`，缓存文档摘要向量、模型和摘要 hash。
- 新增 `document_summary_relations`，保存无向文件关系、相似度和跨知识库标记。
- 新增 `knowledge_base_community_summaries`，保存每个 active 知识库的社区摘要、
  文档集合指纹、模型、prompt 版本和错误状态。
- 新增 `knowledge_graph_state`，保存全局构建指纹、文档数、关系数和构建状态。
- 使用现有 Embedding 配置对文档摘要向量化，使用余弦相似度并按阈值和每文档
  Top-K 选择关系；默认阈值 0.45、每文档最多 6 条。
- 全局图谱指纹由当前 active 文件的最新文档摘要 ID 和摘要 hash 组成；新增摘要、
  摘要变化、文件删除或知识库状态变化会触发自动重建。
- 社区摘要仅使用本知识库当前文档摘要，prompt 版本为
  `knowledge-base-community-summary-v1`；文档集合指纹未变化时跳过生成。
- 图谱 worker 与文档摘要 worker 共用全局 LLM 并发信号量，不突破既有模型并发
  上限。
- 新增 API：
  - `GET /api/v1/knowledge-graph`
  - `POST /api/v1/knowledge-graph/refresh`
  - `GET /api/v1/knowledge-bases/{id}/community-summary`
- 新增用户/管理员共用 `/knowledge-map` 页面：
  - 文档节点、相似度边、跨库虚线、知识库颜色图例。
  - 知识库筛选、跨库边开关、相似度阈值。
  - 缩放、节点拖动、节点摘要、相关文件和社区摘要。
  - Admin 可刷新关系或全量重算摘要向量。

## 边界

- 图谱只包含 active 知识库、未删除文件及其最新 completed/partially_completed
  文档摘要。
- 不把关系图用于现有 Retrieval/Chat，不实现实体关系抽取、子图召回或社区问答。
- 图谱、Embedding 或社区摘要失败不改变文件 indexed 状态。

## 验证

- 后端完整测试：`133 passed`。
- 余弦相似度、阈值、Top-K 去重和同库/跨库过滤专项测试通过。
- 普通用户读取知识地图、普通用户禁止刷新、Admin 刷新权限测试通过。
- 前端 ESLint 无新增 warning，Vue/TypeScript 类型检查和生产构建通过。
- Alembic 已升级至 `0014_knowledge_graph (head)`。
- 运行态已使用 `qwen3-vl-embedding` 为 active 文档摘要生成文档级向量。
- 运行态知识图谱状态为 `completed`，当前包含 2 个真实文档节点和 1 条相似度
  `0.6669` 的同知识库关系边。
- 运行态“测试”知识库社区摘要已根据 2 篇真实文档摘要重新生成并保存为
  `completed`。
- 当前运行库只有一个 active 知识库，真实跨库边无数据条件；双知识库自动化测试已
  验证跨知识库过滤和标记逻辑。
