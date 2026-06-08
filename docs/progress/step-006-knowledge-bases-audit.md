# Step 006：知识库模型、CRUD 与审计基础

## 1. 本步骤目标

完成 SDD v0.1 Phase 2-A 的知识库与审计基础能力：新增 `knowledge_bases`、`audit_logs` 数据模型与 migration，实现知识库 CRUD API、Admin/User 权限边界、知识库软删除、知识库操作审计写入，并提供 Admin-only 审计日志查询接口。

本步骤不处理文件上传、MinIO、文件 hash 去重、cleanup job 实际任务系统、MinerU 解析、索引、检索、问答或前端页面联调。

## 2. 对应 SDD 条目

- `4.4 knowledge_bases`：知识库字段、状态 `active/deleting/deleted`、Admin 创建/编辑/删除、User 查看 active 知识库、软删除、删除后创建 cleanup job。
- `4.14 audit_logs`：审计日志字段与记录范围，包括 `create_knowledge_base`、`update_knowledge_base`、`delete_knowledge_base`。
- `6.6 Knowledge Bases API`：`GET/POST/GET by id/PATCH/DELETE /api/v1/knowledge-bases`，GET 允许 admin 和 user，POST/PATCH/DELETE admin only。
- `6.11 Audit Logs API`：`GET /api/v1/audit-logs`，admin only。
- `Phase 2：知识库 CRUD 与文件管理`：本步骤覆盖其中的 `knowledge_bases 表`、`KnowledgeBase CRUD`、`audit_logs 写入`。
- TDD：`TDD-KB-001`、`TDD-KB-002`、`TDD-KB-003`、`TDD-KB-004`、`TDD-KB-005`、`TDD-AUDIT-001`、`TDD-AUDIT-004`、`TDD-AUDIT-005` 的本阶段可执行部分。

## 3. 本步骤完成内容

- 新增 `KnowledgeBase` SQLAlchemy 模型与 `KnowledgeBaseStatus` 枚举。
- 新增 `AuditLog` SQLAlchemy 模型。
- 新增 `0004_kb_audit` migration，创建 `knowledge_bases`、`audit_logs` 表与关键索引。
- 新增知识库 API：
  - `GET /api/v1/knowledge-bases`
  - `POST /api/v1/knowledge-bases`
  - `GET /api/v1/knowledge-bases/{knowledge_base_id}`
  - `PATCH /api/v1/knowledge-bases/{knowledge_base_id}`
  - `DELETE /api/v1/knowledge-bases/{knowledge_base_id}`
- 新增审计日志 API：
  - `GET /api/v1/audit-logs`
- 实现权限边界：
  - Admin 可创建、更新、删除、查询知识库。
  - User 只能查询 active 知识库。
  - User 创建知识库返回 `403 FORBIDDEN`。
  - User 查询非 active 知识库返回 `404 RESOURCE_NOT_FOUND`。
  - User 查询审计日志返回 `403 FORBIDDEN`。
- 实现知识库软删除：
  - 删除时将 `status` 置为 `deleted`。
  - 写入 `deleted_at`。
  - 默认列表不返回 deleted 知识库。
  - Admin 可通过 `status=deleted` 查询 deleted 知识库。
- 实现知识库操作审计：
  - 创建写入 `create_knowledge_base`。
  - 更新写入 `update_knowledge_base`。
  - 删除写入 `delete_knowledge_base`。
  - 记录 actor、resource、details、IP、User-Agent。
- 同步修正 SDD 与接口契约冲突：
  - API contract、OpenAPI、前端类型、TDD 中的知识库状态统一为 SDD 的 `active/deleting/deleted`。
- 启动后端服务完成 smoke 验证：
  - 默认 Admin 登录。
  - 创建知识库。
  - 删除知识库。
  - 查询删除审计日志。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/knowledge_base.py` | 新增 | 新增知识库模型与 SDD 状态枚举 |
| `backend/app/models/audit_log.py` | 新增 | 新增审计日志模型 |
| `backend/app/models/__init__.py` | 修改 | 导出 `KnowledgeBase`、`KnowledgeBaseStatus`、`AuditLog` |
| `backend/migrations/versions/0004_create_knowledge_bases_and_audit_logs.py` | 新增 | 创建 `knowledge_bases`、`audit_logs` 表、约束和索引 |
| `backend/app/schemas/knowledge_bases.py` | 新增 | 新增知识库请求与响应 schema |
| `backend/app/schemas/audit_logs.py` | 新增 | 新增审计日志列表响应 schema |
| `backend/app/services/knowledge_bases.py` | 新增 | 实现知识库列表、创建、查看、更新、软删除和审计写入 |
| `backend/app/services/audit_logs.py` | 新增 | 实现审计日志创建与查询 |
| `backend/app/api/v1/knowledge_bases.py` | 新增 | 新增知识库 API 路由 |
| `backend/app/api/v1/audit_logs.py` | 新增 | 新增审计日志 API 路由 |
| `backend/app/api/v1/router.py` | 修改 | 注册知识库与审计日志路由 |
| `backend/tests/test_knowledge_bases_api.py` | 新增 | 新增知识库 CRUD、权限、软删除、审计查询测试 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 将 `KnowledgeBaseStatus` 从 `archived` 修正为 SDD 的 `deleting` |
| `docs/api/openapi.v0.1.yaml` | 修改 | 将 OpenAPI 知识库状态枚举同步为 `active/deleting/deleted` |
| `docs/tests/TDD.v0.1.md` | 修改 | 将 inactive 知识库上传用例中的状态描述同步为 `deleting/deleted` |
| `frontend/src/api/types.ts` | 修改 | 将前端 `KnowledgeBaseStatus` 同步为 `active/deleting/deleted`，并允许审计 `resource_id` 为 null |
| `docs/progress/step-006-knowledge-bases-audit.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步 |
| `docs/progress/README.md` | 修改 | 同步总进度索引与下一步建议 |

## 5. 关键实现说明

- `KnowledgeBaseStatus` 以 SDD 为准，只允许 `active`、`deleting`、`deleted`。
- `knowledge_bases.settings` 默认写入 SDD 示例中的基础设置：`default_top_k=8`、`strict_citation=true`、`answer_language=zh`。
- `GET /knowledge-bases` 对 User 强制追加 active 过滤；即使 User 显式传入其他 status，也只返回 active 知识库。
- `DELETE /knowledge-bases/{id}` 执行软删除，不物理删除数据，并写入 `delete_knowledge_base` 审计日志。
- `audit_logs` 的 API 字段使用契约中的 `actor_id`，数据库字段保持 SDD 的 `actor_user_id`。
- `file_count` 与 `chunk_count` 目前固定为 0，因为 files/chunks 表尚未进入本步骤。
- cleanup job 的实际创建未实现：当前项目还没有 cleanup_jobs 表或任务队列抽象，本步骤只完成软删除与审计，并将 cleanup job 留到文件/清理任务阶段。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Python 版本检查 | `python3.11 --version` | 通过 | 当前为 Python 3.11.13 |
| Docker daemon 检查 | `docker info --format '{{.ServerVersion}}'` | 通过 | Docker Server 26.1.3 正常响应 |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 后端 Ruff 检查 | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端 Black 检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 46 files would be left unchanged |
| 后端 Mypy 检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | no issues found in 41 source files |
| 后端单元/接口测试 | `backend/.venv/bin/pytest` | 通过 | 21 passed，24 warnings；warnings 为 TestClient/httpx 与短测试 JWT secret 警告 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 镜像构建完成 |
| PostgreSQL 启动检查 | `docker compose up -d postgres` | 通过 | PostgreSQL 容器 running/healthy |
| Migration 执行 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 已从 `0003_revoked_refresh_tokens` 升级到 `0004_kb_audit` |
| Migration 版本确认 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "select version_num from alembic_version;"` | 通过 | 当前版本 `0004_kb_audit` |
| 数据表检查 | `\d knowledge_bases`、`\d audit_logs` | 通过 | 两张表、约束、索引均已落库 |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 21 passed，1 warning |
| 后端启动检查 | `docker compose up -d --no-deps backend-api` + `GET /api/v1/health` | 通过 | 健康接口返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| API smoke 验证 | 登录 Admin、创建知识库、删除知识库、查询删除审计日志 | 通过 | 删除返回 204，审计列表返回 `delete_knowledge_base` |
| 错误命令记录 | 在 `backend` 目录执行 `backend/.venv/bin/pytest` | 失败后已纠正 | 路径错误导致 `No such file or directory`，随后用正确路径重跑并通过 |
| 中间测试失败记录 | 首次 `backend/.venv/bin/pytest` | 失败后已修复 | 测试代码用字符串查询 UUID，已改为 UUID 对象；修复后完整测试通过 |

## 7. 当前未完成事项

- 未实现 files 表、文件上传、文件类型/大小/数量校验、同名拒绝、hash 重复 warning、MinIO raw-files 写入。
- 未实现 cleanup job 表或异步清理任务。SDD 要求删除知识库后创建 cleanup job，本步骤记录为后续任务。
- 未将用户管理操作补写入 audit_logs。`TDD-AUDIT-003` 需在审计服务稳定后单独补齐。
- 未实现 MinerU API 解析调用。本项将在解析任务阶段接入用户指定的 MinerU API。
- 未实现前端真实接口联调，当前前端仍主要使用 mock 数据。

## 8. 风险与注意事项

- SDD 与原 API contract/TDD/前端类型存在状态枚举冲突：SDD 是 `active/deleting/deleted`，原契约写 `active/archived/deleted`。本步骤按 SDD 优先原则修正为 `deleting`。
- `PATCH /knowledge-bases/{id}` 当前只有当 `description` 非 null 时才更新描述，因此暂不支持显式清空描述。若后续前端需要清空描述，需要增加字段是否传入的区分逻辑。
- `file_count`、`chunk_count` 目前固定为 0，后续 files/chunks 表落地后需要改为真实统计。
- 后端服务当前已通过 `docker compose up -d --no-deps backend-api` 启动，访问地址为 `http://localhost:8000`。该启动方式未启动 Redis/Qdrant/MinIO，因为本步骤不依赖这些服务。

## 9. 下一步建议

进入 Step 007：Phase 2-B 文件模型、上传校验与 MinIO raw-files 基础。

建议 Step 007 聚焦：

- `files` 表与 migration。
- 知识库 active 状态校验。
- Admin-only 文件上传入口。
- 文件大小、数量、扩展名校验。
- 同一知识库同名拒绝。
- 文件 hash 计算与 hash 重复 warning。
- MinIO raw-files 写入。
- 文件列表、状态查询、软删除和删除审计。

暂不在 Step 007 同时实现 MinerU 解析任务。MinerU API 接入建议放入 Step 008：parse_jobs 与 MinerU API client。
