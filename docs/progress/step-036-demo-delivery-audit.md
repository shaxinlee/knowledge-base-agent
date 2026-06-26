# Step 036：第一版 Demo 交付审计与收口

## 1. 本步骤目标

对当前第一版 Demo 做交付审计，确认 SDD v0.1 要求在 Demo 边界内的实现状态、验收证据、外部依赖缺口和 MinerU API 调用方式，并形成可供后续 Agent 或验收人员接手的收口文档。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：文档解析、标准化、Chunking、Embedding、检索、重排、回答、引用、会话与反馈保存的核心目标。
- SDD v0.1 1.4：Admin 登录与用户管理、知识库 CRUD、文件上传校验、MinIO、MinerU 解析、blocks/chunks、Qdrant、全文检索、混合召回、Reranker、SSE、引用、拒答、trace、feedback、审计、Docker Compose。
- SDD v0.1 2.1.5：上传后解析、标准化、chunking、embedding、indexing 状态链路。
- SDD v0.1 2.1.6：引用 `source_locator` 需要支持溯源。
- 用户补充要求：MinerU 后端逻辑采用 API 调用方式，并参考 `https://mineru.net/apiManage/docs`。

## 3. 本步骤完成内容

- 新增第一版 Demo 交付验收报告，明确当前可以验收为“第一版基础 Web Demo 已完成”，不能验收为“完整 SDD v0.1 MVP 已完成”。
- 按 SDD v0.1 核心能力整理 Demo 对照矩阵，区分“Demo 通过”“部分通过”“真实链路待验收”。
- 明确记录 MinerU 当前实现采用 API 调用方式：
  - `POST /api/v4/file-urls/batch`
  - signed `PUT` 上传
  - `GET /api/v4/extract-results/batch/{batch_id}`
  - 下载 `full_zip_url`
- 更新 Demo 文档和 README，增加交付验收报告入口。
- 更新 TDD 当前实现状态，记录 Step 036 交付审计结论。
- 更新总进度索引，将 Step 036 标记为已完成，并将下一步建议转向真实外部服务接入与端到端验收。
- 复跑后端类型检查时发现既有类型标注问题，已做最小类型修正：
  - SSE helper 补充生成器和 payload 类型标注。
  - API endpoint module 显式导出测试覆盖使用的 dependency provider。
  - 测试替身补齐 `VectorIndexClientProtocol.deactivate_points()`。
  - 测试中对 JSON details 与可空查询结果补充类型收窄。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `docs/demo/first-version-demo-acceptance-report.md` | 新增 | 第一版 Demo 交付验收报告，记录 SDD 对照矩阵、MinerU API 调用方式、可演示路径、交付边界和后续建议 |
| `docs/demo/first-version-demo.md` | 修改 | 增加交付验收报告入口，并同步第一版 Demo 收口结论 |
| `docs/tests/TDD.v0.1.md` | 修改 | 同步 Step 036 当前实现与测试状态 |
| `README.md` | 修改 | 增加第一版 Demo 交付验收报告入口，并更新当前 Demo 说明 |
| `backend/app/api/v1/conversations.py` | 修改 | 补充 SSE helper 类型标注，并显式导出 dependency provider，修复后端 mypy 问题 |
| `backend/app/api/v1/retrieval.py` | 修改 | 显式导出 dependency provider，修复测试覆盖导入的 mypy 问题 |
| `backend/app/api/v1/files.py` | 修改 | 显式导出 dependency provider，修复测试覆盖导入的 mypy 问题 |
| `backend/tests/test_retrieval_api.py` | 修改 | FakeVectorIndexClient 补齐 `deactivate_points()` 协议方法 |
| `backend/tests/test_conversations_api.py` | 修改 | FakeVectorIndexClient 补齐 `deactivate_points()` 协议方法 |
| `backend/tests/test_demo_fixture.py` | 修改 | 在使用 file id 前补充非空断言，完成类型收窄 |
| `backend/tests/test_users_api.py` | 修改 | 对 audit log details 补充 `cast`，避免可空 JSON 字段直接索引 |
| `backend/tests/test_files_api.py` | 修改 | 对 delete file 审计 details 补充 `cast`，避免可空 JSON 字段直接索引 |
| `docs/progress/step-036-demo-delivery-audit.md` | 新增 | 记录 Step 036 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 036 状态、已完成内容、风险注意事项和下一步建议 |

## 5. 关键实现说明

- 本步骤没有新增业务功能，也没有改变后端或前端运行逻辑。
- 本步骤的核心产物是交付审计文档：用于避免把 Demo fixture、fake/local demo 模型或模板回答误认为完整 SDD MVP 验收。
- MinerU 相关说明基于当前代码和 MinerU API 文档核对：项目后端调用 MinerU API，而不是依赖本地 MinerU 服务。
- 当前 Demo fixture 仅用于第一版 Demo 的 citation UI 演示，不替代真实 MinerU、embedding、reranker 或 LLM 验收。
- 代码侧只做类型和测试替身修正，以满足 Step 036 验证闭环；不新增接口、不改变 response schema、不新增依赖、不新增 migration。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| Python 版本检查 | `backend/.venv/bin/python --version` | 通过 | 当前项目环境为 Python 3.11.13 |
| Docker daemon 检查 | `docker version --format '{{.Server.Version}}'` | 通过 | Docker Server 版本为 26.1.3 |
| Compose 配置 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端 dev server 可访问 |
| 后端格式检查 | `cd backend && .venv/bin/black --check app tests migrations` | 通过 | 84 个文件无需格式化 |
| 后端 lint | `cd backend && .venv/bin/ruff check app tests migrations` | 通过 | All checks passed |
| 后端类型检查 | `cd backend && .venv/bin/mypy app tests` | 通过 | 初次发现既有类型标注问题；最小修正后复跑通过，74 个 source files 无问题 |
| 后端测试 | `cd backend && .venv/bin/python -m pytest tests -q` | 通过 | 42 passed, 1 warning |
| 前端 lint | `cd frontend && npm run lint` | 通过 | ESLint 通过 |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `cd frontend && npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| Migration 状态 | `docker compose exec backend-api alembic current` | 通过 | 当前为 `0009_create_feedback (head)` |
| Demo fixture seed | `docker compose exec backend-api python -m app.dev.seed_demo_fixture` | 通过 | 幂等生成/确认 Demo Fixture 知识库、demo 用户、indexed file、3 个 chunks |
| Demo citation + feedback API smoke | 真实 HTTP API 登录 `demo_user`、创建 conversation、发送推荐问题、提交 helpful、读取 detail | 通过 | assistant answer 包含 `[1]`；citation_count 为 3；首条 citation 含 file_name/source_locator/excerpt；feedback_rating 回显 `helpful` |
| Chat SSE API smoke | 真实 HTTP API 使用 `stream=true` 发送推荐问题 | 通过 | 返回 `text/event-stream; charset=utf-8`，包含 `message_created`、`retrieval`、`token`、`done`，并包含 `[1]` 引用编号 |
| MinerU API 方式核对 | 阅读 `backend/app/services/mineru.py` 并对照 `https://mineru.net/apiManage/docs` | 通过 | 当前实现采用 MinerU API 批量签名上传和批量结果查询；真实在线解析因无 token 未执行 |

## 7. 当前未完成事项

- 真实 MinerU 在线解析仍需要配置 `MINERU_API_TOKEN` 后执行。
- 真实 bge-m3 embedding-service 尚未作为 Compose 服务接入。
- 真实 BGE reranker-service 尚未作为 Compose 服务接入。
- 真实 LLM Provider 尚未接入，当前 Chat answer 仍是模板化 Demo 文本。
- 真实样本文档的上传、解析、索引、检索、重排、生成、引用端到端验收尚未执行。
- Playwright/Cypress 浏览器自动化测试体系尚未引入。

## 8. 风险与注意事项

- 第一版 Demo 已可交付演示，但不等同于 SDD v0.1 完整 MVP 内测通过。
- Demo fixture 使用本地确定性 demo embedding/reranker，仅用于演示 citation UI。
- 当前本地 `.env` 已打开 `DEMO_FIXTURE_ENABLED=true`，`.env.example` 默认仍为 `false`。
- 有 active indexed chunks 且未启用 Demo fixture/local demo client 时，真实 Retrieval/Chat 仍依赖外部 embedding/reranker 服务。
- 当前 `MINERU_API_TOKEN` 为空，点击真实重新解析会得到明确上游服务错误，这是外部条件未满足，不是当前 Demo 页面故障。

## 9. 下一步建议

建议下一步进入真实外部服务接入与端到端验收阶段：

1. 配置 `MINERU_API_TOKEN`，复跑真实 MinerU 在线解析。
2. 新增或接入真实 bge-m3 embedding-service。
3. 新增或接入真实 BGE reranker-service。
4. 接入 LLM Provider。
5. 使用 TDD 中真实样本文档执行完整上传到带引用回答的端到端验收。

如果短期仍不具备外部服务条件，则建议只做 Demo 稳定性和浏览器自动化验收，不继续扩大 SDD 未要求的业务功能。
