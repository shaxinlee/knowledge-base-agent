# Step 004：Phase 1-C 用户管理与 RBAC 权限边界

## 1. 本步骤目标

实现 SDD v0.1 Phase 1 的 Admin 用户管理与 RBAC 权限边界，包括 Admin-only dependency、用户列表、创建用户、更新用户、禁用/启用用户、重置密码，以及普通 User 访问 Admin API 返回 403。

本步骤不实现 refresh token logout/revoke，不处理知识库、文件上传、审计日志或 Phase 2 功能。

## 2. 对应 SDD 条目

- `4.2 users`：用户角色、状态、禁用用户保留历史会话和审计日志、后续用户只能由 Admin 创建。
- `7 开发里程碑 / Phase 1：认证、用户与权限`：覆盖 Admin 创建用户、Admin 禁用/启用用户、Admin 重置密码、RBAC dependency。
- `8.5 安全约束`：默认不开放注册，默认只有 Admin 可创建用户。
- `docs/api/frontend-backend-api-contract.md / 4. Users API`：覆盖 users 列表、创建、更新、禁用、启用、重置密码。
- `docs/tests/TDD.v0.1.md / 6.2 认证、用户与权限`：覆盖 TDD-AUTH-002、TDD-AUTH-003、TDD-AUTH-005 的用户管理和权限边界部分。

## 3. 本步骤完成内容

- 新增 Admin-only RBAC dependency：`require_admin_user`。
- 新增 Users API schema。
- 新增 Users service 层。
- 新增 `GET /api/v1/users`，支持分页、keyword、role、is_active 筛选。
- 新增 `POST /api/v1/users`，Admin 创建用户。
- 新增 `PATCH /api/v1/users/{user_id}`，Admin 更新 display_name 和 role。
- 新增 `POST /api/v1/users/{user_id}/disable`，Admin 禁用用户。
- 新增 `POST /api/v1/users/{user_id}/enable`，Admin 启用用户，并清理登录失败锁定状态。
- 新增 `POST /api/v1/users/{user_id}/reset-password`，Admin 重置用户密码，并清理登录失败锁定状态。
- 新增 Users API 测试，覆盖 Admin 用户管理链路、普通 User 权限拒绝、重复 email/username 拒绝。
- 同步 API contract、OpenAPI、前端类型和 TDD 说明。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/api/deps.py` | 修改 | 新增 `require_admin_user` RBAC dependency |
| `backend/app/api/v1/router.py` | 修改 | 挂载 Users router |
| `backend/app/api/v1/users.py` | 新增 | Users API 路由 |
| `backend/app/schemas/users.py` | 新增 | Users API 请求/响应 schema |
| `backend/app/services/users.py` | 新增 | 用户列表、创建、更新、禁用、启用、重置密码 service |
| `backend/tests/test_users_api.py` | 新增 | 用户管理与 RBAC 权限测试 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 创建用户请求示例增加 `email` |
| `docs/api/openapi.v0.1.yaml` | 修改 | `UserCreateRequest` 增加必填 `email` 字段 |
| `frontend/src/api/types.ts` | 修改 | `UserCreateRequest` 增加 `email` |
| `docs/tests/TDD.v0.1.md` | 修改 | 说明 Admin 创建 user 测试数据必须包含唯一 email |
| `docs/progress/README.md` | 修改 | 追加 Step 004 状态和后续建议 |
| `docs/progress/step-004-users-rbac.md` | 新增 | 本步骤进度记录 |

## 5. 关键实现说明

- `require_admin_user` 复用 `get_current_user`，当当前用户 `role != admin` 时返回 `403 FORBIDDEN`。
- 用户列表默认过滤 `deleted_at IS NULL`，符合 SDD 软删除记录不得参与默认查询的要求。
- 用户列表支持：
  - `page`
  - `page_size`
  - `keyword`
  - `role`
  - `is_active`
- `is_active=true` 映射到 `status=active`，`is_active=false` 映射到 `status=disabled`。
- 创建用户时使用 bcrypt 保存 `password_hash`，默认 `status=active`。
- 重置密码会更新 bcrypt hash，并清理 `failed_login_count` 和 `locked_until`。
- 启用用户也会清理 `failed_login_count` 和 `locked_until`，避免启用后仍处于锁定状态。
- `email` 字段处理：
  - SDD 明确 `users.email VARCHAR UNIQUE NOT NULL`。
  - 现有 API contract 和前端类型原先未包含 `email`。
  - 本步骤按 SDD 数据约束要求后端创建用户请求必须包含 `email`，并同步更新 API contract、OpenAPI、前端类型与 TDD 说明。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Ruff lint | `. .venv/bin/activate && ruff check app tests migrations` | 通过 | 所有检查通过 |
| Black 格式检查 | `. .venv/bin/activate && black --check app tests migrations` | 通过 | 34 个文件无需重新格式化 |
| MyPy 类型检查 | `. .venv/bin/activate && mypy app tests` | 通过 | 31 个源文件无类型问题 |
| 本地单元测试 | `. .venv/bin/activate && pytest` | 通过 | 14 passed，1 warning；warning 为 Starlette TestClient deprecation |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| OpenAPI YAML 解析 | 使用 Python `yaml.safe_load` 读取 `docs/api/openapi.v0.1.yaml` | 通过 | `UserCreateRequest.required` 包含 `email` |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 新增 Users API 已进入容器镜像 |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 14 passed，1 warning |
| 真实数据库用户管理链路 | 容器内 TestClient 执行 Admin login、create user、user login、user list forbidden、disable、enable、reset-password、new login | 通过 | create=201，普通 user 访问 `/users` 返回 `403 FORBIDDEN`，禁用/启用/重置密码均成功 |
| 真实数据库落库检查 | 查询 PostgreSQL 中 `step004_%` 用户 | 通过 | 新建 user 为 `role=user`、`status=active` |
| Alembic 版本检查 | 查询 `alembic_version` | 通过 | 当前仍为 `0002_users_profiles`，本步骤未新增数据库结构 |

## 7. 当前未完成事项

- 未实现 `POST /api/v1/auth/logout` 的 refresh token revoke。
- 未实现 Users profile 的 `GET/PATCH /users/me/profile`。
- 未实现 audit_logs；Admin 用户管理是否写审计日志需在审计模块落地后补齐。
- 未实现 Phase 2 知识库 CRUD。

## 8. 风险与注意事项

- `UserCreateRequest.email` 是本步骤为满足 SDD `users.email UNIQUE NOT NULL` 约束而加入的字段。API contract、OpenAPI、前端类型和 TDD 说明已同步更新。
- 当前 Users API 返回对象不包含 email，保持与既有 User response contract 一致；如前端需要展示 email，需在后续明确变更响应契约。
- `POST /api/v1/auth/logout` 仍无法满足 TDD-AUTH-008，因为 refresh token 当前是无状态 JWT；需要服务端 token 状态存储或 blacklist。
- Admin 用户管理操作未来应写入 audit_logs；由于 audit_logs 表和审计服务尚未进入当前阶段，本步骤未实现审计写入。

## 9. 下一步建议

建议下一步优先处理 Step 005：refresh token logout/revoke。

原因：这是 Phase 1 TDD-AUTH-008 的剩余项，需要先确认是否新增 refresh token 存储表或 token blacklist。若暂缓该项，则进入 Phase 2-A：知识库模型、CRUD 与审计基础。
