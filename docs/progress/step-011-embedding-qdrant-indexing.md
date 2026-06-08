# Step 011：Phase 4-A embedding-service 与 Qdrant 索引基础

## 1. 本步骤目标

本步骤目标是在 Step 010 已生成 active chunks 并将 parse_job 推进到 `embedding` 的基础上，完成 Phase 4 的索引基础闭环：

- 调用独立 embedding-service 的 HTTP client 抽象。
- 初始化 Qdrant collection。
- 将 active chunks 写入 Qdrant points。
- 写入 Qdrant payload，包含 SDD 要求的核心过滤和溯源字段。
- 为 `chunks_metadata.tsv` 写入基础全文检索内容。
- 将 parse_job 从 `embedding -> indexing -> indexed` 推进。
- 将 file 状态从 `processing -> indexed` 推进。

本步骤不实现真实检索 API、混合召回、reranker、chat/SSE、引用生成。

## 2. 对应 SDD 条目

- `3.3 数据库与存储`：PostgreSQL 保存全文索引与 metadata，Qdrant 保存向量索引。
- `3.4 模型服务`：embedding-service 为 bge-m3 本地 embedding 服务。
- `5.1 Qdrant Collection 策略`：MVP 使用全局 collection `chunks`，通过 payload 过滤知识库。
- `5.2 Payload 字段`：payload 包含 `chunk_id`、`knowledge_base_id`、`file_id`、`parse_job_id`、`file_name`、`source_type`、定位字段、`is_active`、`token_count`、`content_hash`。
- `13.4 Phase 4：Embedding 与 Qdrant 索引`：完成 embedding-service、chunk embedding、Qdrant collection 初始化、Qdrant point 写入、payload 写入、knowledge_base_id/is_active filter。
- `13.5 Phase 5：全文检索、混合召回与 Reranker`：本步骤仅提前落地 `chunks_metadata.tsv` 字段写入基础，不实现检索和 reranker。
- `docs/tests/TDD.v0.1.md`：
  - `TDD-INDEX-001`：chunking 后进入 embedding，每个 active chunk 调用 embedding-service。
  - `TDD-INDEX-002`：Qdrant points 存在，payload 包含 `knowledge_base_id`、`file_id`、`chunk_id`、`is_active`。
  - `TDD-INDEX-003`：indexed 后查询 tsvector。当前完成 `tsv` 写入基础，正式全文检索查询留待 Step 012/Phase 5。

## 3. 本步骤完成内容

- 新增 `EmbeddingClient`：
  - 使用项目已有 `httpx` 调用独立 embedding-service。
  - 默认请求 `POST {EMBEDDING_SERVICE_URL}/embed`。
  - 请求体为 `{"model": EMBEDDING_MODEL, "texts": [...]}`。
  - 兼容 `vectors`、`embeddings` 和 OpenAI-style `data[].embedding` 三种响应形态。
  - 校验向量数量、向量非空和数值类型。
- 新增 `QdrantVectorIndexClient`：
  - 使用 Qdrant HTTP API 初始化 collection。
  - 默认 collection 为 `.env.example` 中已有的 `QDRANT_COLLECTION=chunks`。
  - 通过 `PUT /collections/{collection}/points?wait=true` 写入 points。
- 新增 `index_parse_job` 编排逻辑：
  - 读取当前 parse_job 的 active chunks。
  - 将 parse_job 从 `embedding` 推进到 `indexing`，progress 设置为 `75`。
  - 调用 embedding client 获取每个 chunk 的向量。
  - 初始化 Qdrant collection。
  - 写入 `chunks_metadata.tsv`。
  - 构造 Qdrant points 和 payload。
  - 写入 Qdrant。
  - 成功后将 parse_job 标记为 `indexed`、progress `100`、写入 `finished_at`。
  - 成功后将 file 状态标记为 `indexed`。
  - 失败时将 parse_job/file 标记为 failed，并记录错误日志。
- 更新 `GET /api/v1/files/{file_id}/status`：
  - 在 `embedding` 状态下自动执行 indexing 编排。
  - 依赖注入 embedding client 和 vector index client，测试中可替换 fake client。
- 更新测试：
  - fake MinerU 成功解析后，状态从 `parsing` 一路推进到 `indexed`。
  - 验证 fake embedding 被传入 4 个 active chunks。
  - 验证 fake Qdrant collection 初始化和 4 个 points 写入。
  - 验证 payload 中包含 `chunk_id`、`knowledge_base_id`、`file_id`、`parse_job_id`、`file_name`、`source_type`、`source_locator`、`is_active`、`content_hash`。
  - 验证 SQLite 测试环境中 `chunk.tsv` 写入 chunk 内容。
- 解决运行环境镜像缺口：
  - 通过可用镜像源拉取并 tag `qdrant/qdrant:v1.12.4`。
  - 通过可用镜像源拉取并 tag `redis:7-alpine`。
  - 通过可用镜像源拉取并 tag `node:20-alpine`。
  - 完成完整 `docker compose up -d` 启动验证。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/core/config.py` | 修改 | 新增 `embedding_service_url`、`embedding_model`、`qdrant_url`、`qdrant_collection` 配置读取 |
| `backend/app/services/embedding.py` | 新增 | 新增 embedding-service HTTP client、协议接口和响应向量解析 |
| `backend/app/services/vector_index.py` | 新增 | 新增 Qdrant HTTP client、collection 初始化和 point upsert |
| `backend/app/services/indexing.py` | 新增 | 新增 indexing 编排逻辑、Qdrant payload 构造、tsv 写入和状态推进 |
| `backend/app/services/files.py` | 修改 | 在 status polling 中接入 `embedding -> indexing -> indexed` 流程 |
| `backend/app/api/v1/files.py` | 修改 | 为文件状态接口增加 embedding client 和 vector index client 依赖注入 |
| `backend/tests/test_files_api.py` | 修改 | 增加 fake embedding/Qdrant，验证索引状态推进、payload、tsv 和 points 写入 |
| `docs/progress/step-011-embedding-qdrant-indexing.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 011 状态和下一步建议 |

## 5. 关键实现说明

- `EmbeddingClientProtocol`：
  - 抽象出 `model` 与 `embed_texts()`，避免业务编排直接依赖具体 HTTP 实现。
  - 由于 SDD 未规定 embedding-service 的精确 HTTP 契约，本步骤采用最小合理假设：`POST /embed`，请求包含模型名和 texts。
  - 为降低后续真实服务适配成本，响应解析兼容 `vectors`、`embeddings` 和 `data[].embedding`。
- `QdrantVectorIndexClient`：
  - 不引入 `qdrant-client` 新依赖，直接使用项目已有 `httpx` 调 Qdrant HTTP API。
  - `ensure_collection()` 先查询 collection，若不存在则创建，距离度量为 `Cosine`。
  - `upsert_points()` 使用 wait=true，便于开发和测试时确认写入完成。
- `index_parse_job()`：
  - 先将 parse_job 状态写为 `indexing` 并提交，后续失败时可清晰看到已经进入索引阶段。
  - 向量数量必须与 chunks 数量一致，向量维度必须一致。
  - Qdrant point id 使用 `chunk.id`，便于后续更新、失效或删除。
  - payload 保留 SDD 要求的知识库过滤字段和引用溯源字段。
- `chunks_metadata.tsv`：
  - PostgreSQL 环境使用 `to_tsvector('simple', chunk.content)` 写入。
  - SQLite 测试环境使用 chunk content 文本写入，避免内存 SQLite 缺少 PostgreSQL 函数导致测试不可运行。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式化 | `backend/.venv/bin/black backend/app backend/tests backend/migrations` | 通过 | `indexing.py`、`vector_index.py` 被格式化 |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | 无 lint 问题 |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 56 个 source files 无类型错误 |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 64 个文件格式检查通过 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 29 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 后端镜像构建成功 |
| 容器内 migration | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 当前无新增 migration，数据库保持 head |
| 容器内后端测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 29 passed，1 个 Starlette/httpx deprecation warning |
| Qdrant 镜像拉取 | `docker pull m.daocloud.io/docker.io/qdrant/qdrant:v1.12.4` + tag | 通过 | 已 tag 为 Compose 需要的 `qdrant/qdrant:v1.12.4` |
| Redis 镜像拉取 | `docker pull m.daocloud.io/docker.io/library/redis:7-alpine` + tag | 通过 | 已 tag 为 Compose 需要的 `redis:7-alpine` |
| Node 镜像拉取 | `docker pull m.daocloud.io/docker.io/library/node:20-alpine` + tag | 通过 | 已 tag 为 Compose 需要的 `node:20-alpine` |
| 真实 Qdrant smoke | 使用 `QdrantVectorIndexClient` 创建临时 `step011_smoke` collection 并写入 1 个 point | 通过 | Qdrant 返回 collection green、points_count=1；验证后已删除临时 collection |
| 完整 Compose 启动 | `docker compose up -d` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均启动 |
| 后端健康检查 | `curl http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Qdrant 健康检查 | `curl http://localhost:6333/collections` | 通过 | 返回空 collection 列表，服务正常 |
| 前端启动检查 | `curl -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 真实 embedding-service 在线验证 | 配置并启动真实 bge-m3 embedding-service 后上传文件索引 | 未执行 | 当前 Compose 还没有 embedding-service 服务定义；本步骤通过 fake embedding client 覆盖业务链路 |

## 7. 当前未完成事项

- 未定义或启动真实 bge-m3 embedding-service 容器。
- 未执行真实 embedding-service 在线索引验证。
- 未实现检索 API。
- 未实现 PostgreSQL full-text 查询。
- 未实现 Qdrant vector search。
- 未实现 hybrid merge、deduplicate、reranker。
- 未实现删除文件时 Qdrant points 失效或异步清理。
- 未实现 chat/SSE/引用/拒答/trace/feedback。

## 8. 风险与注意事项

- SDD 规定 embedding-service 是独立服务，但未规定 HTTP API 契约。本步骤采用 `POST /embed` 的最小合理假设，并记录为后续需要和真实 embedding-service 对齐的不明确项。
- 当前 Qdrant 写入逻辑已通过真实 Qdrant smoke，但完整“真实 embedding -> 真实 Qdrant”链路还未验证。
- 当前 collection 初始化使用首次 embedding 返回的向量维度。如果后续真实模型维度与已有 collection 不一致，需要重建 collection 或迁移策略。
- 当前文件删除只软删除 file，尚未将 chunks inactive 和 Qdrant points inactive 串起来；这属于 Phase 4 删除策略后续项。
- 当前 indexing 是在 `GET /files/{file_id}/status` 中同步触发，符合当前无 Celery worker 的阶段性实现；后续接入 worker 后应迁移为异步任务。

## 9. 下一步建议

建议进入 Step 012：Phase 5-A 检索基础 API。

原因：

- Step 011 已完成 active chunks 到 Qdrant point 的基础写入能力。
- 第一版 demo 需要尽快从“可索引”推进到“可查询 chunks”。
- 在 chat/SSE 之前，应先完成一个可测试的检索服务：按 `knowledge_base_id` 做 Qdrant vector search、PostgreSQL full-text search、结果合并和去重。

Step 012 建议最小范围：

- 新增 retrieval service 和只读检索 API。
- 使用 embedding client 将 query 转为向量。
- 调 Qdrant vector search，必须带 `knowledge_base_id` 和 `is_active` filter。
- 调 PostgreSQL full-text search。
- 合并结果并按 chunk_id 去重。
- 返回 chunk_id、file_name、source_locator、content excerpt、score/source。
- 暂不接 reranker、LLM、SSE。
