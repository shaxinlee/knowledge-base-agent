# Knowledge Base Agent Assistant

## 中文版

### 项目作用

Knowledge Base Agent Assistant 是一个面向企业/团队内部知识库的 RAG 问答系统。它的目标是把用户上传的文档转换为可检索、可追溯、可审计的知识资产，并在对话中基于真实文档证据生成带引用的回答。

当前项目已经从早期 Web Demo 演进为具备完整主链路实现的 v0.1 原型：支持用户与权限管理、知识库管理、文件上传、MinerU 文档解析、结构化 blocks/chunks 生成、向量索引、中文 BM25 关键词索引、混合检索、Reranker 重排、LLM 问答、引用溯源、反馈和审计日志。

核心链路如下：

```text
上传文件
  -> MinIO 保存原始文件
  -> MinerU API 解析 PDF/文档
  -> 标准化 document_blocks
  -> heading-aware recursive chunking
  -> Embedding 生成向量
  -> Qdrant 向量索引 + OpenSearch BM25 中文关键词索引
  -> Vector/BM25 混合召回
  -> RRF 融合
  -> Reranker 重排
  -> LLM 生成带 citation 的回答
  -> 保存 conversation/message/citation/trace/feedback/audit log
```

### 当前实现的功能

- 认证与权限：默认 Admin 初始化、JWT access/refresh token、refresh token logout/revoke、登录失败锁定、Admin/User RBAC。
- 用户管理：Admin 可创建、编辑、启用/禁用用户、重置密码，并写入审计日志。
- 知识库管理：知识库创建、查询、编辑、软删除、状态过滤、文件数和 active chunk 数统计。
- 文件管理：文件上传校验、Hash 重复提示与强制上传、MinIO `raw-files` 存储、状态查询、重新解析、软删除。
- 解析任务：上传/重试后创建 `parse_job`，由后端轻量 in-process worker 后台推进 queued/parsing/normalizing/chunking/embedding/indexing 阶段；状态接口保持只读。
- MinerU 接入：已实现 MinerU API batch upload/result 链路，保存 parsed zip 到 MinIO `parsed-results`，并记录上游状态、错误码和日志。
- 文档标准化：支持 MinerU Markdown/JSON 产物标准化，提取标题层级、表格、页面/块元数据、图片/OCR 区域、source locator 和资产路径。
- Chunking：已从 one-block-one-chunk 升级为 `heading_aware_recursive`，支持标题上下文合并、长文本递归切分、overlap，以及表格/图片 OCR 边界保留。
- Embedding 与向量索引：支持 OpenAI-compatible embeddings、旧本地 `/embed` 服务契约，以及 Qwen 多模态 embedding provider；索引写入 Qdrant，并按知识库和 active 状态过滤检索。
- 中文关键词检索：已接入 OpenSearch BM25 + IK Analyzer，默认 `ik_max_word` 建索引、`ik_smart` 搜索；PostgreSQL/SQLite full-text 保留为 fallback。
- 混合检索：Qdrant vector topK + OpenSearch BM25 topK 召回，使用 RRF 融合后送入 Reranker。
- Reranker：支持通用 `/rerank` API 和 DashScope/Qwen text rerank endpoint，trace 中保存 reranked chunk ids 与 reranker scores。
- LLM 问答：Chat 链路支持可配置 LLM API；无充分证据时按 evidence gate 拒答；测试/演示环境保留明确标记的 template demo client。
- 对话系统：conversation/message/citation/trace 持久化，支持历史会话列表、搜索、打开、软删除，支持非流式与 SSE 流式回答。
- 引用溯源：回答可返回 citation，包含文件名、source locator、excerpt、chunk id 等信息。
- 反馈：assistant message 支持 helpful/unhelpful feedback upsert，并保存 query、召回 chunk、最终引用 chunk 和模型元数据。
- 审计日志：知识库、文件、用户管理等关键操作写入 audit logs，前端展示中文可读操作文案并保留原始 code。
- 前端页面：Vue + Vite 前端已接入真实 API，包含登录、Chat、文件、chunks、知识库、用户、审计日志、个人资料、403/404 等页面。
- 多模态基础骨架：已新增 QueryRouter、多标签路由、Qwen 多模态 embedding provider、ImageBlock/Evidence 数据结构和 Weighted RRF evidence 融合测试骨架；图片证据尚未完整接入 Chat 主链路。

### 当前边界

- 代码层面已实现真实解析、索引、检索、重排和 LLM 问答主链路；运行时需要在 `.env` 中配置真实 MinerU、embedding、reranker、LLM/Qwen/DashScope 等外部服务密钥和地址。
- 本仓库不提交真实 API token/key；`.env.example` 只提供占位配置。
- 当前后台推进器是 backend-api 进程内轻量 worker，不是独立队列系统。多实例部署时需要引入数据库锁、Redis Queue、Celery、RQ、Dramatiq 等机制。
- OpenSearch 当前是本地开发单节点配置，适合 Demo/开发验证；生产部署需要补充安全、备份、分片副本和运维配置。
- 多模态图片/视觉证据召回已有基础抽象，但尚未完整接入真实 Chat 主链路。

### 项目结构

```text
backend/                  FastAPI 后端、SQLAlchemy 模型、Alembic 迁移、RAG 服务、测试
frontend/                 Vue + Vite 前端，已接入真实后端 API
docs/specs/               SDD 产品范围、架构、数据库、API、里程碑和验收标准
docs/tests/               TDD 测试范围、用例、验收门槛和阻塞项
docs/api/                 可读 API contract 与 OpenAPI contract
docs/demo/                Demo 启动、操作流和验收边界
docs/progress/            按步骤记录的开发进度
opensearch/               OpenSearch + IK Analyzer 本地开发镜像与词典
docker-compose.yml        本地基础服务编排
.env.example              本地环境变量模板
```

### 本地启动

复制环境变量模板：

```bash
cp .env.example .env
```

按需在 `.env` 中配置真实外部服务：

```text
MINERU_API_TOKEN=
EMBEDDING_API_BASE_URL=
EMBEDDING_API_KEY=
QWEN_API_KEY=
RERANKER_API_BASE_URL=
RERANKER_API_KEY=
LLM_API_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
INTENT_RECOGNITION_API_BASE_URL=
INTENT_RECOGNITION_API_KEY=
INTENT_RECOGNITION_MODEL=
KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL=
KNOWLEDGE_SEARCH_CLASSIFIER_API_KEY=
KNOWLEDGE_SEARCH_CLASSIFIER_MODEL=
IMAGE_DESCRIPTION_API_BASE_URL=
IMAGE_DESCRIPTION_API_KEY=
IMAGE_DESCRIPTION_MODEL=
```

启动本地栈：

```bash
docker compose up --build
```

执行数据库迁移：

```bash
docker compose exec backend-api alembic upgrade head
```

默认本地入口：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://localhost:5173` |
| 后端健康检查 | `http://localhost:8000/api/v1/health` |
| Qdrant | `http://localhost:6333` |
| OpenSearch | `http://localhost:9200` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

默认 Admin：

| 字段 | 值 |
| --- | --- |
| Username | `admin` |
| Password | `AdminPassword123` |
| Email | `admin@example.local` |

后端健康检查期望返回：

```json
{
  "status": "ok",
  "service": "backend-api",
  "version": "0.1.0"
}
```

### 开发检查

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
black --check app tests migrations
ruff check app tests migrations
mypy app tests
pytest
```

前端：

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

### 主要文档

- `docs/specs/SDD.v0.1.md`：产品范围、架构和验收标准的主要来源。
- `docs/tests/TDD.v0.1.md`：测试计划、验收门槛和当前测试状态。
- `docs/api/frontend-backend-api-contract.md`：前后端可读 API contract。
- `docs/api/openapi.v0.1.yaml`：OpenAPI contract。
- `docs/demo/first-version-demo.md`：Demo 运行和验收边界说明。
- `docs/progress/README.md`：开发进度总览。
- `AGENTS.md`：本仓库 AI coding 协作规则。

任何 API 变更都应同步更新可读 API contract、OpenAPI、前端类型和相关 TDD 用例。

---

## English Version

### Purpose

Knowledge Base Agent Assistant is a RAG question-answering system for internal team or enterprise knowledge bases. Its goal is to turn uploaded documents into searchable, traceable, and auditable knowledge assets, then answer user questions with citations grounded in the original documents.

The project has evolved from an early Web Demo into a v0.1 prototype with the main RAG pipeline implemented: user and permission management, knowledge base management, file upload, MinerU document parsing, normalized blocks/chunks, vector indexing, Chinese BM25 keyword indexing, hybrid retrieval, reranking, LLM answer generation, citations, feedback, and audit logs.

Main pipeline:

```text
Upload file
  -> Store raw file in MinIO
  -> Parse document through MinerU API
  -> Normalize document_blocks
  -> Build heading-aware recursive chunks
  -> Generate embeddings
  -> Index into Qdrant vectors + OpenSearch BM25 keyword documents
  -> Retrieve with Vector/BM25 hybrid search
  -> Fuse with RRF
  -> Rerank candidates
  -> Generate cited answer with LLM
  -> Persist conversation/message/citation/trace/feedback/audit log
```

### Implemented Features

- Auth and permissions: default Admin bootstrap, JWT access/refresh tokens, refresh token logout/revoke, login failure lockout, Admin/User RBAC.
- User management: Admin can create, edit, enable/disable users, reset passwords, and write audit logs.
- Knowledge base management: create, list, update, soft delete, status filtering, real file count and active chunk count.
- File management: upload validation, duplicate hash warning and force upload, MinIO `raw-files` storage, status query, retry parse, soft delete.
- Parse jobs: upload/retry creates a `parse_job`; a lightweight in-process backend worker advances queued/parsing/normalizing/chunking/embedding/indexing stages; the file status endpoint is read-only.
- MinerU integration: implemented MinerU batch upload/result flow, parsed zip storage in MinIO `parsed-results`, upstream status/error/log recording.
- Document normalization: supports MinerU Markdown/JSON outputs, heading hierarchy, tables, page/block metadata, image/OCR areas, source locators, and asset paths.
- Chunking: upgraded from one-block-one-chunk to `heading_aware_recursive`, with heading-context merging, recursive long-text splitting, overlap, and table/image OCR boundary preservation.
- Embeddings and vector indexing: supports OpenAI-compatible embeddings, the legacy local `/embed` service contract, and Qwen multimodal embedding provider; indexes vectors into Qdrant with knowledge-base and active-state filters.
- Chinese keyword retrieval: uses OpenSearch BM25 + IK Analyzer by default, with `ik_max_word` for indexing and `ik_smart` for search; PostgreSQL/SQLite full-text search remains available as a fallback.
- Hybrid retrieval: retrieves Qdrant vector topK and OpenSearch BM25 topK, fuses candidates with RRF, then sends them to the reranker.
- Reranker: supports a generic `/rerank` API and the DashScope/Qwen text rerank endpoint; traces store reranked chunk ids and reranker scores.
- LLM answers: Chat can call a configurable LLM API; an evidence gate refuses weakly grounded questions; tests/demo environments keep an explicitly marked template demo client.
- Conversations: persistent conversations, messages, citations, and traces; supports history list, search, open, soft delete, non-streaming answers, and SSE streaming answers.
- Citations: answers can include citations with file name, source locator, excerpt, and chunk id.
- Feedback: assistant messages support helpful/unhelpful feedback upsert with query, retrieved chunks, final cited chunks, and model metadata.
- Audit logs: key knowledge base, file, and user management actions are written to audit logs; the frontend displays readable Chinese labels while preserving raw codes.
- Frontend pages: Vue + Vite frontend is wired to real APIs, including login, Chat, files, chunks, knowledge bases, users, audit logs, profile, 403, and 404 pages.
- Multimodal foundation: QueryRouter, multi-label routing, Qwen multimodal embedding provider, ImageBlock/Evidence data structures, and Weighted RRF evidence fusion test scaffolding are in place; visual evidence is not fully wired into the main Chat path yet.

### Current Boundaries

- The real parsing, indexing, retrieval, reranking, and LLM answer path is implemented in code, but runtime execution requires valid external MinerU, embedding, reranker, LLM/Qwen/DashScope configuration in `.env`.
- Real API tokens/keys are not committed. `.env.example` contains placeholders only.
- The current parse worker is a lightweight in-process worker inside `backend-api`, not a standalone queue system. Multi-instance deployment should add database locks, Redis Queue, Celery, RQ, Dramatiq, or an equivalent worker mechanism.
- OpenSearch is configured as a local development single-node service. Production deployment needs security, backup, shard/replica, and operations hardening.
- Multimodal image/visual evidence retrieval has foundational abstractions, but is not fully connected to the production Chat path.

### Repository Layout

```text
backend/                  FastAPI backend, SQLAlchemy models, Alembic migrations, RAG services, tests
frontend/                 Vue + Vite frontend wired to real backend APIs
docs/specs/               SDD product scope, architecture, database, APIs, milestones, acceptance criteria
docs/tests/               TDD test scope, cases, gates, and blockers
docs/api/                 Readable API contract and OpenAPI contract
docs/demo/                Demo startup, operation flow, and acceptance boundary
docs/progress/            Step-by-step development progress records
opensearch/               Local OpenSearch + IK Analyzer image and dictionaries
docker-compose.yml        Local service orchestration
.env.example              Local environment template
```

### Local Startup

Copy the environment template:

```bash
cp .env.example .env
```

Configure real external services in `.env` as needed:

```text
MINERU_API_TOKEN=
EMBEDDING_API_BASE_URL=
EMBEDDING_API_KEY=
QWEN_API_KEY=
RERANKER_API_BASE_URL=
RERANKER_API_KEY=
LLM_API_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
INTENT_RECOGNITION_API_BASE_URL=
INTENT_RECOGNITION_API_KEY=
INTENT_RECOGNITION_MODEL=
KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL=
KNOWLEDGE_SEARCH_CLASSIFIER_API_KEY=
KNOWLEDGE_SEARCH_CLASSIFIER_MODEL=
IMAGE_DESCRIPTION_API_BASE_URL=
IMAGE_DESCRIPTION_API_KEY=
IMAGE_DESCRIPTION_MODEL=
```

Start the local stack:

```bash
docker compose up --build
```

Run database migrations:

```bash
docker compose exec backend-api alembic upgrade head
```

Default local endpoints:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend health | `http://localhost:8000/api/v1/health` |
| Qdrant | `http://localhost:6333` |
| OpenSearch | `http://localhost:9200` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Default Admin:

| Field | Value |
| --- | --- |
| Username | `admin` |
| Password | `AdminPassword123` |
| Email | `admin@example.local` |

Expected backend health response:

```json
{
  "status": "ok",
  "service": "backend-api",
  "version": "0.1.0"
}
```

### Development Checks

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
black --check app tests migrations
ruff check app tests migrations
mypy app tests
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

### Primary Documents

- `docs/specs/SDD.v0.1.md`: main source for product scope, architecture, and acceptance criteria.
- `docs/tests/TDD.v0.1.md`: test plan, acceptance gates, and current test state.
- `docs/api/frontend-backend-api-contract.md`: readable frontend-backend API contract.
- `docs/api/openapi.v0.1.yaml`: OpenAPI contract.
- `docs/demo/first-version-demo.md`: Demo startup and acceptance boundary.
- `docs/progress/README.md`: development progress index.
- `AGENTS.md`: AI coding collaboration rules for this repository.

Any API change should update the readable API contract, OpenAPI file, frontend types, and related TDD cases together.
