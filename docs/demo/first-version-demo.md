# 第一版 Demo 运行与验收说明

本文档记录当前第一版 Web Demo 的可运行范围、操作流程、验收边界和外部依赖缺口。它只描述当前仓库已经实现并验证过的能力，不把 fake 测试、模板回答或未配置外部服务描述为真实端到端能力。

第一版 Demo 交付验收报告详见：`docs/demo/first-version-demo-acceptance-report.md`。

前端页面验收步骤详见：`docs/demo/frontend-acceptance-checklist.md`。

## 1. Demo 当前定位

当前 Demo 是“基础 Web Demo 可操作版本”。

它已经可以演示：

- Admin 登录。
- 当前用户展示、个人资料页和退出登录。
- 知识库创建、查询、编辑、软删除。
- 文件上传、状态查看、重新解析入口、删除和 chunks 空态/调试页。
- 用户管理：创建、编辑、启用、禁用、重置密码。
- 审计日志查询和详情。
- Chat 会话创建、历史会话搜索、历史会话打开、历史会话删除、SSE 流式消息发送。
- 空知识库或证据不足时拒答。
- 受限 Demo fixture 路线：在无真实 MinerU/embedding/reranker/LLM 的本地环境中，种入明确标记的演示知识库、indexed 文件、chunks 和 Qdrant points，演示 Chat citation UI。
- Assistant message 引用展示入口。
- 会话、消息、引用、trace 保存。
- helpful / unhelpful 反馈提交。
- Retrieval API 的 vector + full-text merge 后 reranker client 接入。

它还不能在当前环境中证明：

- 真实 MinerU 在线解析。
- 真实 bge-m3 embedding-service 在线生成向量。
- 真实 Qdrant 向量索引完整写入后的问答。
- 真实 BGE reranker-service 在线重排。
- 真实 LLM 生成回答。
- “上传文件 -> MinerU API 解析 -> blocks -> chunks -> embedding -> Qdrant -> reranker -> LLM -> 带引用回答”的完整真实端到端链路。

注意：Demo fixture 路线仅用于第一版 Web Demo 演示 citation UI，不等同于真实 MinerU 解析、真实 embedding、真实 reranker 或真实 LLM 验收。

## 2. 启动前准备

### 2.1 环境要求

- Python 3.11+。
- Docker daemon 正常运行。
- Docker Compose 可用。
- Node / npm 由 frontend 容器负责，普通 Demo 启动不需要本机手动安装前端依赖。

### 2.2 环境变量

首次启动前复制环境变量文件：

```bash
cp .env.example .env
```

当前 Demo 默认 Admin：

| 项目 | 值 |
|---|---|
| 用户名 | `admin` |
| 密码 | `AdminPassword123` |
| 邮箱 | `admin@example.local` |

当前外部服务相关变量：

| 变量 | 当前默认值 | 当前状态 |
|---|---|---|
| `MINERU_API_BASE_URL` | `https://mineru.net` | 已用于 MinerU API client |
| `MINERU_API_TOKEN` | 空 | 未配置，真实 MinerU 在线解析不可执行 |
| `EMBEDDING_SERVICE_URL` | `http://embedding-service:8200` | Compose 尚未提供该服务 |
| `EMBEDDING_MODEL` | `bge-m3` | 已用于 embedding client 记录 |
| `RERANKER_SERVICE_URL` | `http://reranker-service:8300` | Compose 尚未提供该服务 |
| `RERANKER_MODEL` | `bge-reranker` | 已用于 reranker client 记录 |
| `LLM_PROVIDER` / `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` | 空 | 当前 Chat 为模板化 Demo answer |
| `DEMO_FIXTURE_ENABLED` | `false` | 开发/演示开关；本地需要演示 fixture citation 时设为 `true` |

MinerU 解析按用户要求采用 API 调用方式实现。当前代码已实现 batch upload/result 方式：

- `POST /api/v4/file-urls/batch`
- signed `PUT` 上传文件
- `GET /api/v4/extract-results/batch/{batch_id}`
- 下载 `full_zip_url`

真实在线验证需要先配置 `MINERU_API_TOKEN`。

## 3. 启动方式

### 3.1 启动完整基础栈

```bash
docker compose up --build
```

如果镜像已经构建过，也可以使用：

```bash
docker compose up -d
```

### 3.2 服务地址

| 服务 | 地址 |
|---|---|
| 前端 Demo | `http://localhost:5173` |
| 后端 API health | `http://localhost:8000/api/v1/health` |
| Qdrant | `http://localhost:6333` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

后端健康检查期望返回：

```json
{
  "status": "ok",
  "service": "backend-api",
  "version": "0.1.0"
}
```

### 3.3 数据库迁移

容器启动后执行迁移：

```bash
docker compose exec backend-api alembic upgrade head
```

### 3.4 可选：种入受限 Demo fixture

当当前环境没有真实 MinerU token、embedding-service、reranker-service 和 LLM Provider，但需要演示带引用的 Chat UI 时，可以启用受限 fixture 路线。

1. 在 `.env` 中设置：

```bash
DEMO_FIXTURE_ENABLED=true
```

2. 重新创建后端容器，让环境变量生效：

```bash
docker compose up -d --force-recreate backend-api
```

3. 执行 seed：

```bash
docker compose exec backend-api python -m app.dev.seed_demo_fixture
```

seed 会幂等生成：

| 项目 | 值 |
|---|---|
| 知识库 | `Demo Fixture 知识库` |
| 文件 | `demo-rag-fixture.txt` |
| Demo User | `demo_user` |
| Demo User 密码 | `DemoUserPassword123` |
| 推荐问题 | `井下落鱼可视化工具 使用步骤是什么？` |

验收结果：

- 生成 active knowledge base、indexed file、active chunks 和 Qdrant points。
- Chat 对推荐问题可返回 `[1]` 等引用编号。
- citation 包含 `file_name`、`source_locator`、`excerpt` 和 `chunk_id`。
- 该路径使用本地确定性 demo embedding/reranker，不调用真实 embedding-service/reranker-service。

注意：

- 该路线只用于开发/演示，不替代真实上传解析索引问答链路。
- 完整 SDD MVP 内测仍必须接入真实 MinerU、embedding-service、reranker-service 和 LLM Provider，或重新定义验收边界。

默认 Admin 会在后端启动时自动初始化。

## 4. 当前可演示流程

### 4.1 登录

1. 打开 `http://localhost:5173`。
2. 使用默认 Admin 登录：
   - 用户名：`admin`
   - 密码：`AdminPassword123`
3. 登录成功后进入 Chat 页面。

验收结果：

- 页面能够进入主应用。
- 侧边栏/顶部显示当前用户信息。
- Profile 页面能展示真实 `/auth/me` 返回的数据。

### 4.2 知识库管理

1. 进入知识库管理页面。
2. 创建一个知识库。
3. 编辑知识库名称。
4. 查询 active 知识库。
5. 删除知识库。
6. 如需要，按 deleted 状态确认软删除结果。

验收结果：

- 创建、编辑、删除走真实后端 API。
- 删除为软删除。
- 高危操作会进入审计日志。

### 4.3 文件上传和状态查看

1. 进入文件页面。
2. 选择 active 知识库。
3. 上传 `.txt`、`.md`、`.pdf` 等 SDD 白名单内文件。
4. 查看文件列表和状态。
5. 打开 chunks 调试页。

验收结果：

- 上传请求走真实 multipart API。
- 原始文件保存到 MinIO `raw-files`。
- 同名文件会被拒绝。
- 同知识库同 hash 但不同文件名会返回 warning，可通过 force 上传。
- 当前未完成真实解析/索引的文件，chunks 页面可能为空，这是当前外部依赖缺失下的预期结果。

注意：

- 点击重新解析会触发 MinerU API client。
- 如果 `MINERU_API_TOKEN` 未配置，后端会返回明确的上游服务错误。
- 这不是页面故障，而是当前真实解析外部条件未满足。

### 4.4 Chat SSE 与拒答

1. 进入 Chat 页面。
2. 选择一个知识库。
3. 创建会话。
4. 使用左侧搜索框按标题过滤历史会话。
5. 输入问题并发送。
6. 在历史会话列表中删除会话。

验收结果：

- 前端使用 POST SSE 流式读取后端响应。
- 历史会话搜索在当前知识库的已加载会话列表内按标题本地过滤。
- 后端返回 `text/event-stream`。
- SSE events 包含：
  - `message_created`
  - `retrieval`
  - `token`
  - `done`
- 空知识库或无 active indexed chunks 时返回证据不足拒答。
- 用户消息、assistant 消息和 trace 会保存。
- 删除历史会话会调用真实 `DELETE /api/v1/conversations/{conversation_id}` 接口。
- 删除后的会话会从当前知识库历史列表中移除；如果删除的是当前会话，页面会切换到下一条会话或清空消息区。

注意：

- 当前 Chat 回答是模板化 Demo answer。
- 当前 token streaming 是模板文本分片，不是真实 LLM token streaming。
- 删除会话采用软删除；后端保留 messages、citations、traces 和 feedback 历史数据。
- 如果知识库中存在 active indexed chunks，默认检索链路会调用 embedding-service、Qdrant 和 reranker-service；当前 Compose 没有真实 embedding-service / reranker-service，因此真实带引用回答路径仍不可在线验证。
- 如果启用 `DEMO_FIXTURE_ENABLED=true` 并执行 seed，当前本地 Demo 会使用本地确定性 demo embedding/reranker 和 Qdrant points 演示 citation UI。

### 4.4.1 Demo fixture citation 前端验收

完整页面验收清单见 `docs/demo/frontend-acceptance-checklist.md`。

核心流程：

1. 使用 `demo_user` / `DemoUserPassword123` 登录。
2. 选择 `Demo Fixture 知识库`。
3. 新建会话。
4. 发送：`井下落鱼可视化工具 使用步骤是什么？`
5. 检查 assistant answer 包含 `[1]`。
6. 点击 citation chip，检查右侧引用详情显示：
   - `demo-rag-fixture.txt`
   - `demo:section-1`
   - 原文片段
7. 点击 helpful / unhelpful 并重新打开历史会话，检查 feedback 状态回显。

Step 035 已为 Chat 页面补充稳定 `data-testid` selector，供后续 Playwright/Cypress 或人工辅助验收使用。

### 4.5 Feedback

1. 在 Chat 页面发送消息。
2. 对 assistant message 点击 helpful 或 unhelpful。
3. 重新打开该历史会话。

验收结果：

- Feedback 走真实后端 API。
- 同一用户对同一 assistant message 的 feedback 会 upsert。
- Feedback telemetry 会保存 query、retrieved chunk ids、final cited chunk ids、model、prompt、embedding、reranker 信息。
- 历史会话重新打开后，assistant message 的 helpful/unhelpful 按钮会回显当前用户已提交的状态。

### 4.6 用户与审计

1. 进入用户管理页面。
2. 创建普通用户。
3. 编辑、禁用、启用、重置密码。
4. 进入审计日志页面查询知识库/文件等操作日志。

验收结果：

- 用户管理接口只有 Admin 可访问。
- 普通 User 访问 Admin-only API 会返回 `403 FORBIDDEN`。
- 用户创建、编辑、禁用、启用、重置密码会写入 audit_logs。
- 重置密码审计不会记录明文密码或 password hash。
- 审计日志页面读取真实后端数据，并以可读中文文案展示常见操作类型。

## 5. SDD MVP 验收矩阵

| SDD MVP 条目 | 当前状态 | 说明 |
|---|---|---|
| Admin 登录与用户管理 | 已完成 | Auth、Users API、前端页面已接真实接口 |
| Admin 创建、编辑、删除知识库 | 已完成 | 支持软删除和审计 |
| Admin 上传多格式文件 | 已完成基础能力 | 支持白名单、大小、同名、hash 校验 |
| 原始文件保存到 MinIO | 已完成 | `raw-files` 已验证 |
| 使用 MinerU 解析文件 | 部分完成 | 已实现 API client；真实 token 未配置，在线解析未验证 |
| 解析结果持久化 | 部分完成 | fake/fixture 路径已验证；真实 MinerU 产物未在线验证 |
| blocks 标准化 | 已完成基础能力 | document_blocks 已落库 |
| chunks 生成 | 已完成基础能力 | 当前为 one-block-one-chunk MVP 策略 |
| bge-m3 embedding | 部分完成 | client 抽象和 fake 测试完成；Demo fixture 可使用本地确定性 embedding；真实服务未提供 |
| Qdrant 写入/失效 | 部分完成 | client 和真实 Qdrant smoke 完成；Demo fixture 已写入 Qdrant points；indexed 文件删除时 fake Qdrant points 失效已验证；完整真实文件索引未验证 |
| PostgreSQL tsvector 全文检索 | 已完成基础能力 | 当前中文质量未专项优化 |
| Vector + Full-text 混合召回 | 已完成基础能力 | Retrieval API 已实现 |
| BGE Reranker 重排 | 部分完成 | client 抽象和 fake 排序测试完成；Demo fixture 可使用本地确定性 reranker；真实服务未提供 |
| User 基于单知识库提问 | 已完成基础能力 | Conversation 绑定 knowledge_base_id |
| SSE 流式返回回答 | 已完成基础能力 | 当前流式模板文本 |
| 回答带引用编号 | 部分完成 | Demo fixture 路线已通过真实 API smoke 返回 `[1]`；真实带引用回答依赖完整索引链路 |
| 引用包含文件名、定位、片段 | 部分完成 | Demo fixture 路线已通过真实 API smoke 返回 file_name/source_locator/excerpt/chunk_id；真实可引用数据依赖完整索引链路 |
| 证据不足拒答 | 已完成 | 空知识库路径已验证 |
| 保存会话、消息、引用、trace | 已完成基础能力 | 已落库 |
| helpful / unhelpful 反馈 | 已完成 | 支持 upsert 和 telemetry |
| 高危操作审计日志 | 已完成基础能力 | 知识库/文件等操作已写入审计 |
| Docker Compose 一键启动完整系统 | 部分完成 | 基础栈可启动；缺真实 embedding-service / reranker-service / worker |

## 6. 当前验收命令

后端本地验证：

```bash
backend/.venv/bin/black --check backend/app backend/tests backend/migrations
backend/.venv/bin/ruff check backend/app backend/tests backend/migrations
backend/.venv/bin/mypy backend/app backend/tests
cd backend && .venv/bin/pytest
```

前端验证：

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

运行服务验证：

```bash
docker compose config --quiet
docker compose ps
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:5173 >/dev/null
```

## 7. 当前第一版 Demo 验收结论

当前可以验收为：

“第一版基础 Web Demo 可操作，主要页面和后端基础接口已接通，能够演示登录、知识库、文件上传、用户/审计、Chat SSE 拒答、trace、feedback，以及受限 Demo fixture 下的 citation UI。”

Step 036 已补充交付验收报告：`docs/demo/first-version-demo-acceptance-report.md`。

当前不能验收为：

“SDD v0.1 完整 MVP 已完成”。

原因：

- `MINERU_API_TOKEN` 未配置，真实 MinerU 在线解析未验证。
- Compose 尚未提供真实 embedding-service。
- Compose 尚未提供真实 reranker-service。
- 当前 Chat 仍是模板化回答，不是真实 LLM。
- 真实带引用回答端到端链路未被当前环境证明。
- Demo fixture 只能证明当前 UI/API citation 数据结构和保存链路可演示，不能证明真实解析索引与真实模型质量。

## 8. 下一步选择

### 选项 A：接入真实外部服务

适用条件：

- 提供 `MINERU_API_TOKEN`。
- 提供或允许新增真实 embedding-service。
- 提供或允许新增真实 reranker-service。
- 提供 LLM Provider 配置。

下一步：

- 重新执行 Step 016 真实端到端验证。
- 验证上传真实文件后可进入 indexed。
- 验证删除真实 indexed 文件后旧 chunks 不再参与检索。
- 验证 Chat 能返回带真实引用的回答。

### 选项 B：使用已实现的 Demo fixture 路线

适用条件：

- 短期无法提供真实外部服务。
- 允许新增仅限开发/演示用途的数据种子或 fixture 路径。

当前状态：

- Step 034 已新增受限 seed 命令：`python -m app.dev.seed_demo_fixture`。
- Step 034 已生成 active knowledge base、indexed file、chunks、Qdrant points。
- Step 034 已使用本地可控 demo embedding/reranker 让 Chat 演示 citation UI。

下一步：

- 通过前端页面用 `demo_user` 登录，选择 `Demo Fixture 知识库`，发送推荐问题并检查 citation UI。
- 可补充前端自动化截图或 Playwright 点击验证。

注意：

- 该路线不能替代真实 MinerU / embedding / reranker / LLM 验收。
- 必须在文档和代码入口中明确标记为开发 Demo，避免污染生产逻辑。
