# Step 003：Phase 1-B 认证基础能力

## 1. 本步骤目标

实现 SDD v0.1 Phase 1 的认证基础能力：bcrypt 密码哈希、默认 Admin 初始化、JWT access token、JWT refresh token、登录 API、刷新 token API、`auth/me` 当前用户接口，以及登录失败锁定和 disabled 用户登录拒绝。

本步骤不实现 Admin 用户管理 API、RBAC dependency、用户禁用/启用接口、重置密码接口，也不实现 refresh token logout/revoke。

## 2. 对应 SDD 条目

- `4.2 users`：默认 Admin、密码哈希、登录失败计数、锁定时间、disabled 用户不可登录。
- `7 开发里程碑 / Phase 1：认证、用户与权限`：覆盖默认 Admin 初始化、bcrypt 密码哈希、JWT access token、JWT refresh token、登录失败计数、失败 5 次锁定 15 分钟、auth/me。
- `8.5 安全约束`：默认不开放注册、密码必须 bcrypt 哈希、登录失败 5 次锁定 15 分钟、JWT secret 必须通过环境变量提供。
- `docs/api/frontend-backend-api-contract.md / 3. Auth API`：覆盖 `POST /auth/login`、`POST /auth/refresh`、`GET /auth/me`。
- `docs/tests/TDD.v0.1.md / 6.2 认证、用户与权限`：覆盖 TDD-AUTH-001、TDD-AUTH-003、TDD-AUTH-004、TDD-AUTH-006、TDD-AUTH-007 的基础能力。

## 3. 本步骤完成内容

- 新增 `bcrypt` 与 `PyJWT` 后端依赖。
- 新增 Auth 相关配置项和 `.env.example` 示例项。
- 新增 bcrypt 密码哈希与校验函数。
- 新增 JWT access token 与 refresh token 生成和解析函数。
- 新增统一业务错误 `ApiError` 与错误响应 envelope。
- 新增 Auth 请求/响应 Pydantic schema。
- 新增默认 Admin 初始化逻辑，应用启动时会尝试初始化默认 Admin。
- 新增当前用户解析 dependency。
- 新增 `POST /api/v1/auth/login`。
- 新增 `POST /api/v1/auth/refresh`。
- 新增 `GET /api/v1/auth/me`。
- 实现登录失败计数，连续 5 次失败后锁定账号 15 分钟。
- 实现 disabled 用户登录拒绝。
- 新增认证服务单元测试和 Auth API 测试。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `.env.example` | 修改 | 新增默认 Admin、JWT、登录锁定相关配置示例，并更新开发 JWT secret 示例长度 |
| `backend/pyproject.toml` | 修改 | 新增 `bcrypt` 与 `PyJWT` 依赖 |
| `backend/app/core/config.py` | 修改 | 新增认证相关 Settings 配置项 |
| `backend/app/core/errors.py` | 新增 | 统一业务错误类和错误响应 envelope |
| `backend/app/core/security.py` | 新增 | bcrypt 哈希/校验和 JWT 生成/解析 |
| `backend/app/models/user.py` | 修改 | 将模型类型调整为通用 UUID/JSON 类型，便于轻量单元测试；PostgreSQL 仍使用 JSONB 变体 |
| `backend/app/schemas/auth.py` | 新增 | Auth 请求与响应 schema |
| `backend/app/services/__init__.py` | 新增 | service 层包声明 |
| `backend/app/services/auth.py` | 新增 | 默认 Admin、登录认证、token 响应、用户响应构建逻辑 |
| `backend/app/db/init.py` | 新增 | 默认 Admin 初始化入口 |
| `backend/app/api/deps.py` | 新增 | 当前用户解析 dependency |
| `backend/app/api/v1/auth.py` | 新增 | Auth API 路由 |
| `backend/app/api/v1/router.py` | 修改 | 挂载 Auth router |
| `backend/app/main.py` | 修改 | 增加 lifespan 默认 Admin 初始化和 ApiError handler |
| `backend/tests/test_auth_security.py` | 新增 | 覆盖 bcrypt 与 JWT 基础行为 |
| `backend/tests/test_auth_api.py` | 新增 | 覆盖登录、刷新、me、缺失 token、账号锁定、disabled 用户拒绝 |
| `docs/progress/README.md` | 修改 | 追加 Step 003 状态和下一步建议 |
| `docs/progress/step-003-auth-basics.md` | 新增 | 本步骤进度记录 |

## 5. 关键实现说明

- 密码使用 `bcrypt.hashpw` 和 `bcrypt.checkpw`，数据库只保存 hash，不保存明文密码。
- JWT 使用 HS256，token payload 包含 `sub`、`type`、`iat`、`exp`。
- access token 和 refresh token 通过 `type` 字段区分，避免 refresh token 被误用为 access token。
- 默认 Admin 由 `init_default_admin()` 创建，账号来自环境变量或配置默认值：
  - `DEFAULT_ADMIN_EMAIL`
  - `DEFAULT_ADMIN_USERNAME`
  - `DEFAULT_ADMIN_PASSWORD`
  - `DEFAULT_ADMIN_DISPLAY_NAME`
- 默认 Admin 初始化只在不存在同 username/email 用户时创建，不覆盖已有用户。
- 登录成功会清空 `failed_login_count` 和 `locked_until`，并更新 `last_login_at`。
- 登录失败会递增 `failed_login_count`；达到 `LOGIN_FAILURE_LOCK_THRESHOLD=5` 后设置 `locked_until=now+15min` 并返回 `ACCOUNT_LOCKED`。
- disabled 用户登录返回 `ACCOUNT_DISABLED`。
- 缺失或无效 access token 访问 `auth/me` 返回 `UNAUTHORIZED`。
- 统一错误响应遵循 API contract 的 envelope 结构：`{"error": {"code", "message", "details", "request_id"}}`。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端依赖安装 | `. .venv/bin/activate && pip install -e ".[dev]"` | 通过 | 新增 `bcrypt`、`PyJWT` 安装成功 |
| Ruff lint | `. .venv/bin/activate && ruff check app tests migrations` | 通过 | 所有检查通过 |
| Black 格式检查 | `. .venv/bin/activate && black --check app tests migrations` | 通过 | 30 个文件无需重新格式化 |
| MyPy 类型检查 | `. .venv/bin/activate && mypy app tests` | 通过 | 27 个源文件无类型问题 |
| 本地单元测试 | `. .venv/bin/activate && pytest` | 通过 | 11 passed，1 warning；warning 为 Starlette TestClient deprecation |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 新增依赖和认证代码已进入容器镜像 |
| Alembic migration 检查 | `docker compose run --rm --no-deps backend-api alembic upgrade head` | 通过 | 数据库已处于 head，无需新增 migration |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 11 passed，1 warning；JWT 短密钥告警已通过覆盖 env 消除 |
| 默认 Admin 初始化 | `docker compose run --rm --no-deps backend-api python -c "from app.db.init import init_default_admin; init_default_admin()"` | 通过 | 默认 Admin 可初始化 |
| 真实数据库登录链路 | 使用容器内 TestClient 请求 login/refresh/me | 通过 | `login_status 200`、`refresh_status 200`、`me_status 200` |
| 默认 Admin 落库检查 | 查询 PostgreSQL `users` 和 `user_profiles` | 通过 | `admin@example.local`、`admin`、`role=admin`、`status=active`、`display_name=Administrator` |

## 7. 当前未完成事项

- 未实现 Admin 创建用户。
- 未实现 Admin 禁用/启用用户。
- 未实现 Admin 重置密码。
- 未实现 Admin-only RBAC dependency。
- 未实现 `GET /api/v1/users` 等 Users API。
- 未实现 `POST /api/v1/auth/logout` 的 refresh token revoke。
- Refresh token 当前为无状态 JWT；刷新接口会签发新 token，但旧 refresh token 在过期前仍可使用。

## 8. 风险与注意事项

- 本地 `.env` 当前可能仍使用短 `JWT_SECRET_KEY=change-me`。`.env.example` 已更新为较长开发密钥；生产部署必须设置安全随机的 `JWT_SECRET_KEY`。
- `POST /api/v1/auth/logout` 要满足 TDD-AUTH-008 的“logout 后 refresh token 不可继续使用”，需要服务端 token 状态存储或黑名单。SDD 未明确 refresh token 存储表，本步骤未擅自新增表，建议后续单独确认方案。
- 默认 Admin 初始化在应用 lifespan 中执行；如果数据库不可用，会记录异常并继续启动，避免 health 页面被数据库初始化阻塞。Docker Compose 正常依赖 PostgreSQL healthy 后可初始化成功。
- 当前统一错误 envelope 只覆盖 `ApiError`；全局 validation error 和通用 HTTPException 的统一 envelope 可在后续 API 步骤补齐。

## 9. 下一步建议

进入 Step 004：Phase 1-C 用户管理与 RBAC 权限边界。

建议 Step 004 聚焦：

- Admin-only RBAC dependency。
- `GET /api/v1/users`。
- `POST /api/v1/users`。
- `PATCH /api/v1/users/{user_id}`。
- `POST /api/v1/users/{user_id}/disable`。
- `POST /api/v1/users/{user_id}/enable`。
- `POST /api/v1/users/{user_id}/reset-password`。
- 验证普通 User 访问 Admin API 返回 `403 FORBIDDEN`。

`POST /api/v1/auth/logout` 的 refresh token revoke 建议作为独立步骤，或在 Step 004 前先确认是否新增 refresh token 存储表。
