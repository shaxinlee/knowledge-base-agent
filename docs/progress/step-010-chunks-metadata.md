# Step 010：Phase 3-C chunks_metadata 与基础 chunking

## 1. 本步骤目标

本步骤目标是在 Step 009 已完成 `document_blocks` 标准化产物的基础上，按 SDD Phase 3 要求生成可进入后续 embedding/indexing 阶段的 `chunks_metadata` 数据。

本步骤聚焦：

- 新增 `chunks_metadata` 数据表、SQLAlchemy 模型和 Alembic migration。
- 从 `document_blocks` 生成 active chunks。
- 为每个 chunk 生成 `source_locator`、`content_hash`、`token_count` 和基础溯源字段。
- 将旧 active chunks 标记为 inactive，避免重新解析后旧产物继续作为 active 检索候选。
- 将 parse_job 从 `chunking` 推进到 `embedding`，为 Phase 4 embedding-service 与 Qdrant indexing 留出清晰入口。
- 将 `GET /api/v1/files/{file_id}/chunks` 从 document_blocks 调试视图切换为真实 `chunks_metadata` active chunks 查询。

## 2. 对应 SDD 条目

- `2.1.5 解析链路`：`normalize document blocks -> chunking -> save chunks metadata -> call embedding-service`。
- `2.1.6 source_locator 规则`：每个 chunk 必须生成用于引用溯源的 `source_locator`。
- `4.8 chunks_metadata`：PostgreSQL 保存 chunk 元数据和原文内容，包含 `knowledge_base_id`、`file_id`、`parse_job_id`、`chunk_index`、`content`、`content_hash`、`token_count`、定位字段、`source_locator`、`metadata`、`is_active`、`tsv` 等字段。
- `13.3 Phase 3：文档解析与 Chunking`：完成 `chunks_metadata` 表、chunking、`source_locator` 生成。
- `13.3 验收标准`：成功 chunking 后生成 `chunks_metadata`，每个 chunk 必须有 `source_locator`。
- `docs/tests/TDD.v0.1.md`：
  - `TDD-PARSE-002`：解析状态流转进入 `embedding`。
  - `TDD-PARSE-003`：PDF/source locator 形态要求。本步骤实现通用 locator 规则，真实 PDF 样本验证留待后续集成测试。
  - `TDD-PARSE-004`：生成 document_blocks 和 chunks，内容非空。
  - `TDD-PARSE-010`：检查 `token_count`、`content_hash`、`is_active`。

## 3. 本步骤完成内容

- 新增 `ChunkMetadata` SQLAlchemy 模型，对应 SDD 的 `chunks_metadata` 表。
- 新增 Alembic migration `0007_chunks_metadata`，在 PostgreSQL 中创建：
  - 主键 `id`
  - 关联 `knowledge_bases`、`files`、`parse_jobs` 的外键
  - chunk 内容和 hash/token 字段
  - page/slide/sheet/row/heading 定位字段
  - `source_type`、`source_locator`
  - `metadata`、`is_active`、`tsv`
  - `idx_chunks_kb_active`、`idx_chunks_file`、`idx_chunks_parse_job`、`idx_chunks_tsv`
- 新增 `app.services.chunks`：
  - 从 `document_blocks` 查询当前 parse_job 的 blocks。
  - 采用 MVP 最小合理策略：一个非空 `DocumentBlock` 生成一个 chunk。
  - 生成 SHA-256 `content_hash`。
  - 使用基础空白分词统计 `token_count`。
  - 根据文件类型和 block 定位字段生成 `source_locator`。
  - 重新解析时将同一文件旧 active chunks 更新为 inactive。
  - 成功后将 parse_job 状态推进到 `embedding`，进度推进到 `60`。
  - 无 blocks 或无可切片内容时将 parse_job/file 标记为 failed。
- 更新文件状态轮询流程：
  - MinerU API 解析完成后保存 parsed zip。
  - 标准化写入 `document_blocks`。
  - `chunking` 状态下生成 `chunks_metadata`。
  - 完成后进入 `embedding`。
- 更新 chunks 查询接口：
  - `GET /api/v1/files/{file_id}/chunks` 返回 active `chunks_metadata`，不再返回 block-backed 调试数据。
- 更新后端测试，覆盖 MinerU fake 成功解析后的标准化、chunking、状态推进和 chunks 查询。
- 重新安装后端与前端依赖，确认 Python 3.11 与 Docker daemon 可用。
- 按用户要求继续保持 MinerU 解析为 API 调用方式；本步骤没有引入本地 MinerU 服务。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/chunk.py` | 新增 | 新增 `ChunkMetadata` 模型，对应 `chunks_metadata` 表 |
| `backend/app/models/__init__.py` | 修改 | 导出 `ChunkMetadata`，使迁移、测试和服务可统一引用模型 |
| `backend/migrations/versions/0007_create_chunks_metadata.py` | 新增 | 新增 `chunks_metadata` migration 和必要索引 |
| `backend/app/services/chunks.py` | 新增 | 新增基础 chunking、source locator、hash/token 计算和 chunks 查询逻辑 |
| `backend/app/services/files.py` | 修改 | 在 status polling 流程中接入 chunking，并将 chunks 查询切换为真实 chunks |
| `backend/tests/test_files_api.py` | 修改 | 增加 fake MinerU 成功后生成 chunks、状态进入 `embedding`、chunks API 返回真实 chunks 的断言 |
| `frontend/package-lock.json` | 新增/刷新 | 执行前端依赖重装时生成/刷新 lockfile；未引入新的前端依赖 |
| `docs/progress/step-010-chunks-metadata.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步总进度状态，新增 Step 010 记录和下一步建议 |

## 5. 关键实现说明

- `ChunkMetadata`：
  - 使用 `chunk_metadata` 映射数据库列名 `metadata`，避免与 SQLAlchemy declarative 的保留属性 `metadata` 冲突。
  - `tsv` 在 PostgreSQL 中使用 `TSVECTOR`，在 SQLite 测试中使用 `Text` variant，以便单元测试能在内存 SQLite 中执行。
- `generate_chunks_for_parse_job`：
  - 查询同一 parse_job 的 `DocumentBlock`，按 `block_index` 顺序处理。
  - 先将同一文件旧 active chunks 设置为 inactive，再写入新 active chunks。
  - 当前 MVP 策略为 `one_block_one_chunk`，此策略已写入 `parse_jobs.logs["chunking"]`，便于后续升级到合并/滑窗/按 token 上限切片。
  - 若无 blocks 或全部 blocks 内容为空，当前 parse_job 与 file 标记为 failed，防止空索引进入后续检索。
- `source_locator`：
  - 页码：`{source_type}:p{page_number}`，例如 `txt:p2`、`pdf:p12`。
  - 幻灯片：`{source_type}:slide-{slide_number}`。
  - 表格：`{source_type}:{sheet_name}!row-{row_start}-row-{row_end}`，当前先记录 row 范围；单元格区域如 `A20:F35` 留待后续 MinerU 表格结构更明确后增强。
  - fallback：`{source_type}:block-{block_index + 1}`。
- `token_count`：
  - 当前使用正则按非空白片段统计，作为 Phase 3 基础元数据。
  - 后续接入 embedding-service 或 tokenizer 后可替换为更接近模型的 token 统计。
- MinerU：
  - 本步骤未改变 Step 008 的 MinerU API 调用方式。
  - 当前链路仍是通过 MinerU API v4 batch 上传/轮询结果，并从 `full_zip_url` 获取解析产物。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Python 版本检查 | `python3.11 --version`、`backend/.venv/bin/python --version` | 通过 | 均为 Python 3.11.13，满足项目 `>=3.11` 要求 |
| Docker daemon 检查 | `docker version --format '{{.Server.Version}}'` | 通过 | Docker daemon 返回 `26.1.3` |
| 后端依赖重装 | `backend/.venv/bin/pip install -e 'backend[dev]'` | 通过 | 后端依赖安装成功 |
| 前端依赖重装 | `npm install --prefix frontend` | 通过 | 前端依赖安装成功，未发现漏洞 |
| 后端格式化 | `backend/.venv/bin/black backend/app backend/tests backend/migrations` | 通过 | `backend/app/services/chunks.py` 被格式化，其余文件无需调整 |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | 无 lint 问题 |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 61 个文件格式检查通过 |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 53 个 source files 无类型错误 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 29 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | `knowledge-base-agent-backend-api` 镜像构建成功 |
| 容器内 migration | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 成功从 `0006_document_blocks` 升级到 `0007_chunks_metadata` |
| PostgreSQL migration 版本检查 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "select version_num from alembic_version;"` | 通过 | 当前版本为 `0007_chunks_metadata` |
| PostgreSQL 表结构检查 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "\\d chunks_metadata"` | 通过 | `chunks_metadata` 表、外键和索引均存在 |
| 容器内后端测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 29 passed，1 个 Starlette/httpx deprecation warning |
| 后端启动验证 | `docker compose up -d --no-deps backend-api` + `curl http://localhost:8000/api/v1/health` | 通过 | 后端健康检查返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 完整 Compose 启动 | `docker compose up -d backend-api` | 失败 | Docker Hub 拉取 Redis/Qdrant 超时；本步骤未依赖 Redis/Qdrant，已改用 `--no-deps` 验证后端启动 |
| 真实 MinerU 在线验证 | 配置 `MINERU_API_TOKEN` 后上传真实文件并轮询 | 未执行 | 当前环境未配置 `MINERU_API_TOKEN`；本步骤通过 fake MinerU client 覆盖 API 提交、轮询、结果 zip 保存、标准化和 chunking 链路 |

## 7. 当前未完成事项

- 未实现 embedding-service 调用。
- 未实现 Qdrant collection 初始化与 vector point 写入。
- 未实现 `chunks_metadata.tsv` 的全文索引内容生成。
- 未实现 Vector + Full-text 混合检索。
- 未实现 reranker-service 重排。
- 未实现 chat/SSE/引用/拒答/trace/feedback。
- 未执行真实 MinerU 在线解析验证，因为当前环境没有 `MINERU_API_TOKEN`。
- 当前 `source_locator` 对表格只支持 sheet + row 范围，尚未支持 Excel 单元格区域如 `A20:F35`。

## 8. 风险与注意事项

- 当前 chunking 是 `one_block_one_chunk` MVP 策略，不代表最终最佳切片质量。它满足 Phase 3 的可落库和可验证要求，但后续 RAG 质量可能需要按 token 上限、标题层级、滑窗重叠等策略优化。
- 当前 `token_count` 是基础正则统计，不是 embedding 模型 tokenizer 的真实 token 数。
- `source_locator` 依赖 MinerU 标准化后的 block 定位字段；不同格式的真实 MinerU 产物字段可能需要在后续样本验证中补齐映射。
- 完整 Docker Compose 启动仍可能受 Docker Hub 网络影响，Redis/Qdrant 镜像拉取需要在后续 Phase 4 前解决。
- `GET /api/v1/files/{file_id}/chunks` 当前仍使用 schema 名称 `ChunkDebugResponse` / `ChunkDebugListResponse`，返回内容已是真实 chunks。后续若作为正式前端 API，应同步更新 API contract、OpenAPI 和前端类型命名。

## 9. 下一步建议

建议进入 Step 011：Phase 4-A embedding 与 Qdrant 索引基础。

原因：

- Step 010 已将 parse_job 稳定推进到 `embedding`，后续入口清晰。
- SDD 下一阶段要求 `embedding-service`、Qdrant collection 初始化、Qdrant point 写入和 `chunks_metadata.tsv` 字段。
- 为了第一版 demo 尽快形成“上传 -> 解析 -> 切片 -> 可检索”的闭环，下一步应先实现 embedding/indexing 基础，而不是提前做聊天界面或复杂 reranker。

Step 011 建议最小范围：

- 新增 embedding client 抽象，默认调用独立 embedding-service HTTP API；测试中使用 fake client。
- 新增 Qdrant client 抽象，完成 collection 初始化和 active chunks point 写入；测试中使用 fake client 或可控最小集成。
- 生成 `chunks_metadata.tsv` 或至少在 PostgreSQL 中写入可全文检索内容。
- 将 parse_job 从 `embedding -> indexing -> indexed` 推进，file 状态从 `processing -> indexed`。
- 暂不实现 hybrid retrieval、reranker 和 chat。
