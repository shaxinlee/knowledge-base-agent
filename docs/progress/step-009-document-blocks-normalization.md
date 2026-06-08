# Step 009：document_blocks 与 MinerU 解析产物标准化

## 1. 本步骤目标

完成 Phase 3-B 的 MinerU 解析产物标准化基础：新增 `document_blocks` 表，从 MinIO `parsed-results` 读取 MinerU zip，提取 Markdown/JSON 内容并写入标准化 document_blocks，将 parse_job 从 `normalizing` 推进到 `chunking`，并通过调试接口查看标准化结果。

本步骤不实现 chunks_metadata、chunking、embedding、Qdrant indexing 或 RAG 问答。

## 2. 对应 SDD 条目

- `4.7 document_blocks`：字段、用途、保存 MinerU / 原生 parser 标准化后的 block。
- `Phase 3：文档解析与 Chunking`：覆盖 `document_blocks 表`、`解析结果写入 MinIO parsed-results` 后的标准化 document_blocks、parse_job 状态推进。
- `6.7 Files API`：`GET /api/v1/files/{file_id}/status` 状态轮询、`GET /api/v1/files/{file_id}/chunks` MVP 调试接口。
- TDD：`TDD-PARSE-002` 状态流转、`TDD-PARSE-004` 生成 document_blocks 且内容非空的本阶段可执行部分。

## 3. 本步骤完成内容

- 新增 `DocumentBlock` SQLAlchemy 模型。
- 新增 `0006_document_blocks` migration，创建 `document_blocks` 表和索引。
- 新增 MinerU zip 标准化服务：
  - 从 `parse_jobs.logs.parsed_result.bucket/key` 定位 MinIO 解析产物。
  - 读取 zip。
  - 支持 `.md` / `.markdown` 文件按段落拆分为 block。
  - 支持 `.json` 文件中常见字段 `blocks`、`document_blocks`、`pages`、`content` 的递归提取。
  - 支持从 JSON block 提取 `content/text/md/markdown`、`page_number/page`、`slide_number/slide`、`sheet_name/sheet`、`row_start/row_end`、`bbox`。
- 增强 `GET /api/v1/files/{file_id}/status`：
  - 当 latest parse_job 为 `normalizing` 且有 parsed_result 时，执行一次标准化。
  - 标准化成功后写入 document_blocks。
  - parse_job 推进到 `chunking`，progress 置为 50。
  - file 保持 `processing`。
  - 标准化结果数量写入 `parse_jobs.logs.normalization.document_block_count`。
  - zip 无有效 Markdown/JSON block 时 parse_job 和 file 置为 `failed`。
- 新增 `GET /api/v1/files/{file_id}/chunks` 调试视图：
  - 由于 chunks_metadata 尚未实现，本步骤返回 document_blocks 的 block-backed debug 视图。
  - 返回字段对齐 API 契约中的 Chunk 调试响应：`id`、`file_id`、`knowledge_base_id`、`content`、`source_locator`、`token_count`、`is_active`、`created_at`。
- 新增测试覆盖：
  - MinerU fake result zip 包含 Markdown 与 JSON。
  - status 轮询后 parse_job 从 `parsing` 经 `normalizing` 推进到 `chunking`。
  - `parsed-results` 保存 zip。
  - `GET /files/{file_id}/chunks` 返回 4 个标准化 block。
  - JSON page_number 可生成 `pdf:p2` / `pdf:p3` 类 locator。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/document_block.py` | 新增 | 新增 DocumentBlock 模型，Python 属性 `block_metadata` 对应数据库列 `metadata` |
| `backend/app/models/__init__.py` | 修改 | 导出 DocumentBlock |
| `backend/migrations/versions/0006_create_document_blocks.py` | 新增 | 创建 `document_blocks` 表、外键和索引 |
| `backend/app/schemas/files.py` | 修改 | 新增 block-backed chunk debug 响应 schema |
| `backend/app/services/document_blocks.py` | 新增 | 新增 MinerU zip 标准化、document_blocks 写入、debug chunks 列表 |
| `backend/app/services/files.py` | 修改 | 在 status 中接入 normalizing 标准化，并新增 debug chunks 查询服务 |
| `backend/app/api/v1/files.py` | 修改 | 新增 `GET /files/{file_id}/chunks` 调试接口 |
| `backend/tests/test_files_api.py` | 修改 | 更新 MinerU fake zip 测试，覆盖 document_blocks 标准化和 debug chunks |
| `docs/progress/step-009-document-blocks-normalization.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步 |
| `docs/progress/README.md` | 修改 | 同步总进度索引与下一步建议 |

## 5. 关键实现说明

- `document_blocks.metadata` 是 SDD 字段；由于 SQLAlchemy Declarative 中 `metadata` 是保留属性，模型中使用 `block_metadata`，数据库列名仍为 `metadata`。
- Markdown 标准化最小假设：按空行拆为段落；以 `#` 开头的段落标记为 `heading`，其他标记为 `text`。
- JSON 标准化最小假设：递归寻找包含文本字段的 dict，支持常见字段 `content`、`text`、`md`、`markdown`。
- 当前 `GET /files/{file_id}/chunks` 返回的是 document_blocks 调试视图，不是真正 chunks_metadata。原因是 chunks_metadata 尚未进入本步骤。
- `source_locator` 目前基于 block 元数据生成：
  - 有 `page_number`：`pdf:p{page_number}`。
  - 有 `slide_number`：`pptx:slide-{slide_number}`。
  - 有 `sheet_name`：`xlsx:{sheet_name}`，如有 row range 则追加行范围。
  - 否则：`block:{source_name}#{index}`。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Python 版本检查 | `python3.11 --version` | 通过 | 当前为 Python 3.11.13 |
| Docker daemon 检查 | `docker info --format '{{.ServerVersion}}'` | 通过 | Docker Server 26.1.3 正常响应 |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 后端 Ruff 检查 | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端 Black 检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 58 files would be left unchanged |
| 后端 Mypy 检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | no issues found in 51 source files |
| 后端单元/接口测试 | `backend/.venv/bin/pytest` | 通过 | 29 passed，40 warnings；warnings 为 TestClient/httpx 与短测试 JWT secret 警告 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 镜像构建完成 |
| Migration 执行 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 已从 `0005_files_parse_jobs` 升级到 `0006_document_blocks` |
| Migration 版本确认 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "select version_num from alembic_version;"` | 通过 | 当前版本 `0006_document_blocks` |
| 数据表检查 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "\\d document_blocks"` | 通过 | 表、外键、索引均已落库 |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 29 passed，1 warning |
| 后端启动检查 | `docker compose up -d --no-deps --force-recreate backend-api` + `GET /api/v1/health` | 通过 | 健康接口返回 `ok` |
| 真实标准化 smoke | 上传文件、向 MinIO 写入模拟 MinerU zip、设置 parse_job normalizing、调用 status 和 chunks | 通过 | parse_job 变为 `chunking`，progress 50，debug chunks 返回 4 个 block，JSON block locator 为 `pdf:p3` |

## 7. 当前未完成事项

- 未实现真正的 chunks_metadata 表。
- 未实现 chunking。
- 未实现 content_hash、token_count 的正式 chunk 计算。
- 未实现 Embedding、Qdrant indexing。
- 未实现只让最新成功 parse_job 的产物进入 active 检索。
- 未实现真实 MinerU 在线解析验证，因为当前环境仍未配置 `MINERU_API_TOKEN`。

## 8. 风险与注意事项

- MinerU zip 内部文件结构可能随 MinerU 平台返回格式变化。本步骤支持 Markdown 与常见 JSON 结构，其他复杂结构需在拿到真实样本后补强。
- 当前 `GET /files/{file_id}/chunks` 是 document_blocks 的调试视图，不是最终 chunks_metadata。后续 Step 010 应替换为真实 chunks 查询。
- Markdown 按段落拆 block 是 MVP 最小实现，不等同于最终 chunking 策略。
- `token_count` 当前在 debug chunks 中使用简单空白分词计数，不是最终 tokenizer。

## 9. 下一步建议

进入 Step 010：chunks_metadata 与基础 chunking。

建议 Step 010 聚焦：

- 新增 `chunks_metadata` 表与 migration。
- 从 document_blocks 生成 chunks。
- 生成 `source_locator`。
- 计算 `content_hash`。
- 计算基础 `token_count`。
- 将 parse_job 从 `chunking` 推进到 `embedding`。
- 让 `GET /files/{file_id}/chunks` 返回真实 chunks_metadata。

暂不在 Step 010 同时实现 embedding-service 和 Qdrant indexing，除非基础 chunking 很快完成且验证清晰。
