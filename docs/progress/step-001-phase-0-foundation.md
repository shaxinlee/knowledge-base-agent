# Step 001：Phase 0 基础补齐与进度体系初始化

## 1. 本步骤目标

补齐 SDD v0.1 Phase 0 中当前仓库缺失的数据库迁移基础，并建立 `docs/progress/` 进度记录体系，使后续 Phase 1 用户、认证和权限开发具备可继续、可检查的上下文。

本步骤不实现任何业务功能，不创建 users、knowledge_bases、files 等业务表。

## 2. 对应 SDD 条目

- `3.2 后端`：后端必须使用 Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy 2.x、Alembic。
- `3.3 数据库与存储`：PostgreSQL 用于关系数据、全文索引、metadata、trace。
- `7 开发里程碑 / Phase 0：工程骨架`：配置基础服务、创建 `/api/v1/health`、Alembic migration 可执行。
- `8.1 Python 代码规范`：数据库变更必须通过 Alembic migration。

## 3. 本步骤完成内容

- 在后端依赖中新增 Alembic、SQLAlchemy、psycopg。
- 在配置对象中新增 `database_url`，读取 `.env.example` 中已有的 `DATABASE_URL`。
- 新增数据库 Declarative Base，并设置统一命名约定，便于后续 Alembic 自动生成稳定约束名。
- 新增 SQLAlchemy engine、SessionLocal 和 `get_db` dependency。
- 新增 Alembic 配置、迁移环境和 migration 模板。
- 新增 Phase 0 最小 migration，用于验证 Alembic 迁移链路。
- 更新后端 Dockerfile 和 Compose 挂载，使容器内可执行 Alembic migration。
- 为后端 Dockerfile 新增可覆盖的 `PIP_INDEX_URL` 构建参数，便于在受限网络中稳定安装 Python 依赖。
- 新增项目开发进度总览文件。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 新增 Alembic、SQLAlchemy、psycopg 依赖，满足 SDD 后端技术栈要求 |
| `backend/Dockerfile` | 修改 | 复制 Alembic 配置和 migrations 到后端容器；新增可覆盖的 `PIP_INDEX_URL` 构建参数 |
| `backend/alembic.ini` | 新增 | Alembic 配置文件，指定 migration 目录和日志配置 |
| `backend/app/core/config.py` | 修改 | 新增 `database_url` 配置项 |
| `backend/app/db/__init__.py` | 新增 | 数据库模块包声明 |
| `backend/app/db/base.py` | 新增 | SQLAlchemy Declarative Base 和命名约定 |
| `backend/app/db/session.py` | 新增 | SQLAlchemy engine、sessionmaker 和 `get_db` dependency |
| `backend/migrations/env.py` | 新增 | Alembic 迁移环境，读取应用配置和 metadata |
| `backend/migrations/script.py.mako` | 新增 | Alembic migration 生成模板 |
| `backend/migrations/versions/0001_phase_0_migration_foundation.py` | 新增 | Phase 0 最小 migration，暂不创建业务表 |
| `docker-compose.yml` | 修改 | 挂载 Alembic 配置和 migrations，便于容器内开发验证 |
| `docs/progress/README.md` | 新增/修改 | 项目开发进度总览，已将 Step 001 更新为已完成 |
| `docs/progress/step-001-phase-0-foundation.md` | 新增/修改 | 本步骤进度记录，补充本次验证结果 |

## 5. 关键实现说明

- `app.db.base.Base` 使用 SQLAlchemy 2.x 的 `DeclarativeBase`。
- `NAMING_CONVENTION` 为索引、唯一约束、检查约束、外键、主键提供稳定命名，避免后续 Alembic autogenerate 出现不稳定 diff。
- `app.db.session.engine` 使用 `settings.database_url` 创建，并启用 `pool_pre_ping=True`。
- `get_db()` 以 generator dependency 形式提供数据库 Session，后续 FastAPI API 可直接复用。
- `migrations/env.py` 从 `app.core.config.get_settings()` 读取 `DATABASE_URL`，确保应用和 migration 使用同一配置来源。
- `0001_phase_0_migration_foundation.py` 是 no-op migration，只用于建立迁移链路；业务表留到后续 Phase 1-A 创建。
- `backend/Dockerfile` 支持通过 `--build-arg PIP_INDEX_URL=...` 指定 PyPI 镜像源；默认仍为 `https://pypi.org/simple`。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Docker Compose 配置检查 | `docker compose config` | 通过 | Compose 配置可解析，新增文件未破坏 compose 配置 |
| Python 版本检查 | `python3.11 --version` | 通过 | 输出 `Python 3.11.13`；系统默认 `python/python3` 仍为 3.6.8，本项目使用明确的 `python3.11` |
| Docker daemon 检查 | `docker version` | 通过 | Docker Client/Server 均为 26.1.3，daemon 已运行 |
| Docker Compose 版本检查 | `docker compose version` | 通过 | 输出 Docker Compose v2.27.0 |
| 后端依赖安装 | `python3.11 -m venv .venv && . .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"` | 通过 | 后端开发依赖安装成功 |
| Alembic 依赖可用性 | `. .venv/bin/activate && python -c "import sqlalchemy, alembic, psycopg"` | 通过 | `alembic 1.18.4`、`psycopg 3.3.4`、`sqlalchemy 2.0.50` |
| 后端本地单元测试 | `. .venv/bin/activate && pytest` | 通过 | 1 passed，1 warning；warning 为 Starlette TestClient deprecation |
| 迁移文件存在性检查 | 使用脚本检查 `alembic.ini`、`migrations/env.py`、migration 文件和 `app/db` 文件是否存在 | 通过 | 所有预期文件均存在 |
| 依赖声明检查 | 检查 `pyproject.toml` 是否包含 `alembic`、`sqlalchemy`、`psycopg` | 通过 | 三项依赖均已声明 |
| Docker 迁移文件打包检查 | 检查 `backend/Dockerfile` 是否复制 `alembic.ini` 和 `migrations` | 通过 | 后端容器构建后应包含迁移配置和迁移脚本 |
| 后端镜像构建初次重试 | `docker compose build backend-api` | 失败 | Docker Hub 直连基础镜像超时；随后通过镜像代理拉取并标记 `python:3.11-slim`、`postgres:16-alpine` |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 后端镜像构建成功，容器内依赖安装完成 |
| PostgreSQL 启动 | `docker compose up -d postgres` | 通过 | PostgreSQL 容器启动并通过 healthcheck |
| Alembic migration 执行 | `docker compose run --rm --no-deps backend-api alembic upgrade head` | 通过 | 成功执行 `Running upgrade -> 0001_phase_0` |
| Alembic 版本落库检查 | `docker compose exec -T postgres psql -U kb_agent -d kb_agent -c 'select version_num from alembic_version;'` | 通过 | 返回 `0001_phase_0` |
| 容器内后端测试 | `docker compose run --rm --no-deps backend-api pytest` | 通过 | 容器内 Python 3.11.15，1 passed，1 warning |
| 容器内 health 检查 | `docker compose run --rm --no-deps backend-api python - <<'PY' ... TestClient(app).get('/api/v1/health') ... PY` | 通过 | 返回 HTTP 200 和 `{'status': 'ok', 'service': 'backend-api', 'version': '0.1.0'}` |

## 7. 当前未完成事项

- 未创建 Phase 1 的 `users` 与 `user_profiles` 表。
- 未实现默认 Admin、密码哈希、JWT、登录、RBAC 或用户管理。

## 8. 风险与注意事项

- Step 001 运行环境问题已解决：`python3.11` 可用，Docker daemon 已运行，后端镜像构建、migration 和测试已通过。
- 系统默认 `python` 和 `python3` 仍为 Python 3.6.8；后续本地后端验证应继续使用 `backend/.venv` 或明确调用 `python3.11`。
- Docker Hub 直连曾出现超时；本次通过镜像代理拉取基础镜像，并使用 `PIP_INDEX_URL` 构建参数完成后端镜像构建。后续如网络受限，可复用同一构建参数。
- SDD 与 API contract 对 `KnowledgeBaseStatus` 存在差异：SDD 写的是 `active/deleting/deleted`，API contract 写的是 `active/archived/deleted`。该冲突不影响 Step 001，但进入 Phase 2 前必须处理。
- SDD 要求数据库主键统一 UUID，而 API contract 建议前端 ID 使用 `usr_`、`kb_` 等前缀。进入 Phase 1-A 前应确定 API 层 ID 表现策略。

## 9. 下一步建议

进入 Step 002：Phase 1-A 用户数据模型与迁移，目标是实现 `users`、`user_profiles`、用户角色/状态枚举、Alembic migration 和对应测试。

Step 002 不建议同时实现登录、JWT 或 RBAC，以保持步骤边界清晰；这些应在后续独立步骤中完成。
