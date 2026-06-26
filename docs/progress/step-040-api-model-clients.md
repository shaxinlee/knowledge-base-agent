# Step 040：API 化 embedding / reranker / LLM 接入

## 1. 本步骤目标

本步骤目标是在 Step 039 已完成真实 MinerU 产物标准化与 chunking 优化后，按用户确认的 API 化方向接入 embedding、reranker 和 LLM client。

本步骤不做真实端到端验收，不强制要求当前环境提供外部 API key，不移除 fake/demo client。fake/demo client 只用于测试和本地演示，不作为真实验收结果。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：Embedding、向量检索、PostgreSQL 全文检索、Reranker 重排、LLM 生成回答、引用溯源、trace 与反馈保存。
- SDD v0.1 1.4：使用本地 bge-m3 embedding 服务生成向量；使用本地 BGE Reranker 重排；SSE 流式返回回答；回答必须带引用编号；证据不足必须拒答；保存会话、消息、引用、trace；支持 feedback。
- SDD v0.1 2.1.5：`call embedding-service -> write vectors to Qdrant -> build PostgreSQL tsvector -> mark indexed`。
- 用户确认方向：当前硬件按 CPU 环境，不依赖本机 GPU；MinerU、embedding、reranker、LLM 后续均按 API 接入方向规划。该方向偏离 SDD 原文“本地 bge-m3 / 本地 BGE reranker”要求，已在本步骤记录。

## 3. 本步骤完成内容

- 新增/扩展配置项：
  - `EMBEDDING_API_BASE_URL`
  - `EMBEDDING_API_KEY`
  - `EMBEDDING_MODEL`
  - `EMBEDDING_BATCH_SIZE`
  - `RERANKER_API_BASE_URL`
  - `RERANKER_API_KEY`
  - `RERANKER_MODEL`
  - `LLM_API_BASE_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL`
  - `EVIDENCE_MIN_RERANKER_SCORE`
- 保留兼容配置：
  - `EMBEDDING_SERVICE_URL`
  - `RERANKER_SERVICE_URL`
  - `LLM_API_BASE`
- 扩展 embedding client：
  - 配置 `EMBEDDING_API_BASE_URL` 时走 API 模式。
  - API 模式默认请求 OpenAI-compatible `/embeddings`，payload 为 `{"model": ..., "input": [...]}`。
  - 未配置 API base 时继续使用旧 `/embed` local service 契约。
  - 继续兼容 `vectors`、`embeddings`、`data[].embedding` 响应形态。
- 扩展 reranker client：
  - 配置 `RERANKER_API_BASE_URL` 时走 API base。
  - 默认请求 `/rerank`，带 `Authorization: Bearer <key>`。
  - 继续兼容 `scores` 与 `results[].{index, score}` 响应形态。
- 新增 LLM client：
  - `LLMApiClient` 使用 OpenAI-compatible `/chat/completions`。
  - `generate_answer()` 生成完整回答并解析 `choices[].message.content`。
  - `stream_answer()` 支持解析 OpenAI-compatible SSE delta。
  - prompt 强制模型只基于最终 context chunks 回答，要求使用 `[1]`、`[2]` 引用，不允许编造文件名或页码。
  - 未配置 `LLM_API_BASE_URL`/`LLM_MODEL` 时使用 `TemplateDemoLLMClient`，保持本地 Demo 可运行。
- Chat 内部回答来源从固定模板函数切换为 LLM client：
  - 有最终上下文时调用 LLM client。
  - 无上下文时拒答，不调用 LLM。
  - citations 仍来自最终 context chunks，不依赖模型自己生成。
  - trace 记录 `embedding_model`、`reranker_model`、`chat_model`、`prompt_version`、`raw_prompt_snapshot`、`token_usage`。
- 新增配置化 evidence gate：
  - 默认 `EVIDENCE_MIN_RERANKER_SCORE` 为空，不改变当前 Demo 行为。
  - 配置后，最高 reranker score 低于阈值时拒答且不调用 LLM。
- Chat SSE 接口保持事件格式不变：
  - `message_created`
  - `retrieval`
  - `token`
  - `done`

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `.env` | 修改 | 增加 API 化 embedding/reranker/LLM 配置项和 evidence gate 配置 |
| `.env.example` | 修改 | 同步新增配置项，并说明 demo client 边界 |
| `backend/app/core/config.py` | 修改 | 新增 API 模型配置与空字符串可选 float 解析 |
| `backend/app/services/embedding.py` | 修改 | 扩展 API 模式、API key、OpenAI-compatible embeddings payload 和 MockTransport 测试入口 |
| `backend/app/services/reranker.py` | 修改 | 扩展 API key、API base `/rerank` 构造和 MockTransport 测试入口 |
| `backend/app/services/llm.py` | 新增 | 新增 LLM API client、template demo client、prompt 构造、SSE delta 解析和拒答文案 |
| `backend/app/services/conversations.py` | 修改 | Chat 回答改为通过 LLM client 生成，增加 evidence gate 和 trace 模型元数据 |
| `backend/app/api/v1/conversations.py` | 修改 | 注入 `get_llm_client` dependency，SSE 事件格式保持不变 |
| `backend/tests/test_api_model_clients.py` | 新增 | 覆盖 embedding/reranker/LLM API client mock 请求、响应解析和流式 delta |
| `backend/tests/test_conversations_api.py` | 修改 | 新增 fake LLM、LLM trace 断言、evidence gate 测试 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 同步 Chat/Feedback 中 LLM API 与 template demo client 边界说明 |
| `docs/progress/step-040-api-model-clients.md` | 新增 | 记录 Step 040 实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 040 状态和下一步建议 |

## 5. 关键实现说明

- `EmbeddingClient`：
  - 通过 `api_mode=True` 区分 API 模式与旧 local service 模式。
  - API base 如果未包含 `/embeddings`，自动拼接 `/embeddings`。
- `RerankerClient`：
  - API base 如果未包含 `/rerank`，自动拼接 `/rerank`。
  - 请求体仍保持 `{model, query, documents}`，便于后续接常见 rerank API。
- `LLMApiClient`：
  - 使用 OpenAI-compatible chat completions 结构，降低后续接入不同供应商 API 的适配成本。
  - `raw_prompt_snapshot` 保存最终 messages JSON，供 trace 和 feedback bad case 排查。
- `TemplateDemoLLMClient`：
  - 仅用于本地 Demo/测试。
  - 不代表真实 LLM 验收结果。
- `apply_evidence_gate()`：
  - 只在配置阈值时启用。
  - 拒答时 final cited chunks 为空，但 retrieved/reranked chunks 仍保存在 trace，便于排查。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| API client mock 测试 | `backend/.venv/bin/python -m pytest backend/tests/test_api_model_clients.py backend/tests/test_conversations_api.py backend/tests/test_retrieval_api.py -q` | 通过 | 14 passed，覆盖 embedding/reranker/LLM API、Chat LLM、SSE 和 evidence gate |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 86 files unchanged |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 76 source files 无类型错误 |
| 后端完整测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 51 passed，存在既有 Starlette/JWT secret warning |
| 前端类型检查 | `npm run typecheck` | 通过 | 前端类型检查通过 |
| 前端构建测试 | `npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞 |
| OpenAPI YAML 解析 | `backend/.venv/bin/python -c "import pathlib, yaml; yaml.safe_load(...)"` | 通过 | 输出 `openapi-ok` |
| Docker 构建与启动 | `docker compose up -d --build backend-api frontend` | 通过 | 后端镜像使用阿里云 PyPI 镜像构建，服务已重启 |
| Migration | `docker compose exec -T backend-api alembic upgrade head` | 通过 | 无新增 migration，当前 schema 可用 |
| 服务健康检查 | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回 `status=ok` |
| Docker Compose 服务状态 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均 Up |
| 容器内后端完整测试 | `docker compose exec -T backend-api pytest -q` | 通过 | 51 passed，存在既有 Starlette/JWT secret warning |
| 真实 embedding API 在线调用 | 配置 `EMBEDDING_API_BASE_URL`/`EMBEDDING_API_KEY` 后执行 | 未执行 | 当前环境未配置真实 embedding API |
| 真实 reranker API 在线调用 | 配置 `RERANKER_API_BASE_URL`/`RERANKER_API_KEY` 后执行 | 未执行 | 当前环境未配置真实 reranker API |
| 真实 LLM API 在线调用 | 配置 `LLM_API_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` 后执行 | 未执行 | 当前环境未配置真实 LLM API |

## 7. 当前未完成事项

- 当前 `.env` 未配置真实 embedding/reranker/LLM API key，因此未执行真实 API 在线调用。
- 当前 Chat SSE 事件格式保持不变，服务端仍先生成并保存完整 answer，再按文本片段输出 token event；`LLMApiClient.stream_answer()` 已具备流式 delta 解析能力，但尚未将数据库写入改造成真正边生成边落库。
- 当前 retrieval 仍使用已有 vector/full-text 合并逻辑，尚未升级为严格 RRF `k=60`。该项可在 Step 041 前后继续增强，但本步骤重点是 API client 接入。

## 8. 风险与注意事项

- 不同供应商 embedding/reranker/LLM API 的 endpoint 和 payload 可能不同。当前实现采用 OpenAI-compatible embeddings/chat completions 与常见 rerank `/rerank` 契约，真实接入时如供应商不同，需要补适配。
- SDD 原文要求本地 bge-m3 和本地 BGE reranker；本步骤按用户确认改为 API 化方向，需在后续验收中继续明确该偏离。
- 未配置真实 API 时，Demo 仍可使用 template/local clients，但不得把该结果标记为真实 RAG 验收。

## 9. 下一步建议

建议进入 Step 041：真实端到端验收。

原因：Step 038-040 已分别完成 MinerU API 解析入口、真实产物标准化/chunking、API 化 embedding/reranker/LLM client。下一步应检查当前环境是否具备真实外部 API 配置，并尝试从真实文件上传走到 indexed 与带引用回答。如果缺少必要 API key，应将 Step 041 标记为“需要人工确认”并明确列出缺失配置。
