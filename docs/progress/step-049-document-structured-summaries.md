# Step 049：文档结构化摘要、并发 Chunk 抽取与历史回填

## 目标

在不阻断现有解析、embedding、Qdrant、BM25 和 Chat 链路的前提下，为每个文档
增加独立的结构化摘要流程：

```text
active chunks
→ 有界并发结构化抽取
→ 按 chunk_index 汇总 short_summary
→ 超长上下文分层归并
→ 文档摘要
```

本步骤是对 SDD v0.1“暂不做实体抽取”的用户批准范围变更。结构化结果不接入
GraphRAG、关系召回或现有 Chat context。

## 已实现

- 新增 `chunk_knowledge_extractions` 和 `document_summaries`，迁移版本为
  `0013_document_summaries`。
- 复用现有管理端模型设置或 `.env` 中的 OpenAI-compatible LLM/vLLM 配置。
- 完整使用用户指定的 Chunk 抽取 prompt 和 JSON schema，prompt 版本为
  `chunk-knowledge-extraction-v1`。
- 使用 Pydantic 严格校验枚举、importance、chunk_id 和 evidence 原文连续子串；
  首次格式错误后允许一次模型 JSON 修复。
- 网络错误、429 和 5xx 使用有限次数指数退避重试。
- 共享 `httpx.AsyncClient` 连接池；默认单文档 8 路并发、2 篇文档并行、全局
  16 个模型请求。
- 每个 Chunk 独立短事务落库，进程重启后跳过相同模型和 prompt 版本的成功结果。
- 文档摘要始终按 `chunk_index` 读取；超长输入按连续批次并发压缩并逐层归并。
- 部分 Chunk 失败时生成 `partially_completed` 摘要，不改变文件 `indexed` 状态。
- 使用 worker 租约和 `FOR UPDATE SKIP LOCKED` 防止多 worker 重复领取。
- Chunking 成功后自动创建摘要任务；摘要 worker 与索引 worker 独立。
- 新增历史回填命令：

  ```bash
  python -m app.dev.backfill_document_summaries
  ```

  支持 `--file-id`、`--knowledge-base-id` 和 `--force`。
- 新增 Admin API：
  - `GET /api/v1/files/{file_id}/summary`
  - `POST /api/v1/files/{file_id}/summary/retry`
  - Chunk 调试响应增加 `knowledge_extraction`
- 文件管理页增加摘要抽屉、实时进度、部分完成提示、错误展示、失败项重试和全文
  重新生成。
- 更新 SDD、TDD、OpenAPI、前后端契约、README 和 `.env.example`。

## 验证

- 后端完整测试：`130 passed`。
- 新增并发测试验证实际并行且单文档在途请求不超过 8。
- 新增乱序响应与分层归并测试，确认最终顺序稳定且文档尾部不被丢弃。
- 新增 Admin API、普通用户 403、强制重建和 Chunk 结构化调试响应测试。
- Ruff：通过。
- 前端 `vue-tsc --noEmit`：通过。
- 前端生产构建：通过。
- OpenAPI YAML：可解析。
- PostgreSQL Alembic 已升级至 `0013_document_summaries (head)`。

## 历史回填

2026-06-21 已对当前运行数据库执行回填：

- 未删除文件：18。
- 有 active chunks 并已排队：16。
- 无 active chunks、标记 `not_ready`：2。
- 已创建 Chunk 抽取记录：3,408。
- 已完成首篇真实文档闭环验证：`ADM30528.pdf` 的 19 个 Chunk 全部抽取成功，
  文档摘要状态为 `completed`。

回填使用运行中的独立 worker 持续处理，结果逐 Chunk 提交，可在服务重启后恢复。
