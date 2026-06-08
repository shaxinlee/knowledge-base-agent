# Step 048：文件解析/索引后台推进器

## 1. 本步骤目标

本步骤目标是修复文件解析/索引阶段依赖 `GET /files/{file_id}/status` 轮询推进的问题。

此前 Step 045 为了解决上传后长期停留 `queued`，临时让状态接口在查询时推进 `queued -> parsing -> normalizing -> chunking -> embedding -> indexed`。这会导致任务进度依赖前端页面刷新或状态轮询：如果用户不打开页面，后台任务不会继续前进。

本步骤将任务推进职责迁回后端内部：

- 上传文件后创建 `queued` parse_job，并由后端后台任务立即唤醒推进。
- 重新解析后创建 `queued` parse_job，并由后端后台任务立即唤醒推进。
- 应用启动后运行轻量 in-process worker，按间隔扫描待处理 parse_job。
- 状态接口恢复为只读查询，不再提交 MinerU、不再拉取 MinerU 结果、不再执行标准化/切片/索引。

当前实现是轻量 in-process worker，为后续替换为独立 worker / queue 预留了清晰边界。

## 2. 本步骤完成内容

- 新增 `parse_pipeline` 后台推进服务：
  - `advance_parse_job_once()`
  - `run_parse_job_until_waiting()`
  - `process_pending_parse_jobs_once()`
  - `ParseJobWorker`
- 后台推进覆盖状态：
  - `queued`
  - `parsing`
  - `normalizing`
  - `chunking`
  - `embedding`
- 终态自动停止：
  - `indexed`
  - `partially_indexed`
  - `failed`
  - `cancelled`
- 上传接口接入后台任务唤醒：
  - 响应仍返回已创建的 file/parse_job。
  - 响应完成后由后台任务推进最新 parse_job。
- 重新解析接口接入后台任务唤醒：
  - 请求返回 `202 queued`，表示任务已接受。
  - MinerU 提交失败不再让 retry 请求返回 5xx，而是由后台推进器写入 parse_job/file failed 状态。
- 应用生命周期接入 worker：
  - `PARSE_WORKER_ENABLED`
  - `PARSE_WORKER_POLL_INTERVAL_SECONDS`
  - `PARSE_WORKER_BATCH_SIZE`
- `GET /api/v1/files/{file_id}/status` 改回只读：
  - 只读取 file/latest parse_job 当前状态。
  - 不再注入 MinIO、MinerU、embedding、Qdrant、BM25 client。

## 3. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/parse_pipeline.py` | 新增 | 后台解析/索引推进器和 in-process worker |
| `backend/app/api/v1/files.py` | 修改 | 上传/重试后安排后台推进；状态接口改为只读 |
| `backend/app/services/files.py` | 修改 | 移除状态接口推进函数；重试解析改为创建 queued 任务 |
| `backend/app/main.py` | 修改 | 应用生命周期启动/停止 parse job worker |
| `backend/app/core/config.py` | 修改 | 新增 parse worker 开关、轮询间隔和批量大小 |
| `backend/app/db/session.py` | 修改 | 暴露 session factory，供后台任务使用并支持测试覆盖 |
| `backend/tests/test_files_api.py` | 修改 | 测试改为验证后台推进和状态接口只读语义 |
| `docs/progress/step-048-backend-parse-job-worker.md` | 新增 | 记录本步骤目标、实现和验证 |
| `docs/progress/README.md` | 修改 | 同步 Step 048 状态 |

## 4. 验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| Files API 目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_files_api.py -q` | 通过：13 passed |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过：80 passed |
| Ruff 检查 | `backend/.venv/bin/python -m ruff check backend/app/api/v1/files.py backend/app/services/files.py backend/app/services/parse_pipeline.py backend/app/main.py backend/app/db/session.py backend/app/core/config.py backend/tests/test_files_api.py` | 通过 |
| Black 检查 | `backend/.venv/bin/python -m black --check backend/app/api/v1/files.py backend/app/services/files.py backend/app/services/parse_pipeline.py backend/app/main.py backend/app/db/session.py backend/app/core/config.py backend/tests/test_files_api.py` | 通过 |
| Mypy 检查 | `backend/.venv/bin/python -m mypy backend/app/api/v1/files.py backend/app/services/files.py backend/app/services/parse_pipeline.py backend/app/main.py backend/app/db/session.py backend/app/core/config.py` | 通过 |

## 5. 当前边界

- 当前 worker 是 backend-api 进程内轻量 worker，不是独立队列系统。
- 多实例部署时需要进一步引入数据库锁、队列或外部 worker，避免多个 backend 实例重复推进同一任务。
- 当前实现已经把推进职责从状态查询接口中移出，后续替换为 Redis Queue / Celery / RQ / Dramatiq 等独立 worker 时，可以优先复用 `parse_pipeline` 中的阶段推进函数。
