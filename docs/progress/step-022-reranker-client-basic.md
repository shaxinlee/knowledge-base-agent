# Step 022：Reranker Client 与检索重排基础

## 1. 本步骤目标

在不引入真实 reranker 容器、不扩大 Demo fixture 范围的前提下，补齐 SDD MVP 中 Reranker 阶段的后端基础能力：新增 reranker HTTP client 抽象，将 reranker 接入 Retrieval API 与 Chat 检索路径，并在 message trace / feedback telemetry 中记录 reranker model，为后续真实 BGE reranker 服务接入留下明确契约和测试保护。

## 2. 对应 SDD 条目

- SDD v0.1 Phase 5 / Phase 6：检索链路应包含向量检索、全文检索、重排、引用上下文选择和 trace 记录。
- SDD v0.1 MVP Demo：Chat 问答需要基于知识库检索结果生成可引用回答，并保留检索/模型相关可追踪信息。
- 本步骤只处理 reranker 基础接入，不处理真实 LLM、不处理真实 embedding-service 容器、不处理真实 MinerU token 验证。

## 3. 本步骤完成内容

- 新增 reranker-service HTTP client 抽象，默认调用 `POST /rerank`。
- 新增后端配置项：`reranker_service_url`、`reranker_model`。
- Retrieval API 在 vector + full-text merge 后调用 reranker，对候选 chunks 进行重排。
- Chat message 创建路径透传 reranker client，并在 `message_traces.reranker_model` 中记录当前 reranker model。
- Feedback telemetry 继续从 trace 读取并返回 `reranker_model`。
- 新增检索测试，验证 fake reranker scores 可以改变返回顺序。
- 补充 Chat/Feedback 测试断言，确认 reranker model 被写入 trace 并进入 feedback response。
- 保留空知识库保护：无 active indexed chunks 时不调用 embedding-service / Qdrant / reranker-service，继续返回拒答。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| backend/app/core/config.py | 修改 | 新增 reranker service URL 与 model 配置项 |
| backend/app/services/reranker.py | 新增 | 新增 Reranker client protocol、HTTP client、response parser 和 dependency factory |
| backend/app/services/retrieval.py | 修改 | 在候选结果合并后接入 reranker，并按 reranker score 重排返回结果 |
| backend/app/api/v1/retrieval.py | 修改 | 为 Retrieval API 注入 reranker client |
| backend/app/api/v1/conversations.py | 修改 | 为 Chat message 创建接口注入 reranker client |
| backend/app/services/conversations.py | 修改 | Chat 检索路径传入 reranker client，并在 trace 记录 reranker model |
| backend/tests/test_retrieval_api.py | 修改 | 新增 fake reranker client、依赖覆盖和 reranker 排序验证用例 |
| backend/tests/test_conversations_api.py | 修改 | 新增 fake reranker client 依赖覆盖，并断言 trace/feedback 包含 reranker model |
| docs/progress/step-022-reranker-client-basic.md | 新增 | 记录本步骤目标、实现、验证结果、风险和下一步 |
| docs/progress/README.md | 修改 | 更新总进度索引和当前总体状态 |

## 5. 关键实现说明

- `RerankerClientProtocol` 定义最小后端契约：
  - `model: str`
  - `rerank(query: str, documents: Sequence[str]) -> list[float]`
- `RerankerClient` 默认请求：
  - URL：`{RERANKER_SERVICE_URL}/rerank`
  - Body：`{"model": model, "query": query, "documents": [...]}`
- `parse_reranker_scores()` 兼容两种响应形态：
  - `{"scores": [0.9, 0.2, ...]}`
  - `{"results": [{"index": 0, "score": 0.9}, ...]}`
- Retrieval 排序流程：
  - 先执行 query embedding + Qdrant vector search。
  - 再执行 PostgreSQL/SQLite full-text search。
  - `merge_candidates()` 按 chunk_id 合并 vector/full_text 候选，并保留 `hybrid` 来源标记。
  - 取 `max(top_k, 12)` 个候选加载 chunk content。
  - 调用 reranker，对候选文档打分并按 reranker score 降序返回。
- Chat trace 当前记录：
  - `retrieved_chunk_ids`
  - `final_context_chunk_ids`
  - `final_cited_chunk_ids`
  - `embedding_model`
  - `reranker_model`
  - `chat_model`
  - `prompt_version`
- 本步骤没有引入新数据库表，没有新增 migration。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 81 个文件保持格式一致 |
| 静态检查 | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | 无 lint 问题 |
| 类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 71 个 source files 无类型错误 |
| 后端单元/接口测试 | `cd backend && .venv/bin/pytest` | 通过 | 37 passed，1 个既有 Starlette TestClient deprecation warning |
| Docker Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| Compose 服务状态 | `docker compose ps` | 通过 | backend-api、frontend、postgres、redis、qdrant、minio 均处于 Up 状态 |
| 后端启动健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端运行检查 | `curl -fsS http://localhost:5173 >/dev/null && printf 'frontend-ok\n'` | 通过 | 前端开发服务可访问 |
| 误用旧健康路径检查 | `curl -fsS http://localhost:8000/health` | 失败 | 返回 404，已确认项目正确路径为 `/api/v1/health`，不影响本步骤结论 |

## 7. 当前未完成事项

- 真实 reranker-service 容器尚未加入 Docker Compose。
- 真实 BGE reranker 在线请求尚未验证。
- `message_traces.reranker_scores` 仍未保存每个 chunk 的具体重排分数；当前仅通过 retrieval response score 体现排序结果。
- Chat 回答仍是模板化 demo answer，不是真实 LLM 生成。
- Step 016 真实端到端仍未解除：缺少 `MINERU_API_TOKEN`、真实 embedding-service、真实 reranker-service。

## 8. 风险与注意事项

- SDD 没有规定 reranker-service 的 HTTP 契约。本步骤采用最小合理假设 `POST /rerank`，真实服务接入时需要再次对齐接口字段和响应格式。
- 当前 reranker 是检索链路的必需依赖；有 active indexed chunks 时，如果真实 reranker-service 不可达，Retrieval/Chat 会返回上游服务错误。空知识库路径已保护，不会触发外部服务。
- `RERANKER_SERVICE_URL` 默认值为 `http://reranker-service:8300`，但当前 Compose 尚未定义该服务。
- 当前 `git` 命令在系统中不可用，无法通过 `git status` 辅助确认工作区状态；本步骤基于文件内容与验证命令确认结果。

## 9. 下一步建议

建议进入 Step 023：第一版 Demo 运行说明与端到端可验收边界整理。

原因：到 Step 022 为止，后端基础检索链路已具备 embedding、Qdrant、full-text、reranker、conversation、SSE、feedback 的接口骨架；前端主要页面也已接真实 API。当前最大的 Demo 风险不是页面交互，而是真实外部服务缺失导致“上传文件 -> MinerU API 解析 -> embedding -> Qdrant -> reranker -> 带引用回答”的完整链路无法在线验证。下一步应把可运行 Demo 边界、必需环境变量、服务启动方式、当前已可操作流程和未满足外部条件写清楚，便于用户决定继续补真实服务还是批准开发 Demo fixture 路线。
