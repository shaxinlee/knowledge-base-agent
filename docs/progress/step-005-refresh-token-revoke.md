# Step 005：Phase 1-D Refresh Token Logout/Revoke

## 1. 本步骤目标

实现 `POST /api/v1/auth/logout`，确保 logout 后同一个 refresh token 不可继续用于 `/auth/refresh`，完成 Phase 1 中 TDD-AUTH-008 的剩余认证闭环。

本步骤不处理知识库、文件上传、前端页面联调或 Phase 2 功能。

## 2. 对应 SDD 条目

- `3.2 后端`：认证必须使用 JWT access token + refresh token。
- `6 Auth API`：包含 `POST /api/v1/auth/logout`。
- `7 开发里程碑 / Phase 1`：JWT refresh token。
- `10 禁止 AI Agent 自行变更的架构决策`：认证必须使用 JWT access token + refresh token。
- `docs/api/frontend-backend-api-contract.md / 3. Auth API`：logout 请求为 refresh token，响应 `204 No Content`。
- `docs/tests/TDD.v0.1.md / TDD-AUTH-008`：logout 后复用 refresh token，refresh token 不可继续使用。

## 3. 本步骤完成内容

- 新增 `RevokedRefreshToken` 模型。
- 新增 `0003_revoked_refresh_tokens` migration。
- JWT payload 新增 `jti` 字段，用于唯一标识 token。
- 新增 refresh token 吊销检查。
- 新增 refresh token 吊销写入逻辑。
- `POST /api/v1/auth/refresh` 增加吊销检查。
- 新增 `POST /api/v1/auth/logout`。
- logout 要求当前 access token，并校验 refresh token 归属当前用户。
- logout 成功后写入 `revoked_refresh_tokens`，再次 refresh 或重复 logout 返回 `UNAUTHORIZED`。
- 同步前端 API 类型、API contract 和 TDD 说明。
- 新增 logout/revoke 测试。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/__init__.py` | 修改 | 导出 `RevokedRefreshToken` |
| `backend/app/models/token.py` | 新增 | 定义 refresh token 吊销表模型 |
| `backend/migrations/versions/0003_create_revoked_refresh_tokens.py` | 新增 | 创建 `revoked_refresh_tokens` 表 |
| `backend/app/core/security.py` | 修改 | JWT payload 增加 `jti`，decode 时校验 `jti` 存在 |
| `backend/app/schemas/auth.py` | 修改 | 新增 `LogoutRequest` |
| `backend/app/services/auth.py` | 修改 | 新增 refresh token 吊销检查和吊销写入 |
| `backend/app/api/v1/auth.py` | 修改 | 新增 `/auth/logout`，refresh 增加吊销检查 |
| `backend/tests/test_auth_api.py` | 修改 | 增加 logout 后 refresh token 不可复用测试 |
| `backend/tests/test_auth_security.py` | 修改 | 增加 JWT `jti` 校验 |
| `backend/tests/test_user_models.py` | 修改 | 增加 `revoked_refresh_tokens` 表结构测试 |
| `frontend/src/api/types.ts` | 修改 | 新增 `LogoutRequest` 类型 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 补充 logout 后 refresh token 不可继续用于 refresh |
| `docs/tests/TDD.v0.1.md` | 修改 | 补充 logout 用例要求服务端记录 refresh token 吊销状态 |
| `docs/progress/README.md` | 修改 | 追加 Step 005 状态和下一步建议 |
| `docs/progress/step-005-refresh-token-revoke.md` | 新增 | 本步骤进度记录 |

## 5. 关键实现说明

- Refresh token 仍然是 JWT，但新增 `jti` 作为唯一 token id。
- 新增 `revoked_refresh_tokens` 表，字段包括：
  - `id`
  - `jti`
  - `user_id`
  - `expires_at`
  - `revoked_at`
  - `created_at`
- `/auth/refresh` 在签发新 token 前检查 refresh token 的 `jti` 是否已吊销。
- `/auth/logout` 要求 Authorization access token，并校验 refresh token 的 `sub` 与当前用户一致。
- logout 成功后写入吊销记录，返回 `204 No Content`。
- 已吊销 refresh token 再用于 refresh 或重复 logout 会返回 `401 UNAUTHORIZED`。

最小合理假设：

SDD 和 API contract 要求 refresh token logout 后不可复用，但未定义 refresh token 存储表。本步骤采用最小持久化方案：只存储已吊销 refresh token 的 `jti`，不存储完整 token 明文。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Ruff lint | `. .venv/bin/activate && ruff check app tests migrations` | 通过 | 所有检查通过 |
| Black 格式检查 | `. .venv/bin/activate && black --check app tests migrations` | 通过 | 36 个文件无需重新格式化 |
| MyPy 类型检查 | `. .venv/bin/activate && mypy app tests` | 通过 | 32 个源文件无类型问题 |
| 本地单元测试 | `. .venv/bin/activate && pytest` | 通过 | 17 passed，1 warning；warning 为 Starlette TestClient deprecation |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 新增模型、migration 和 logout API 已进入容器镜像 |
| Alembic migration 执行 | `docker compose run --rm --no-deps backend-api alembic upgrade head` | 通过 | 成功执行 `0002_users_profiles -> 0003_revoked_refresh_tokens` |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 17 passed，1 warning |
| 真实数据库 logout 链路 | 容器内 TestClient 执行 login、logout、refresh-after-logout | 通过 | login=200，logout=204，refresh-after-logout=401 `UNAUTHORIZED` |
| Alembic 版本检查 | 查询 PostgreSQL `alembic_version` | 通过 | 当前为 `0003_revoked_refresh_tokens` |
| 吊销记录检查 | 查询 `revoked_refresh_tokens` count | 通过 | 至少 1 条吊销记录 |
| 字段落库检查 | 查询 `information_schema.columns` | 通过 | 6 个字段均已落库且 NOT NULL 符合预期 |

## 7. 当前未完成事项

- 未实现过期 revoked token 的清理任务。
- 未实现 refresh token 轮换后自动吊销旧 refresh token；当前只在 logout 时吊销指定 refresh token。
- 未实现 Phase 2 知识库 CRUD。

## 8. 风险与注意事项

- `revoked_refresh_tokens` 是基于 TDD-AUTH-008 的最小持久化假设新增的表；它不存储完整 refresh token，只存储 `jti`。
- 后续可以通过 Celery cleanup 清理 `expires_at` 已过期的吊销记录。
- 当前 logout 需要 access token 和 refresh token；这符合 API contract “当前登录用户”要求，同时避免用户吊销不属于自己的 refresh token。
- 如果后续需要更强会话控制，可扩展为 refresh token allowlist/session 表，但这超出本步骤范围。

## 9. 下一步建议

进入 Step 006：Phase 2-A 知识库模型、CRUD 与审计基础。

建议 Step 006 聚焦：

- `knowledge_bases` 表。
- `audit_logs` 表。
- KnowledgeBase CRUD API。
- Admin-only 创建/更新/删除。
- User 只读 active 知识库。
- 删除知识库软删除。
- Admin 高危操作写 audit_logs。

文件上传、MinIO、hash 去重和 parse_job 建议放到后续 Step 007。
