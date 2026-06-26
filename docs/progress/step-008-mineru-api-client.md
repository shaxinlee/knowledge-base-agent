# Step 008：parse_jobs 与 MinerU API client

## 1. 本步骤目标

完成 Phase 3-A 的 MinerU API 调用基础：新增 MinerU API client，按用户要求参考 `https://mineru.net/apiManage/docs`，采用 API 调用方式实现文件解析提交、任务结果轮询、解析产物保存到 MinIO `parsed-results`，并将状态写回 `parse_jobs`。

本步骤不实现 document_blocks、chunks_metadata、chunking、embedding、Qdrant indexing 或 RAG 问答。

## 2. 对应 SDD 条目

- `2.1.4 解析任务状态流转`：上传成功后创建 parse_job，由异步执行进入 parsing/normalizing/chunking 等状态。
- `4.6 parse_jobs`：parse_jobs 字段、状态、失败保留日志、retry 创建新 parse_job。
- `6.7 Files API`：`POST /api/v1/files/{file_id}/retry-parse`、`GET /api/v1/files/{file_id}/status`。
- `Phase 3：文档解析与 Chunking`：本步骤覆盖 parse_job 状态机与 MinerU API 调用的最小闭环，不覆盖 blocks/chunks。
- 用户明确要求：后端 MinerU 解析部分采用 API 调用方式，并参考 `https://mineru.net/apiManage/docs`。

## 3. 本步骤完成内容

- 新增 MinerU API 配置项：
  - `MINERU_API_BASE_URL`
  - `MINERU_API_TOKEN`
  - `MINERU_MODEL_VERSION`
  - `MINERU_LANGUAGE`
  - `MINERU_ENABLE_FORMULA`
  - `MINERU_ENABLE_TABLE`
  - `MINERU_IS_OCR`
  - `MINERU_REQUEST_TIMEOUT_SECONDS`
- 将 `httpx` 调整为后端运行时依赖，因为 MinerU API client 在运行时需要发 HTTP 请求。
- 新增 MinerU API client：
  - `POST /api/v4/file-urls/batch` 申请上传 URL。
  - `PUT` 文件内容到 MinerU 返回的 signed upload URL。
  - `GET /api/v4/extract-results/batch/{batch_id}` 轮询批量解析结果。
  - 下载 `full_zip_url` 对应的解析产物。
- 新增 ObjectStorage `get_object` 能力，用于从 MinIO `raw-files` 读取原始文件。
- 实现 `POST /api/v1/files/{file_id}/retry-parse`：
  - Admin only。
  - 读取 `raw-files` 原始文件。
  - 创建新的 parse_job。
  - 提交 MinerU API。
  - 将 `batch_id`、`data_id`、提交响应写入 `parse_jobs.logs`。
  - 将 parse_job 置为 `parsing`，progress 置为 10。
  - 将 file 置为 `processing`。
- 增强 `GET /api/v1/files/{file_id}/status`：
  - 当 latest parse_job 为 `parsing` 且包含 MinerU batch_id 时，轮询 MinerU API 一次。
  - MinerU 成功时下载 `full_zip_url`，保存到 MinIO `parsed-results`。
  - 将解析产物 bucket/key/source_url 写入 `parse_jobs.logs.parsed_result`。
  - 将 parse_job 推进到 `normalizing`，progress 置为 40。
  - MinerU 失败时将 parse_job 和 file 置为 `failed`，记录 `MINERU_PARSE_FAILED`。
- 未新增数据库字段：
  - MinerU 的 `batch_id`、`data_id`、latest result、parsed result location 均写入现有 `parse_jobs.logs` JSON 字段。
  - 这是基于 SDD 未定义 MinerU 专属字段的最小合理假设。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 将 `httpx` 调整为运行时依赖 |
| `backend/app/core/config.py` | 修改 | 新增 MinerU API 配置和 `parsed_results_bucket` |
| `backend/app/services/object_storage.py` | 修改 | 新增 `get_object`，支持从 MinIO 读取 raw file |
| `backend/app/services/mineru.py` | 新增 | 新增 MinerU API client 与响应解析逻辑 |
| `backend/app/services/files.py` | 修改 | 新增 retry-parse、MinerU 提交、状态轮询、parsed-results 保存 |
| `backend/app/api/v1/files.py` | 修改 | 接入 `POST /files/{file_id}/retry-parse` 与 status 轮询依赖 |
| `backend/tests/test_files_api.py` | 修改 | 新增 fake MinerU client 测试提交、轮询成功、轮询失败 |
| `.env.example` | 修改 | 将 MinerU 配置改为 API 调用相关环境变量 |
| `docs/progress/step-008-mineru-api-client.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步 |
| `docs/progress/README.md` | 修改 | 同步总进度索引与下一步建议 |

## 5. 关键实现说明

- MinerU API 调用路径采用文档中的批量本地文件上传解析方式：
  - 先申请 upload URL。
  - 再把原始文件 PUT 到 MinerU signed URL。
  - 再通过 batch result endpoint 轮询。
- 当前系统的 MinIO 在内网容器网络中，不要求公网可访问。因此本步骤没有采用“把 MinIO URL 直接交给 MinerU”的方案。
- `parse_jobs.logs` 示例结构：

```json
{
  "provider": "mineru",
  "mode": "api_v4_file_urls_batch",
  "mineru": {
    "batch_id": "xxx",
    "data_id": "parse_job_uuid",
    "submit_response": {}
  },
  "mineru_latest_state": "done",
  "parsed_result": {
    "bucket": "parsed-results",
    "key": "knowledge-bases/.../mineru-full.zip",
    "source_url": "https://..."
  }
}
```

- MinerU 成功后 parse_job 暂推进到 `normalizing`，表示 MinerU 解析产物已经保存，下一阶段应进行标准化写入 document_blocks。
- 本步骤没有把 parse_job 标为 `indexed`，因为 blocks/chunks/embedding/indexing 尚未实现。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Python 版本检查 | `python3.11 --version` | 通过 | 当前为 Python 3.11.13 |
| Docker daemon 检查 | `docker info --format '{{.ServerVersion}}'` | 通过 | Docker Server 26.1.3 正常响应 |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 后端 Ruff 检查 | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端 Black 检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 55 files would be left unchanged |
| 后端 Mypy 检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | no issues found in 49 source files |
| 后端单元/接口测试 | `backend/.venv/bin/pytest` | 通过 | 29 passed，40 warnings；warnings 为 TestClient/httpx 与短测试 JWT secret 警告 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 镜像构建完成 |
| 容器内测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 29 passed，1 warning |
| 后端启动检查 | `docker compose up -d --no-deps --force-recreate backend-api` + `GET /api/v1/health` | 通过 | 健康接口返回 `ok` |
| MinerU fake submit 测试 | `test_retry_parse_submits_file_to_mineru_and_status_poll_saves_result` | 通过 | 验证 raw file 提交、batch_id 写入、轮询成功、parsed-results 保存 |
| MinerU fake failed 测试 | `test_retry_parse_marks_parse_job_failed_when_mineru_result_fails` | 通过 | 验证 MinerU failed 状态写回 file/parse_job |
| MinerU token 缺失 smoke | 实际上传文件后调用 `POST /files/{file_id}/retry-parse` | 通过 | 返回 `503 UPSTREAM_SERVICE_ERROR`，message 为 `MinerU API token is not configured.`；DB 中 file/parse_job 均标记 failed，error_code 为 `MINERU_SUBMIT_FAILED` |
| 真实 MinerU 在线 API 调用 | 需要 `MINERU_API_TOKEN` | 未执行 | 当前环境未配置 MinerU API token，不能发起真实解析请求 |

## 7. 当前未完成事项

- 未配置真实 MinerU API token，因此未完成真实 MinerU 在线解析验证。
- 未实现异步 worker，当前 `retry-parse` 为同步提交，`GET status` 为单次轮询。
- 未实现 document_blocks。
- 未实现 chunks_metadata。
- 未实现 chunking、embedding、Qdrant indexing。
- 未实现 retry 后的旧 parse_job 清理策略；当前保留所有 parse_job，latest_parse_job_id 指向新任务。

## 8. 风险与注意事项

- MinerU API 文档中的字段可能随平台调整而变化；当前实现使用最小字段：`files[].name`、`files[].is_ocr`、`files[].data_id`，并保留提交原始响应到 `parse_jobs.logs` 便于排查。
- 当前没有真实 token，因此只能证明本地逻辑、请求组装、状态映射、结果保存逻辑在 fake client 下正确，不能证明线上 MinerU 服务已接受请求。
- 当前状态轮询在 `GET /files/{file_id}/status` 中同步执行一次。后续生产化应改为 worker 定时轮询或任务队列。
- MinerU 完成后 parse_job 进入 `normalizing` 而不是 `indexed`，因为本步骤只完成解析产物保存，未生成 blocks/chunks/index。

## 9. 下一步建议

进入 Step 009：document_blocks 与 MinerU 解析产物标准化。

建议 Step 009 聚焦：

- 定义 `document_blocks` 表与 migration。
- 从 MinIO `parsed-results` 中读取 MinerU zip。
- 提取 Markdown/JSON 解析结果。
- 写入 document_blocks。
- 将 parse_job 从 `normalizing` 推进到 `chunking`。
- 仍暂不做 embedding/Qdrant indexing，除非标准化闭环非常小且可清晰验证。
