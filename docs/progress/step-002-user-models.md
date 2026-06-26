# Step 002：Phase 1-A 用户数据模型与迁移

## 1. 本步骤目标

实现 SDD v0.1 Phase 1 的用户数据基础：`users` 表、`user_profiles` 表、用户角色/状态枚举、Alembic migration 和基础模型测试。

本步骤只处理数据模型与迁移，不实现登录、JWT、默认 Admin 初始化、RBAC 或用户管理 API。

## 2. 对应 SDD 条目

- `4.2 users`：定义用户表字段、唯一约束、角色/状态约束、登录失败计数、锁定时间、软删除字段。
- `4.3 user_profiles`：定义用户画像表字段、`user_id` 唯一外键、偏好 JSONB。
- `7 开发里程碑 / Phase 1：认证、用户与权限`：本步骤覆盖其中的 `users 表`、`user_profiles 表` 和登录失败计数字段基础。
- `8.1 Python 代码规范`：所有数据库变更必须通过 Alembic migration。

## 3. 本步骤完成内容

- 新增 `app.models` 包。
- 新增 `UserRole` 枚举，值为 `admin`、`user`。
- 新增 `UserStatus` 枚举，值为 `active`、`disabled`。
- 新增 `User` SQLAlchemy 模型，对应 SDD 的 `users` 表。
- 新增 `UserProfile` SQLAlchemy 模型，对应 SDD 的 `user_profiles` 表。
- 在 Alembic `env.py` 中导入模型包，确保后续 autogenerate 能读取模型 metadata。
- 新增 `0002_users_profiles` migration，创建 `users` 与 `user_profiles` 表。
- 新增模型元数据测试，覆盖字段、唯一约束、检查约束、外键约束和枚举值。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/__init__.py` | 新增 | 导出用户模型和用户枚举 |
| `backend/app/models/user.py` | 新增 | 定义 `UserRole`、`UserStatus`、`User`、`UserProfile` |
| `backend/migrations/env.py` | 修改 | 导入 `app.models`，让 Alembic metadata 包含业务模型 |
| `backend/migrations/versions/0002_create_users_and_profiles.py` | 新增 | 创建 `users` 和 `user_profiles` 表 |
| `backend/tests/test_user_models.py` | 新增 | 验证用户模型字段、枚举和约束 |
| `docs/progress/README.md` | 修改 | 追加 Step 002 状态和下一步建议 |
| `docs/progress/step-002-user-models.md` | 新增 | 本步骤进度记录 |

## 5. 关键实现说明

- `users.id` 与 `user_profiles.id` 使用 PostgreSQL UUID 类型，符合 SDD “主键统一使用 UUID”要求。
- `users.email` 与 `users.username` 均设置唯一约束且不可为空。
- `users.role` 使用检查约束限制为 `admin` 或 `user`。
- `users.status` 使用检查约束限制为 `active` 或 `disabled`。
- `users.failed_login_count` 默认为 `0`，为后续“失败 5 次锁定 15 分钟”逻辑预留数据字段。
- `users.deleted_at` 保留为软删除字段，默认查询过滤逻辑将在后续 repository/service 层实现。
- `user_profiles.user_id` 是指向 `users.id` 的唯一外键，保证一个用户最多一个画像。
- `user_profiles.preferences` 使用 PostgreSQL `JSONB`，用于保存用户偏好；用户画像只作为回答风格输入，不影响事实和引用策略。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Ruff lint | `. .venv/bin/activate && ruff check app tests migrations` | 通过 | 所有检查通过 |
| Black 格式检查 | `. .venv/bin/activate && black --check app tests migrations` | 通过 | 20 个文件无需重新格式化 |
| MyPy 类型检查 | `. .venv/bin/activate && mypy app tests` | 通过 | 17 个源文件无类型问题 |
| 本地单元测试 | `. .venv/bin/activate && pytest` | 通过 | 4 passed，1 warning；warning 为 Starlette TestClient deprecation |
| 宿主机默认 Alembic 检查 | `. .venv/bin/activate && alembic current` | 失败/不阻塞 | 默认 `.env` 中 `DATABASE_URL` 使用容器网络主机名 `postgres`，宿主机无法解析；已改用容器内 Alembic 完成迁移验证 |
| Alembic migration 执行 | `docker compose run --rm --no-deps backend-api alembic upgrade head` | 通过 | 成功执行 `0001_phase_0 -> 0002_users_profiles` |
| Alembic 版本落库检查 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c "select version_num from alembic_version;"` | 通过 | 返回 `0002_users_profiles` |
| 表存在性检查 | 查询 `information_schema.tables` | 通过 | 存在 `alembic_version`、`users`、`user_profiles` |
| 字段落库检查 | 查询 `information_schema.columns` | 通过 | `users` 12 个字段、`user_profiles` 8 个字段均已落库 |
| 约束落库检查 | 查询 `pg_constraint` | 通过 | 主键、唯一约束、检查约束、外键约束均已落库 |
| 容器内后端测试 | `docker compose run --rm --no-deps backend-api pytest` | 通过 | 容器内 Python 3.11.15，4 passed，1 warning |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 新增模型和 migration 已进入构建上下文，镜像构建成功 |

## 7. 当前未完成事项

- 未实现 bcrypt 密码哈希。
- 未实现默认 Admin 初始化。
- 未实现 JWT access token 和 refresh token。
- 未实现登录、refresh、logout 或 auth/me API。
- 未实现 Admin 创建用户、禁用/启用用户、重置密码。
- 未实现 RBAC dependency 和权限边界。
- 未实现默认查询过滤 `deleted_at IS NULL` 的 repository/service 层逻辑。

## 8. 风险与注意事项

- 系统默认 `python` 和 `python3` 仍为 Python 3.6.8；后续本地验证应继续使用 `backend/.venv` 或明确调用 `python3.11`。
- 宿主机直接运行 Alembic 时，如果使用默认 `.env` 的 `postgres` 主机名会解析失败；建议在宿主机运行时覆盖 `DATABASE_URL=postgresql+psycopg://kb_agent:change-me@localhost:5432/kb_agent`，或使用容器内 Alembic。
- 本步骤只建立数据结构，不能作为认证功能已完成的依据。
- `users.deleted_at` 的默认过滤尚未实现，后续实现查询层时必须遵守 SDD 的软删除默认过滤要求。

## 9. 下一步建议

进入 Step 003：Phase 1-B 认证基础能力。

建议 Step 003 聚焦：

- bcrypt 密码哈希工具。
- 默认 Admin 初始化。
- JWT access token 与 refresh token。
- `POST /api/v1/auth/login`。
- `POST /api/v1/auth/refresh`。
- `GET /api/v1/auth/me` 基础能力。

Admin 用户管理、禁用/启用、重置密码和 RBAC dependency 建议放在 Step 004 单独完成。
