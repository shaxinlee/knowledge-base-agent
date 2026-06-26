# Step 033：indexed 文件删除时 chunks/Qdrant 失效闭环

## 1. 本步骤目标

补齐删除已索引文件时的后端失效逻辑：在 file 软删除和审计写入之外，将该文件 active chunks 标记为 inactive，并同步将对应 Qdrant points 的 payload `is_active` 更新为 `false`，确保旧 chunk 不再参与检索。

## 2. 对应 SDD 条目

- SDD v0.1 `5.3 删除策略`：文件删除时 PostgreSQL `files.deleted_at` 软删除、PostgreSQL chunks `is_active=false`、Qdrant payload `is_active=false` 或异步删除 points。
- SDD v0.1 向量索引验收：删除文件后旧 chunk 不再参与检索。
- TDD v0.1 `TDD-FILE-012`：Admin 删除 indexed 文件后，file 软删除，chunks inactive，Qdrant points 失效或清理，写 audit log。

## 3. 本步骤完成内容

- 为 `VectorIndexClientProtocol` 增加 `deactivate_points()` 能力。
- 为 `QdrantVectorIndexClient` 实现同步 payload 失效：将指定 point ids 的 `is_active` 更新为 `false`。
- 删除文件接口注入现有 Qdrant vector index client。
- 删除文件服务在软删除前读取该文件 active chunk ids。
- 删除文件服务调用 Qdrant points payload 失效。
- 删除文件服务将对应 `chunks_metadata.is_active` 批量更新为 `false`。
- 删除文件审计日志增加 `inactive_chunk_count`、`qdrant_points_deactivated` 和 `qdrant_collection`，便于后续排查。
- 新增后端测试，覆盖 indexed 文件删除后的 file/chunks/Qdrant/audit 行为。
- 更新 TDD 和 Demo 文档，记录当前已完成 fake Qdrant 失效验证，真实样本文档端到端仍依赖外部服务。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/vector_index.py` | 修改 | 增加 `deactivate_points()` 协议方法，并实现 Qdrant payload `is_active=false` 更新 |
| `backend/app/services/files.py` | 修改 | 删除文件时先失效 Qdrant points，再批量将 active chunks 标记为 inactive，并扩展审计 details |
| `backend/app/api/v1/files.py` | 修改 | 删除文件接口注入 `VectorIndexClientProtocol` 并传入 service 层 |
| `backend/tests/test_files_api.py` | 修改 | 扩展 fake vector client，并新增 indexed 文件删除失效测试 |
| `docs/tests/TDD.v0.1.md` | 修改 | 更新 `TDD-FILE-012` 当前状态 |
| `docs/demo/first-version-demo.md` | 修改 | 补充 Qdrant 写入/失效当前边界和真实端到端后续验证项 |
| `docs/progress/step-033-indexed-file-delete-invalidation.md` | 新增 | 记录 Step 033 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 033 状态、已完成内容、待完成内容、注意事项和下一步建议 |

## 5. 关键实现说明

- `QdrantVectorIndexClient.deactivate_points()` 调用 Qdrant points payload 更新接口，将指定 point ids 的 payload 设置为 `{"is_active": false}`。
- `delete_file()` 通过 `list_active_chunk_ids()` 查询当前文件仍 active 的 chunk ids。
- 若 Qdrant 失效失败，`deactivate_points()` 会抛出 `UPSTREAM_SERVICE_ERROR`，删除流程不会继续提交 file/chunk 软删除，避免数据库已删除但 Qdrant 仍 active 的明显不一致。
- Qdrant 失效成功后，`delete_file()` 批量更新 `chunks_metadata.is_active=false`，再设置 `files.status=deleted` 和 `files.deleted_at`。
- 审计日志仍使用原有 `delete_file` action，并在 details 中记录本次失效数量和 collection。
- 本步骤不新增 `cleanup_jobs` 表，也不删除 MinIO 对象；这部分属于后续异步清理任务阶段。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 目标后端测试 | `backend/.venv/bin/python -m pytest backend/tests/test_files_api.py -q` | 通过 | `9 passed, 19 warnings`；新增 indexed 文件删除失效用例通过 |
| 后端格式检查 | `backend/.venv/bin/python -m black --check backend/app backend/tests` | 通过 | 初次检查提示 `backend/app/services/files.py` 需格式化；执行 `black backend/app/services/files.py` 后复跑通过 |
| 后端 lint | `backend/.venv/bin/python -m ruff check backend/app backend/tests` | 通过 | `All checks passed!` |
| 后端类型检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | `Success: no issues found in 62 source files` |
| 完整后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | `39 passed, 60 warnings` |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置有效 |
| 后端 migration 状态 | `docker compose exec -T backend-api alembic current` | 通过 | 当前为 `0009_create_feedback (head)`；本步骤无新增 migration |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple backend-api` | 通过 | 默认源构建因依赖下载长期无进展被中断；使用 Dockerfile 既有 `PIP_INDEX_URL` 构建参数复跑成功 |
| 源码关键字扫描 | `rg -n 'deactivate_points|list_active_chunk_ids|inactive_chunk_count|qdrant_points_deactivated|test_delete_indexed_file_deactivates_chunks' backend/app backend/tests` | 通过 | 可定位核心实现和新增测试 |

## 7. 当前未完成事项

- 真实 MinerU token、真实 embedding-service、真实 reranker-service 和真实 LLM Provider 仍未提供，真实上传文件到带引用回答端到端未完成。
- 删除真实 indexed 文件后旧 chunk 不再参与检索的在线验证仍依赖真实样本文档索引链路。
- `cleanup_jobs` 表、异步清理 MinIO/Qdrant 残留对象和后台任务系统尚未实现。
- 删除知识库后的级联清理/失效仍未补齐。

## 8. 风险与注意事项

- 本步骤选择 Qdrant payload 失效，而不是物理删除 points，符合 SDD “`is_active=false` 或异步删除 points”的最小实现。
- 当前失效是同步执行；Qdrant 不可用时删除 indexed 文件会返回上游服务错误，避免旧 points 继续 active。
- 对未索引或没有 active chunks 的文件，`deactivate_points()` 会收到空列表并直接返回，删除流程仍保持原有软删除行为。
- 真实 Qdrant 在线失效尚未通过真实 indexed 文件验证，当前以 fake Qdrant client 覆盖行为闭环。

## 9. 下一步建议

建议进入 Step 034：开发受限 Demo fixture/seed 路线。

原因：当前第一版基础 Web Demo 已经具备登录、管理、文件、审计、Chat SSE、反馈和删除失效等操作闭环，但真实带引用问答仍被 `MINERU_API_TOKEN`、embedding-service、reranker-service 和 LLM Provider 阻塞。若短期无法提供外部服务，下一步应按 Demo 文档的“选项 B”开发明确标记的开发/演示 fixture，使第一版 Demo 能稳定展示“有 indexed chunks -> Chat 返回 citations”的完整界面链路，同时不声称其等同真实生产 RAG。
