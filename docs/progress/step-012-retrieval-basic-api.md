# Step 012：Phase 5-A 检索基础 API

## 1. 本步骤目标

本步骤目标是在 Step 011 已完成 chunks embedding/indexing 基础后，新增一个可测试、可验收的检索基础 API，让系统具备“固定 knowledge_base_id 内检索 chunks”的能力。

本步骤聚焦：

- query embedding。
- Qdrant vector search。
- PostgreSQL/full-text 基础检索。
- vector/full_text 结果合并。
- 按 chunk_id 去重。
- 强制 knowledge_base_id 与 is_active 过滤。
- 返回可供后续 RAG/引用使用的 chunk 结果。

本步骤不实现 reranker、LLM、SSE、conversation/message/trace/citation 持久化。

## 2. 对应 SDD 条目

- `2.2 检索流`：用户每次提问必须绑定固定 `knowledge_base_id`，不允许跨知识库查询。
- `2.2 检索流程`：query embedding -> Qdrant vector search with payload filter -> PostgreSQL tsvector full-text search -> merge results -> deduplicate by chunk_id。
- `2.2 默认检索参数`：`vector_top_k=30`、`full_text_top_k=30`，后续 reranker/final context 暂不在本步处理。
- `2.2 Qdrant 检索必须携带过滤条件`：`knowledge_base_id` 与 `is_active=true`。
- `13.5 Phase 5：全文检索、混合召回与 Reranker`：本步骤完成 full-text search、Qdrant vector search、merge results、deduplicate by chunk_id 的基础部分。
- `docs/tests/TDD.v0.1.md`：
  - `TDD-INDEX-003`：chunks_metadata 可全文检索。本步骤用 SQLite fallback 覆盖基础全文查询，PostgreSQL tsvector 查询逻辑已实现。
  - `TDD-INDEX-004`：单知识库过滤，结果只来自指定 knowledge_base_id。
  - `TDD-SEC-006`：后端仍强制 knowledge_base_id 过滤。

## 3. 本步骤完成内容

- 新增 Retrieval API：
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval/search`
  - 当前登录用户可调用。
  - 请求字段：`query`、`vector_top_k`、`full_text_top_k`、`top_k`。
  - 返回字段：`chunk_id`、`file_id`、`file_name`、`source_locator`、`excerpt`、`score`、`source`。
- 扩展 Qdrant client：
  - 新增 `search_points()`。
  - 调用 `POST /collections/{collection}/points/search`。
  - 请求中强制带 `knowledge_base_id` 与 `is_active=true` filter。
  - 解析 Qdrant hit 为 `VectorSearchHit`。
- 新增 retrieval service：
  - 校验 knowledge_base active。
  - 调用 embedding client 将 query 转成向量。
  - 调用 Qdrant vector search。
  - 调用 PostgreSQL `websearch_to_tsquery` + `ts_rank` 查询 `chunks_metadata.tsv`。
  - 在 SQLite 测试环境使用 `content ILIKE` fallback。
  - 合并 vector/full_text 候选并按 chunk_id 去重。
  - 加载 chunk 详情时再次强制过滤 `knowledge_base_id`、`is_active`、file 未删除、file indexed。
  - 构造 300 字以内 excerpt。
- 新增 retrieval tests：
  - 构造两个 active knowledge bases。
  - fake Qdrant 故意返回一个其他知识库的 chunk。
  - 验证最终 API 结果不会返回跨知识库 chunk。
  - 验证 vector/full_text 同一 chunk 合并为 `hybrid`。
  - 验证 inactive/deleted knowledge base 返回 `404 RESOURCE_NOT_FOUND`。
- 同步契约：
  - 更新 `docs/api/frontend-backend-api-contract.md`。
  - 更新 `docs/api/openapi.v0.1.yaml`。
  - 更新 `frontend/src/api/types.ts`。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/vector_index.py` | 修改 | 新增 `VectorSearchHit` 和 Qdrant `search_points()` |
| `backend/app/schemas/retrieval.py` | 新增 | 新增检索请求、结果项和响应 schema |
| `backend/app/services/retrieval.py` | 新增 | 新增 query embedding、vector search、full-text search、合并去重和结果构造逻辑 |
| `backend/app/api/v1/retrieval.py` | 新增 | 新增检索 API endpoint |
| `backend/app/api/v1/router.py` | 修改 | 注册 Retrieval router |
| `backend/tests/test_retrieval_api.py` | 新增 | 新增检索 API、知识库过滤和 inactive KB 测试 |
| `backend/tests/test_files_api.py` | 修改 | 为 Step 011 fake Qdrant 补齐 `search_points()` 以满足扩展后的 protocol |
| `frontend/src/api/types.ts` | 修改 | 新增 Retrieval API 前端类型 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 新增 Retrieval API 文字契约 |
| `docs/api/openapi.v0.1.yaml` | 修改 | 新增 Retrieval tag、path 和 schemas |
| `docs/progress/step-012-retrieval-basic-api.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 012 状态和下一步建议 |

## 5. 关键实现说明

- API 路径：
  - SDD 没有规定单独的检索调试/基础 API 路径。
  - 本步骤采用最小合理假设：`POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval/search`。
  - 该接口是 Phase 5-A 的基础检索入口，不替代后续 Chat API。
- 安全过滤：
  - Qdrant search 请求带 `knowledge_base_id` 和 `is_active=true` filter。
  - PostgreSQL/full-text 查询带 `knowledge_base_id`、`is_active=true`、file 未删除、file indexed 过滤。
  - 加载 chunk 详情时再次过滤 `knowledge_base_id`，防止上游异常返回跨知识库 chunk_id。
- 合并策略：
  - vector 候选来源为 `vector`。
  - full-text 候选来源为 `full_text`。
  - 同一 chunk 同时命中时来源为 `hybrid`，score 使用两路 score 相加。
  - 当前不做 reranker，因此排序仅按合并 score 倒序。
- 全文检索：
  - PostgreSQL 使用 `websearch_to_tsquery('simple', query)` 与 `ts_rank`。
  - SQLite 测试环境使用 query words 的 `ILIKE` fallback。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 68 个文件格式检查通过 |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | 无 lint 问题 |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 60 个 source files 无类型错误 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 31 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| OpenAPI YAML 解析 | 使用 PyYAML 读取 `docs/api/openapi.v0.1.yaml` | 通过 | YAML 可解析 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 后端镜像构建成功 |
| 容器内 migration | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 当前无新增 migration，数据库保持 head |
| 容器内后端测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 31 passed，1 个 Starlette/httpx deprecation warning |
| 完整 Compose 启动 | `docker compose up -d` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均启动 |
| PostgreSQL migration 版本检查 | `select version_num from alembic_version;` | 通过 | 当前版本为 `0007_chunks_metadata` |
| 后端健康检查 | `curl http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Qdrant 健康检查 | `curl http://localhost:6333/collections` | 通过 | Qdrant 服务正常 |
| 前端启动检查 | `curl -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 真实 embedding-service + Qdrant 检索 | 启动真实 embedding-service 后执行真实 query | 未执行 | 当前 Compose 尚未定义真实 embedding-service；本步骤使用 fake embedding/Qdrant 覆盖检索业务逻辑，并已在 Step 011 验证真实 Qdrant upsert |

## 7. 当前未完成事项

- 未实现 reranker-service 调用。
- 未实现 retrieval trace 表和 retrieved_chunk_ids 保存。
- 未实现 Chat API、SSE、LLM 调用、引用编号和拒答逻辑。
- 未实现真实 embedding-service 容器。
- 未执行真实 MinerU + 真实 embedding-service + 真实 Qdrant 的端到端业务样本检索。

## 8. 风险与注意事项

- 当前 retrieval API 是 Phase 5-A 基础入口，主要用于验证检索链路；后续 Chat API 应复用 retrieval service，而不是复制逻辑。
- 当前 score 合并策略较简单，没有 reranker，因此不能代表最终 RAG 排序质量。
- 当前 PostgreSQL full-text 使用 `simple` 配置。中文检索质量可能有限，后续可结合分词策略、trigram 或 embedding/reranker 调优。
- Qdrant search endpoint 使用 `/points/search`。若后续 Qdrant 版本升级并推荐新接口，需要在 `QdrantVectorIndexClient` 中集中调整。
- 未保存 retrieval trace，因此还不满足 Phase 5 完整验收的“每次检索保存 retrieved_chunk_ids”。

## 9. 下一步建议

建议进入 Step 013：Phase 6-A conversation/message/trace 基础与非流式 Chat Demo。

原因：

- Step 012 已经能返回带 `file_name`、`source_locator`、`excerpt`、`chunk_id` 的检索结果。
- 第一版 demo 需要从“检索 chunks”推进到“用户提问并得到带引用的回答”。
- 为降低复杂度，下一步可先做非流式 Chat Demo：创建 conversation/message/trace/citation 基础表，调用 retrieval service，证据不足时拒答，有证据时生成一个基于检索内容的模板化回答。

Step 013 建议暂不接真实 LLM/SSE，先形成可演示闭环：

- conversations/messages/message_citations/message_traces 表。
- 创建 conversation。
- 发送 message。
- 调 retrieval service。
- 保存 retrieved chunk ids。
- 返回模板化回答和 citations。
- 证据不足返回拒答模板。
