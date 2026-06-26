# Step 034：受限 Demo fixture/seed 引用演示路线

## 1. 本步骤目标

在不新增真实外部模型服务、不改变 SDD 核心业务链路的前提下，提供一个明确标记为开发/演示用途的 Demo fixture 路线，让第一版 Web Demo 能稳定演示“已有 indexed chunks -> Chat 返回引用编号和 citation 详情”的界面与 API 闭环。

## 2. 对应 SDD 条目

- SDD v0.1：回答必须带引用编号。
- SDD v0.1：引用必须包含文件名、定位信息和原文片段。
- SDD v0.1：保存会话、消息、引用、trace。
- SDD v0.1：User 可登录、选择知识库、提问、查看引用、提交反馈。
- Step 033 下一步建议：开发受限 Demo fixture/seed 路线，演示 citation UI，但不声称其等同真实生产 RAG。

## 3. 本步骤完成内容

- 新增 `DEMO_FIXTURE_ENABLED` 配置项，默认关闭。
- 在 `.env.example` 中记录 fixture 开关默认值 `false`。
- 在当前本地 `.env` 中启用 `DEMO_FIXTURE_ENABLED=true`，使当前 Demo 环境可直接演示 fixture citation。
- 新增本地确定性 `LocalDemoEmbeddingClient`，仅在 fixture 开关开启时由依赖工厂返回。
- 新增本地确定性 `LocalDemoRerankerClient`，仅在 fixture 开关开启时由依赖工厂返回。
- 新增 `app.dev.seed_demo_fixture`，可通过 `python -m app.dev.seed_demo_fixture` 幂等生成：
  - `Demo Fixture 知识库`
  - `demo-rag-fixture.txt`
  - `demo_user` / `DemoUserPassword123`
  - indexed parse_job
  - 3 个 active chunks
  - Qdrant points
  - MinIO raw file object
- seed 重复执行时会先失效旧 active fixture chunks 对应的 Qdrant points，再生成新的 active chunks。
- 新增后端测试覆盖 seed 生成、幂等失效、本地 demo clients 选择和 reranker 排序。
- 使用真实运行服务完成 Demo fixture Chat citation smoke：
  - 登录 `demo_user`
  - 创建 conversation
  - 发送推荐问题
  - assistant answer 返回 `[1]`
  - citation 返回 `file_name`、`source_locator`、`excerpt`、`chunk_id`
  - conversation detail 可回显持久化 citations
- 更新 README、Demo 文档和 TDD 当前状态。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `.env` | 修改 | 当前本地 Demo 环境启用 `DEMO_FIXTURE_ENABLED=true` |
| `.env.example` | 修改 | 增加开发/演示 fixture 开关，默认 `false` |
| `README.md` | 修改 | 补充受限 Demo fixture 启动方式、账号和边界说明 |
| `backend/app/core/config.py` | 修改 | 新增 `demo_fixture_enabled` 配置项 |
| `backend/app/services/embedding.py` | 修改 | 新增本地确定性 demo embedding client，并在开关开启时使用 |
| `backend/app/services/reranker.py` | 修改 | 新增本地确定性 demo reranker client，并在开关开启时使用 |
| `backend/app/dev/__init__.py` | 新增 | 标记开发专用 helper 包 |
| `backend/app/dev/seed_demo_fixture.py` | 新增 | 实现幂等 Demo fixture seed 命令 |
| `backend/tests/test_demo_fixture.py` | 新增 | 覆盖 fixture seed、幂等失效和 demo client 选择 |
| `docs/demo/first-version-demo.md` | 修改 | 补充 fixture seed 步骤、账号、推荐问题、验收边界 |
| `docs/tests/TDD.v0.1.md` | 修改 | 补充 fixture citation 可演示状态，并保留完整 MVP 未满足说明 |
| `docs/progress/step-034-demo-fixture-citation-seed.md` | 新增 | 记录 Step 034 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 034 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- `DEMO_FIXTURE_ENABLED=false` 是默认值，真实运行仍默认调用外部 embedding-service 和 reranker-service。
- `LocalDemoEmbeddingClient` 使用确定性 2 维向量，避免引入新依赖，并兼容当前 Qdrant `chunks` collection 的既有 smoke 维度。
- `LocalDemoRerankerClient` 使用本地可解释的词/字符重叠分数，仅服务于演示 citation UI。
- `seed_demo_fixture()` 直接写入符合现有业务表结构的 active knowledge base、indexed file、indexed parse_job 和 active chunks。
- `seed_demo_fixture()` 使用现有 `build_qdrant_point()` 构造 Qdrant payload，保持 chunk_id、knowledge_base_id、file_id、source_locator、is_active 等字段与真实索引路径一致。
- seed 命令入口在 `app.dev` 命名空间下，并且要求 `DEMO_FIXTURE_ENABLED=true`，避免误作为生产数据初始化入口。
- 当前 Chat 仍是模板化 Demo answer，不是真实 LLM 生成；fixture 只证明 citation UI/API/持久化链路可演示。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 新增 fixture 测试 | `backend/.venv/bin/python -m pytest backend/tests/test_demo_fixture.py -q` | 通过 | `3 passed` |
| 后端格式检查 | `backend/.venv/bin/python -m black --check backend/app backend/tests` | 通过 | 新增文件格式化后通过 |
| 后端 lint | `backend/.venv/bin/python -m ruff check backend/app backend/tests` | 通过 | `All checks passed!` |
| 后端类型检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | `Success: no issues found in 64 source files` |
| 完整后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | `42 passed, 60 warnings` |
| Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置有效 |
| 后端环境开关检查 | `docker compose exec -T backend-api python - <<'PY' ... get_settings().demo_fixture_enabled ... PY` | 通过 | 输出 `True` |
| Demo fixture seed | `docker compose exec -T backend-api python -m app.dev.seed_demo_fixture` | 通过 | 生成 Demo KB、文件、parse_job、3 个 chunk、demo_user 和推荐问题 |
| Demo citation API smoke | 使用真实 HTTP API 登录 `demo_user`、创建 conversation、发送推荐问题、检查 assistant citations | 通过 | assistant answer 包含 `[1]`；citation_count 为 3；第一条 citation 文件为 `demo-rag-fixture.txt` |
| Migration 状态检查 | `docker compose exec -T backend-api alembic current` | 通过 | 当前为 `0009_create_feedback (head)`；本步骤无新增 migration |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端 dev server 可访问 |
| 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端镜像构建 | `docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple backend-api` | 通过 | 后端镜像构建成功 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 源码关键字扫描 | `rg -n 'DEMO_FIXTURE_ENABLED|LocalDemoEmbeddingClient|LocalDemoRerankerClient|seed_demo_fixture|Demo Fixture 知识库|demo_user' ...` | 通过 | 可定位 fixture 开关、实现、测试和文档 |

## 7. 当前未完成事项

- 真实 MinerU 在线解析仍需配置 `MINERU_API_TOKEN` 后验证。
- 真实 embedding-service、reranker-service 和 LLM Provider 仍未接入。
- 真实上传文件到带引用回答的完整端到端链路仍未通过。
- 前端尚未配置 Playwright，未执行自动化浏览器点击/截图验证。
- `cleanup_jobs` 表、异步清理 MinIO/Qdrant 残留对象和知识库删除级联清理仍未实现。

## 8. 风险与注意事项

- Demo fixture 路线只用于开发/演示，不代表真实 RAG 质量。
- 当前 `.env` 已为本地 Demo 打开 `DEMO_FIXTURE_ENABLED=true`；`.env.example` 默认仍是 `false`。
- 本地 demo embedding/reranker 只在开关开启时生效；完整 MVP 必须恢复/接入真实外部模型服务后重新验收。
- seed 会重置 `demo_user` 的密码为 `DemoUserPassword123`，仅适用于本地开发 Demo。
- 当前 Chat 仍是模板化 answer，不是真实 LLM。

## 9. 下一步建议

建议进入 Step 035：第一版 Demo 前端验收固化。

原因：后端真实 API smoke 已证明 fixture citation 数据链路可用。下一步应围绕前端页面验收，把 `demo_user` 登录、选择 `Demo Fixture 知识库`、发送推荐问题、查看 citation chips/detail、提交 feedback 的流程固化为文档化验收或 Playwright 自动化截图/点击验证，进一步提高第一版 Demo 的可交付确定性。
