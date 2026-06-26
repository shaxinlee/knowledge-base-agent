# Step 007：文件模型、上传校验与 MinIO raw-files 基础

## 1. 本步骤目标

完成 SDD v0.1 Phase 2-B 的文件上传基础闭环：新增 `files` 表、最小 `parse_jobs` 表、文件上传 API、上传校验、SHA-256 hash、同名拒绝、hash 重复 warning、force 上传、MinIO `raw-files` 原始文件保存、文件列表/状态查询、文件软删除与删除审计。

本步骤只创建 queued parse_job 记录，用于满足上传接口契约和后续解析衔接；不执行异步解析、不调用 MinerU、不生成 document_blocks/chunks、不写入 Qdrant。

## 2. 对应 SDD 条目

- `2.1.1 支持文件类型`：支持 `.pdf .md .docx .txt .xlsx .xls .csv .pptx .png .jpg .jpeg .webp`。
- `2.1.2 上传校验规则`：Admin 权限、knowledge_base active、50MB 限制、扩展名白名单、SHA-256 hash、同名拒绝、hash 重复 warning 与 force 上传。
- `2.1.3 文件保存`：后端接收 multipart/form-data，由后端写入 MinIO；使用 `raw-files` bucket。
- `4.5 files`：files 字段、状态、唯一约束和 hash 去重逻辑。
- `4.6 parse_jobs`：本步骤创建最小 queued parse_job 记录；状态机执行留到后续解析步骤。
- `6.7 Files API`：文件列表、上传、文件详情、状态查询、删除。
- `Phase 2：知识库 CRUD 与文件管理`：覆盖 files 表、文件上传 API、大小/类型/数量校验、file_hash、同名拒绝、hash 重复 warning、MinIO raw-files、文件列表、状态查询、软删除和 audit_logs 写入。
- TDD：`TDD-FILE-001` 至 `TDD-FILE-012` 中本阶段可执行的上传、权限、校验、重复、force、MinIO、列表、删除审计部分。

## 3. 本步骤完成内容

- 新增 `File` SQLAlchemy 模型与 `FileStatus` 枚举。
- 新增 `ParseJob` SQLAlchemy 模型与 `ParseJobStatus` 枚举。
- 新增 `0005_files_parse_jobs` migration，创建 `files`、`parse_jobs` 表、外键、检查约束和索引。
- 新增文件 API：
  - `GET /api/v1/knowledge-bases/{knowledge_base_id}/files`
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/files/upload`
  - `GET /api/v1/files/{file_id}`
  - `GET /api/v1/files/{file_id}/status`
  - `DELETE /api/v1/files/{file_id}`
- 新增 MinIO object storage 适配层：
  - 自动创建 `raw-files` bucket。
  - 上传原始文件对象。
  - 写入对象 metadata：`file_id`、`knowledge_base_id`、`file_hash`。
- 新增上传校验：
  - User 上传返回 `403 FORBIDDEN`。
  - 非 active 知识库上传返回 `409 KNOWLEDGE_BASE_INACTIVE`。
  - 超大小返回 `413 FILE_TOO_LARGE`。
  - 单次超过数量限制返回 `400 TOO_MANY_FILES`。
  - 不支持扩展名返回 `415 UNSUPPORTED_FILE_TYPE`。
  - 同一知识库同名返回 `409 DUPLICATE_FILE_NAME`。
  - 同一知识库 hash 重复但不同名返回 `409 DUPLICATE_FILE_HASH`，details 包含 duplicates 与 `can_force_upload=true`。
  - `force=true` 允许 hash 重复但不同名继续上传。
- 上传成功后：
  - 创建 file 记录，状态为 `queued`。
  - 创建 parse_job 记录，状态为 `queued`、progress 为 0。
  - 将 file.latest_parse_job_id 指向新 parse_job。
  - 写入 `upload_file` 审计日志。
- 删除文件：
  - 执行软删除，状态置为 `deleted`。
  - 写入 `deleted_at`。
  - 写入 `delete_file` 审计日志。
- 同步修正 SDD 与接口契约冲突：
  - FileStatus 按 SDD 统一为 `uploaded/queued/processing/indexed/partially_indexed/failed/deleting/deleted`。
  - ParseJobStatus 保留解析阶段细分：`queued/parsing/normalizing/chunking/embedding/indexing/indexed/partially_indexed/failed/cancelled`。
- 新增后端依赖：
  - `python-multipart`：支持 FastAPI multipart/form-data 文件上传。
  - `minio`：使用 MinIO 官方 Python 客户端写入对象存储。
- 完成真实 smoke 验证：
  - Admin 登录。
  - 创建知识库。
  - 上传 `.txt` 文件。
  - PostgreSQL 中确认 file 与 parse_job。
  - MinIO `raw-files` 中确认对象存在，metadata 可追溯 file_id。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 新增 `minio` 与 `python-multipart` 依赖 |
| `backend/app/core/config.py` | 修改 | 新增上传限制与 MinIO 配置项 |
| `backend/app/models/file.py` | 新增 | 新增 File 模型与 FileStatus 枚举 |
| `backend/app/models/parse_job.py` | 新增 | 新增 ParseJob 模型与 ParseJobStatus 枚举 |
| `backend/app/models/__init__.py` | 修改 | 导出 File、FileStatus、ParseJob、ParseJobStatus |
| `backend/migrations/versions/0005_create_files_and_parse_jobs.py` | 新增 | 创建 files 与 parse_jobs 表、约束和索引 |
| `backend/app/schemas/files.py` | 新增 | 新增文件、parse_job、上传响应、状态响应 schema |
| `backend/app/services/object_storage.py` | 新增 | 新增 MinIO 对象存储适配层 |
| `backend/app/services/files.py` | 新增 | 实现文件上传校验、MinIO 保存、hash 去重、列表、状态、删除与审计 |
| `backend/app/api/v1/files.py` | 新增 | 新增 Files API 路由 |
| `backend/app/api/v1/router.py` | 修改 | 注册 Files API 路由 |
| `backend/tests/test_files_api.py` | 新增 | 新增文件上传、权限、校验、重复、force、列表、状态、删除审计测试 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 将 FileStatus 同步为 SDD 状态，并保留 ParseJobStatus 细分 |
| `docs/api/openapi.v0.1.yaml` | 修改 | 将 OpenAPI FileStatus 同步为 SDD 状态 |
| `frontend/src/api/types.ts` | 修改 | 将前端 FileStatus 类型同步为 SDD 状态 |
| `docs/progress/step-007-files-upload-minio.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步 |
| `docs/progress/README.md` | 修改 | 同步总进度索引与下一步建议 |

## 5. 关键实现说明

- 上传入口使用 FastAPI multipart/form-data，字段为 `files` 与可选 `force`。
- `prepare_upload` 负责读取上传内容、校验扩展名、校验大小并计算 SHA-256。
- 同名文件以 `knowledge_base_id + file_name + deleted_at IS NULL` 判断，数据库 migration 中也创建了 PostgreSQL partial unique index：`uq_files_kb_filename_active`。
- hash 重复以同一 knowledge_base 中 active 文件的 `file_hash` 判断；不同名且同 hash 时，非 force 返回 `DUPLICATE_FILE_HASH`。
- MinIO storage key 格式为：
  - `knowledge-bases/{knowledge_base_id}/files/{file_id}/{file_name}`
- 上传成功后 file 与 parse_job 都保持 `queued`。本步骤只负责排队，不处理 MinerU 调用。
- `GET /files/{file_id}/status` 返回当前 file status 与 latest parse_job。
- 文件删除当前只软删除 file 并写审计；chunks inactive、Qdrant points 清理、cleanup job 需在后续 chunks/index 阶段补齐。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 依赖安装 | `backend/.venv/bin/pip install -e "backend[dev]"` | 通过 | 已安装 `minio` 与 `python-multipart` |
| Python 版本检查 | `python3.11 --version` | 通过 | 当前为 Python 3.11.13 |
| Docker daemon 检查 | `docker info --format '{{.ServerVersion}}'` | 通过 | Docker Server 26.1.3 正常响应 |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 后端 Ruff 检查 | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端 Black 检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 54 files would be left unchanged |
| 后端 Mypy 检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | no issues found in 48 source files |
| 后端单元/接口测试 | `backend/.venv/bin/pytest` | 通过 | 27 passed，36 warnings；warnings 为 TestClient/httpx 与短测试 JWT secret 警告 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 镜像构建完成 |
| PostgreSQL 启动检查 | `docker compose up -d postgres` | 通过 | PostgreSQL 容器 running |
| Migration 执行 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 已从 `0004_kb_audit` 升级到 `0005_files_parse_jobs` |
| Migration 版本确认 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "select version_num from alembic_version;"` | 通过 | 当前版本 `0005_files_parse_jobs` |
| 数据表检查 | `\d files`、`\d parse_jobs` | 通过 | 两张表、约束、索引均已落库 |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 27 passed，1 warning |
| 后端启动检查 | `docker compose up -d --no-deps --force-recreate backend-api` + `GET /api/v1/health` | 通过 | 健康接口返回 `ok` |
| MinIO 直连拉取 | `docker compose up -d postgres minio` | 失败后已绕过 | Docker Hub 连接被拒绝 |
| MinIO 备用镜像拉取 | `docker pull quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z` 并 tag 到 Compose 使用的镜像名 | 通过 | 使用同版本 MinIO 镜像完成 |
| MinIO 启动检查 | `docker compose up -d minio` + health check | 通过 | MinIO 容器已启动 |
| 真实上传 smoke | Admin 登录、创建知识库、上传 `.txt`、查询 DB、MinIO stat_object | 通过 | file 状态 queued，parse_job queued，`raw-files` 对象存在，metadata_file_id 与 file_id 一致 |

## 7. 当前未完成事项

- 未实现 Celery worker 或后台解析执行。
- 未调用 MinerU API。
- 未实现 parse_job 状态机推进。
- 未实现 document_blocks、chunks_metadata、Qdrant indexing。
- 未实现 retry-parse。
- 未实现 chunks inactive、Qdrant points 删除或 cleanup job。
- 未将真实 Files API 接入前端页面，前端仍主要使用 mock 数据。

## 8. 风险与注意事项

- 本步骤新增了必要依赖 `minio` 与 `python-multipart`，已通过本地与容器构建验证。
- Docker Hub 直连 MinIO 镜像失败，本步骤通过 `quay.io/minio/minio` 拉取同版本镜像并重新 tag 后完成验证。
- SDD 与原 API contract 对 FileStatus 存在差异：SDD 是较粗粒度 file 状态，parse 阶段细分属于 ParseJobStatus。本步骤已按 SDD 修正 FileStatus。
- 当前上传实现会把单个文件内容读入内存后再写入 MinIO。SDD 单文件限制为 50MB，此方式对 MVP 可接受；后续如需更大文件，应改为流式 hash 与流式上传。
- 本步骤真实 smoke 在当前数据库中创建了一个测试知识库和测试文件记录，用于验证 MinIO raw-files 对象存在。

## 9. 下一步建议

进入 Step 008：parse_jobs 与 MinerU API client。

建议 Step 008 聚焦：

- MinerU API 配置项与密钥读取。
- 按用户要求参考 `https://mineru.net/apiManage/docs`，采用 API 调用方式。
- 为 queued parse_job 增加解析触发接口或最小后台执行入口。
- 将 MinIO 原始文件交给 MinerU：优先确认采用对象可访问 URL 还是 MinerU upload-url 流程。
- 轮询 MinerU task 状态。
- 将 MinerU task_id、状态、错误信息写回 parse_jobs。
- 下载/保存 MinerU 解析产物到 MinIO `parsed-results`。
- 暂不在同一步做复杂 chunking/indexing，除非 MinerU 调用闭环很小且验证清晰。
