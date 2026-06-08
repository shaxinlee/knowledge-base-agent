# Step 038：真实 MinerU API 文件解析验证

## 1. 本步骤目标

本步骤目标是在不继续扩展 Demo fixture 的前提下，推进真实后端文件处理链路的第一段：完善 MinerU API 解析任务的提交、轮询、失败隔离、解析产物保存和前端状态可观测性。

本步骤以当前已存在的 MinerU API client 为基础，不实现 Step 039 的真实解析产物标准化增强，不实现 Step 040 的 API 化 embedding / reranker / LLM，也不做 Step 041 的真实端到端问答。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：上传资料后应完成文档解析、文本标准化、Chunking、Embedding、检索、Reranker、LLM、引用溯源、会话与反馈保存。
- SDD v0.1 1.4：Admin 上传多格式文件；文件格式、大小、同名、Hash 校验；原始文件保存到 MinIO；解析结果持久化；文档标准化为 blocks；Docker Compose 一键启动完整系统。
- SDD v0.1 2.1.3：MinIO 建议 bucket 包含 `raw-files`、`parsed-results`、`normalized-docs`、`assets`、`exports`。
- SDD v0.1 2.1.4：`parse_jobs.status` 包含 `queued/parsing/normalizing/chunking/embedding/indexing/indexed/partially_indexed/failed/cancelled`；失败任务必须保留 error log；Admin 可触发重新解析；每次重新解析创建新的 parse_job；失败 job 不能污染线上检索。
- SDD v0.1 2.1.5：`file uploaded -> create parse_job -> call mineru-service -> save MinerU markdown/json/assets -> normalize document blocks -> chunking ...`。
- 用户确认的实现方向：MinerU 使用 API 调用方式；后续 embedding / reranker / LLM 也按 API 接入方向规划。这一点偏离 SDD 原文中本地服务的表述，已在本步骤记录为用户确认后的实现方向。

## 3. 本步骤完成内容

- 确认 MinerU API 路径继续采用 API 方式，参考 MinerU 文档中的批量本地文件上传解析流程：
  - `POST /api/v4/file-urls/batch`
  - signed `PUT` 上传文件
  - `GET /api/v4/extract-results/batch/{batch_id}`
  - 下载 `full_zip_url`
- 在 `.env` 中补齐 MinerU API 配置项，移除旧的本地 `MINERU_SERVICE_URL` 默认配置，避免当前运行环境继续暗示本地 MinerU 服务。
- 将当前 Codex 内置浏览器端口 `50639` 加入 CORS 允许来源，配合 Step 037 的同源 `/api/v1` 代理，减少登录和文件状态页的 `Failed to fetch` 风险。
- 扩展文件状态响应中的 `latest_parse_job` 信息：
  - 返回 `error_code`
  - 返回 `logs`
  - 前端文件页展示 MinerU 最新状态和 parsed-results 保存提示。
- 完善 MinerU 轮询失败隔离：
  - `done/completed/success` 但缺少 `full_zip_url` 时，将 parse_job 标记为 `failed`，写入 `MINERU_RESULT_MISSING`，不进入后续 blocks/chunks/indexing。
  - MinerU 返回 `failed/error` 时，将 parse_job 标记为 `failed`，写入 `MINERU_PARSE_FAILED` 和 `logs.mineru_error`。
  - MinerU 提交阶段失败时，将 parse_job 标记为 `failed`，写入 `MINERU_SUBMIT_FAILED`，并保留 `ApiError.message` 到 `error_message` 与 `logs.mineru_submit_error`。
- 成功下载 MinerU zip 后，将产物保存到 MinIO `parsed-results`，并在 logs 中记录 bucket/key/source_url/content_type。
- 后端 Dockerfile 默认 PyPI 源切换为阿里云镜像，保证后续构建符合用户关于 pip 包下载源的要求。
- API contract、OpenAPI 和前端类型已同步 `ParseJob` 新增字段。
- 本步骤没有新增无关业务功能，没有改变文件上传接口路径，没有新增数据库表或 migration。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `.env` | 修改 | 补齐 MinerU API 配置项，加入当前内置浏览器 `50639` CORS 来源，移除旧本地 MinerU service 默认地址 |
| `.env.example` | 修改 | 同步当前内置浏览器 `50639` CORS 示例 |
| `backend/Dockerfile` | 修改 | 默认 `PIP_INDEX_URL` 改为阿里云 PyPI 镜像，提升容器构建稳定性 |
| `backend/app/schemas/files.py` | 修改 | `ParseJobResponse` 增加 `error_code` 和 `logs` |
| `backend/app/services/files.py` | 修改 | 完善 MinerU poll 成功/失败/缺 zip 处理、parsed-results logs、提交阶段错误信息保留和 parse_job response 构造 |
| `backend/tests/test_files_api.py` | 修改 | 扩展 fake MinerU client，新增 pending、缺 `full_zip_url`、提交失败错误信息保留等测试 |
| `frontend/src/api/types.ts` | 修改 | 前端 `ParseJob` 类型同步 `error_code`、`logs`，`latest_parse_job` 支持 null |
| `frontend/src/views/FilesView.vue` | 修改 | 文件列表展示解析错误码、MinerU 最新状态和 parsed-results 保存提示 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 同步文件状态、retry-parse、logs/error_code 和 MinerU token 缺失说明 |
| `docs/api/openapi.v0.1.yaml` | 修改 | 同步 `ParseJob` schema 和 `FileStatusResponse.latest_parse_job` nullable |
| `docs/progress/step-038-real-mineru-api-parse-validation.md` | 新增 | 记录本步骤目标、实现、验证、未完成事项和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 038 状态、已完成内容、风险和下一步建议 |

## 5. 关键实现说明

- `retry_parse_file()`：
  - 每次重新解析创建新的 parse_job，并将 `file.latest_parse_job_id` 指向新任务。
  - 提交 MinerU 失败时，不吞掉错误；接口继续返回原始上游错误，同时 DB 中 parse_job/file 进入 failed，便于页面刷新时看到真实失败原因。
  - 对 `ApiError` 单独提取 `message`，避免状态接口中的 `error_message` 为空。
- `poll_mineru_parse_job()`：
  - 读取 parse_job logs 中保存的 `batch_id` 和 `data_id`。
  - 查询 MinerU batch result 后保存 `mineru_latest_result` 和 `mineru_latest_state`。
  - 成功状态只允许在存在 `full_zip_url` 时下载 zip 并保存到 `parsed-results`。
  - 缺少 `full_zip_url` 或 MinerU 返回失败状态时调用 `mark_mineru_parse_job_failed()`，保证失败 job 不进入后续 blocks/chunks/indexing。
- `mark_mineru_parse_job_failed()`：
  - 统一设置 parse_job/file failed、error_code、error_message、finished_at 和 `logs.mineru_error`。
- 前端文件状态页：
  - 将错误展示从单纯 message 升级为 `error_code: error_message`。
  - 增加 `解析详情` 列，展示 MinerU 最新状态或 parsed-results 已保存提示。
- Dockerfile：
  - 构建时默认使用 `https://mirrors.aliyun.com/pypi/simple/`，避免 Docker 镜像内 pip 直连默认源长期卡住。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| SDD/README/项目结构核对 | 阅读 `docs/specs/SDD.v0.1.md`、`README.md`、依赖和现有代码 | 通过 | 确认本步骤只处理真实 MinerU API 解析链路可观测性与失败隔离 |
| MinerU API 文档确认 | 查阅 `https://mineru.net/apiManage/docs` | 通过 | 当前 client 继续采用批量上传、signed PUT、batch result、`full_zip_url` 下载路径 |
| Python 项目环境 | `backend/.venv/bin/python --version` | 通过 | 本地项目虚拟环境为 Python 3.11.13；容器内为 Python 3.11.15 |
| 系统默认 Python 检查 | `python3 --version` | 未满足/不阻塞 | 宿主机默认 `python3` 为 3.6.8；项目验证明确使用 `backend/.venv` 和容器 Python 3.11 |
| Docker daemon 检查 | `docker info --format '{{.ServerVersion}}'` | 通过 | Docker daemon 可用，版本 26.1.3 |
| 后端依赖重装 | `backend/.venv/bin/python -m pip install -e './backend[dev]' -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com` | 通过 | 使用阿里云 PyPI 镜像重装/同步项目依赖 |
| 前端依赖检查 | `npm install` | 通过 | 依赖 up to date，无漏洞 |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 后端目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_files_api.py -q` | 通过 | 12 passed，覆盖 MinerU 成功、pending、失败、缺 zip、提交错误记录 |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 84 files unchanged |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 74 source files 无类型错误 |
| 后端完整测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 45 passed，存在既有 Starlette/JWT secret warning |
| 前端 lint | `npm run lint` | 通过 | ESLint 通过 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞 |
| OpenAPI YAML 解析 | `backend/.venv/bin/python -c "import pathlib, yaml; yaml.safe_load(...)"` | 通过 | 输出 `openapi-ok` |
| 后端容器构建 | `docker compose up -d --build backend-api frontend` | 通过 | 后端镜像使用阿里云 PyPI 镜像构建，frontend/backend 均启动 |
| Migration | `docker compose exec -T backend-api alembic upgrade head` | 通过 | Alembic 成功检查到 head，无新增 migration |
| Docker Compose 服务状态 | `docker compose ps` | 通过 | backend-api、frontend、postgres、redis、qdrant、minio 均 Up |
| 前端代理 health | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回后端 health：`status=ok` |
| 当前浏览器端口 CORS | `curl -fsS -i -X OPTIONS http://localhost:8000/api/v1/auth/me -H 'Origin: http://localhost:50639' ...` | 通过 | 返回 `access-control-allow-origin: http://localhost:50639` |
| 运行态 retry-parse token 缺失 smoke | Admin 登录 -> 创建 KB -> 上传 txt -> retry-parse -> status | 通过 | retry 返回 `503 UPSTREAM_SERVICE_ERROR`；状态接口显示 `failed / MINERU_SUBMIT_FAILED / MinerU API token is not configured.` |
| 容器内后端完整测试 | `docker compose exec -T backend-api pytest -q` | 通过 | 45 passed，存在既有 Starlette/JWT secret warning |
| 真实 MinerU PDF 在线解析 | 配置 `MINERU_API_TOKEN` 后上传 `.pdf` 并 retry-parse | 未执行 | 当前 `.env` 中 `MINERU_API_TOKEN=` 为空，不能发起真实 MinerU 在线请求 |
| 真实 MinerU DOCX 在线解析 | 配置 `MINERU_API_TOKEN` 后上传 `.docx` 并 retry-parse | 未执行 | 当前 `.env` 中 `MINERU_API_TOKEN=` 为空，不能发起真实 MinerU 在线请求 |
| 真实 MinerU TXT 在线解析 | 配置 `MINERU_API_TOKEN` 后上传 `.txt` 并 retry-parse | 未执行 | 已验证 txt 上传和 token 缺失失败路径；真实 MinerU 在线解析仍需 token |

## 7. 当前未完成事项

- 当前环境没有配置 `MINERU_API_TOKEN`，因此真实 `.pdf`、`.docx`、`.txt` 在线解析冒烟未执行。
- 当前只保存 MinerU `full_zip_url` 下载的 zip 到 `parsed-results`，尚未在本步骤增强真实 zip 内 markdown/json/assets 的标准化策略；该项属于 Step 039。
- 真实 embedding / reranker / LLM API 接入不在本步骤处理，仍属于 Step 040。
- 完整真实“上传文件到带引用回答”的 E2E 验收不在本步骤处理，仍属于 Step 041。

## 8. 风险与注意事项

- SDD 原文写的是独立 `mineru-service`，用户已确认当前实现方向改为 MinerU API 调用方式；本步骤按用户确认执行，并在进度文件中记录该偏离。
- SDD 原文写的是本地 bge-m3 embedding 服务和本地 BGE reranker；用户已确认后续 embedding/reranker/LLM 也按 API 化规划。Step 040 需要继续记录该偏离，并保留 fake/demo client 只用于测试和演示。
- 当前 `GET /files/{file_id}/status` 仍承担同步推进解析链路的职责；后续接 Celery worker 后应迁移为异步任务。
- 真实 MinerU 返回字段可能随平台调整。当前实现兼容 `state/status` 和 `done/completed/success/failed/error`，但真实样本验证时仍需根据返回结构补齐映射。
- 本地 `.env` 仍未配置 MinerU token；页面点击重新解析会真实返回上游服务错误，但不会再表现为 `Failed to fetch`。
- 宿主机默认 `python3` 不是 3.11；本项目运行和验证应继续显式使用 `backend/.venv/bin/python` 或 Docker Compose 容器内 Python。

## 9. 下一步建议

建议进入 Step 039：真实 MinerU 产物标准化与 chunking 优化。

原因：Step 038 已把 MinerU API 提交、轮询、错误记录、parsed-results 保存和页面状态展示整理为可观察链路。下一步应围绕 MinerU zip 内 markdown/json/assets 的真实结构，增强 `document_blocks` 标准化、source_locator 生成和层级感知 chunking。若能提供 `MINERU_API_TOKEN`，Step 039 开始前建议先补跑 Step 038 的真实 `.pdf/.docx/.txt` 在线冒烟，并把结果追加到本文件。
