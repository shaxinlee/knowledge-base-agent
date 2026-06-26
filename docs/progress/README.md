# 项目开发进度总览

## 当前总体状态

项目当前已完成 SDD v0.1 Phase 0 基础补齐、Phase 1 用户认证与权限基础闭环、Phase 2-A 知识库模型/CRUD/审计基础、Phase 2-B 文件模型/上传校验/MinIO raw-files 基础、Phase 3-A MinerU API client 与 parse_job 提交/轮询基础、Phase 3-B document_blocks 与 MinerU 解析产物标准化、Phase 3-C chunks_metadata 与基础 chunking、Phase 4-A embedding-service 与 Qdrant 索引基础、Phase 5-A 检索基础 API、Phase 5-B Reranker Client 与检索重排基础、Phase 6-A conversation/message/trace 基础、Phase 6-B Chat SSE 流式 Demo、Phase 7-A helpful/unhelpful 反馈基础、Phase 8-A 前端 Chat Demo 真实接口联调、Phase 8-B 前端文件上传与后台管理页面真实接口联调、第一版 Demo 运行说明与验收边界整理、API Contract / OpenAPI / 前端类型一致性同步、TDD 文档与当前实现差异核对、message trace 中 reranker_scores 补齐、当前用户删除自己 conversation 接口、前端 Chat 历史会话删除交互、Chat 历史会话搜索过滤、Chat 历史消息 feedback 状态回显、用户管理操作审计日志写入、审计日志前端可读操作文案、indexed 文件删除时 chunks/Qdrant 失效闭环、受限 Demo fixture/seed 引用演示路线，以及第一版 Demo 前端验收固化。后端已具备 SQLAlchemy/Alembic 数据库迁移基础，`users`、`user_profiles`、`revoked_refresh_tokens`、`knowledge_bases`、`audit_logs`、`files`、`parse_jobs`、`document_blocks`、`chunks_metadata`、`conversations`、`messages`、`message_citations`、`message_traces`、`feedback` 表已通过 migration 落库；默认 Admin、JWT access/refresh token、Auth API、refresh token logout/revoke、Users API、KnowledgeBase API、Files API、Audit Logs API、Retrieval API、Conversations API、Feedback API、Admin/User 权限边界、MinerU fake parse 链路、document_blocks 标准化、chunks 生成、fake embedding/Qdrant 索引闭环、删除 indexed 文件时 chunks/Qdrant points 失效、Demo fixture indexed chunks/Qdrant points/citation smoke、检索合并去重、reranker client 抽象与 fake/local demo reranker 重排验证、SSE 模板化问答、citations、trace 保存、feedback telemetry 保存、conversation 软删除、用户管理审计日志、前端审计日志可读文案、前端登录/Chat 页面真实接口联调、前端 Chat 历史会话删除/搜索/feedback 回显交互、前端 fixture citation 验收 selector/清单，以及前端文件上传/状态/Chunk 调试/后台管理页面真实接口联调已通过本地与运行服务验证。当前完整 Docker Compose 已能启动 frontend、backend-api、postgres、redis、qdrant、minio；`docs/demo/first-version-demo.md` 已记录当前 Demo 可运行流程、fixture citation 路线、前端验收清单、验收矩阵和外部依赖缺口；Readable API contract、OpenAPI 和前端类型已同步当前 SSE、feedback、reranker 与 Profile 边界；`docs/tests/TDD.v0.1.md` 已补充当前基础 Demo 已验证能力、完整 MVP 未解除缺口和关键测试用例当前状态；Chat trace 已保存 reranked_chunk_ids 与 `{chunk_id: score}` 形式的 reranker_scores；当前用户可通过后端 API 和前端 Chat 页面软删除自己的 conversation，Chat 历史会话搜索输入框已支持按标题本地过滤，历史 conversation detail 会返回当前用户对 assistant message 的 feedback 状态并在前端回显；Admin 用户管理操作会写入 audit_logs，审计日志页面已将常见 action/resource_type 展示为中文文案并保留原始 code。

当前已具备第一版 Web Demo 的基础操作闭环：登录、真实当前用户展示、真实退出登录、真实个人资料、真实知识库管理、真实用户管理、用户管理操作审计、真实审计日志查询、审计日志中文操作文案、创建知识库、上传文件、查看文件状态、查看 chunks 空态、删除 indexed 文件时 chunks/Qdrant 失效、创建会话、搜索历史会话、打开历史会话、删除历史会话、SSE 流式发送消息、证据不足拒答、受限 fixture citation 演示、引用展示入口、trace 保存、helpful/unhelpful 反馈提交，以及历史会话 feedback 状态回显。Step 035 已补充前端验收 selector 和 `docs/demo/frontend-acceptance-checklist.md`。Step 016 已确认真实解析/索引端到端仍缺少必要外部条件：`MINERU_API_TOKEN` 未配置，Compose 中没有真实 embedding-service，本机 8200/8300 模型服务端口不可达。因此当前状态为“第一版基础 Web Demo 可操作，受限 Demo fixture 可演示 citation UI；真实带引用问答端到端仍需要外部服务后重新验收”。

Step 036 已完成第一版 Demo 交付审计与收口，并新增 `docs/demo/first-version-demo-acceptance-report.md`。当前状态更新为：“第一版基础 Web Demo 已完成并可交付演示；受限 Demo fixture 可演示 citation UI；完整 SDD v0.1 MVP 仍需要真实 MinerU、embedding-service、reranker-service、LLM 和真实样本文档端到端验收后才能宣称完成”。

Step 037 已修复 Codex 内置浏览器访问 `http://localhost:63166/login` 时可能出现的 `Failed to fetch` 问题：前端默认 API 地址改为同源 `/api/v1`，由 Vite `/api` proxy 转发到 Docker Compose 内的 `backend-api:8000`，并补充当前内置浏览器端口的 CORS 来源。

Step 038 已完成真实 MinerU API 文件解析验证链路的可观测性与失败隔离增强：文件状态接口会返回 parse_job `error_code` 与 `logs`，前端文件页可展示 MinerU 最新状态和 parsed-results 保存提示；MinerU 成功但缺少 `full_zip_url`、MinerU 返回 failed/error、提交阶段 token/上游错误都会写入明确错误日志；Dockerfile 默认 PyPI 源已切换为阿里云镜像。Step 044/045 已补齐真实 MinerU 配置并用用户上传 PDF 补跑在线解析，当前 MinerU 解析已验证通过。

Step 039 已完成真实 MinerU 产物标准化与 chunking 优化：Markdown 标题层级、表格块、JSON pages/blocks/tables/images、图片 OCR 区域、父级 page/sheet/row 上下文、heading_path 和 source_locator metadata 均已增强；chunking 从 `one_block_one_chunk` 升级为 `heading_aware_recursive`，支持同一标题路径下小段合并、表格/图片 OCR 边界保留、长文本递归切分和 overlap。Step 045 已用真实 MinerU zip 补跑标准化与 chunking，当前 PDF 生成 222 个 document_blocks 和 74 个 active chunks。

Step 040 已完成 API 化 embedding / reranker / LLM client 接入：新增 `EMBEDDING_API_BASE_URL`、`RERANKER_API_BASE_URL`、`LLM_API_BASE_URL`、API key、model 和 evidence gate 配置；embedding 支持 OpenAI-compatible `/embeddings` 与旧 `/embed` local service；reranker 支持 `/rerank` API；Chat 回答来源切换为 LLM client，并保留 template demo client 仅用于测试/演示。Step 044 已补齐真实模型配置，Step 045 已验证 Qwen embedding API 与 Qdrant 写入；真实 reranker/LLM 问答仍待补跑。

Step 041 已执行真实端到端验收前置检查和运行态 smoke：该步骤当时因缺少真实外部配置被标记为“需要人工确认”。Step 044/045 已解除解析与索引侧配置缺口，并完成用户真实 PDF 到 indexed 的补跑；完整带引用问答端到端仍需继续验证 reranker、LLM、citation、feedback 和 trace。

Step 042 已完成混合检索 RRF 策略补齐：Vector + Full-text 候选合并已升级为 RRF `k=60`，同一 chunk 多路命中标记为 `hybrid`，默认召回规模调整为 vector topK 50 / full-text topK 50，并只将 merged top 20 送入 reranker。该步骤已通过检索专项测试、后端全量测试、类型检查、lint/format 检查和前端构建验证；Step 041 的真实外部 API 配置缺口仍未解除。

Step 043 已完成多模态检索路由与图文召回基础骨架：新增 QueryRouter 多标签路由、LLM router 预留 prompt、text/image/video embedding provider 抽象、Qwen 多模态 embedding provider、ImageBlock/Evidence 数据结构、MultimodalRetriever 可注入骨架和 Weighted RRF evidence 融合。该步骤不改变现有 Chat/Retrieval 主链路，不新增数据库 migration，不执行真实 Qwen 在线调用；已通过 20 个新增目标测试、后端全量测试、lint、format 和 mypy 验证。

Step 044 已完成运行配置生效与 Demo 信息清理：当前 `.env` 已写入用户提供的真实 MinerU、embedding、reranker、LLM 和 Qwen 多模态配置，`DEMO_FIXTURE_ENABLED` 已关闭；`backend-api` 已重启并确认容器内真实配置生效；已删除运行数据中的 `Demo Fixture 知识库`、`demo_user`、`demo-rag-fixture.txt`、相关 chunks/Qdrant points/MinIO object/conversation/citation/trace/feedback；前端 Chat 页面可见的 `Demo 知识库` 硬编码名称和 Demo 描述已改为普通知识库创建文案。

Step 045 已完成 queued 解析自动提交、历史 smoke/readiness 知识库清理和当前真实 PDF 索引修复：文件状态轮询遇到 `queued` parse_job 时会自动提交 MinerU；运行数据库中仅保留用户知识库 `测试`；用户上传的 `1.井下落鱼可视化工具使用说明书_1.5.pdf` 已完成真实 MinerU 解析、222 个 document_blocks、74 个 active chunks、Qwen `qwen3-vl-embedding` 2560 维向量生成和 Qdrant 写入，文件状态为 `indexed`。本步骤还修复了 Qwen 多模态 embedding 在真实索引链路中的 provider 选择、embedding batch size 超限和重试索引成功后旧错误残留问题。

Step 046 已完成真实问答 reranker、知识库统计和顶部标题修复：DashScope/Qwen reranker 已从错误的 `/compatible-mode/v1/rerank` 适配为 text rerank endpoint，并兼容 `output.results[].relevance_score`；知识库列表/详情已返回真实 `file_count` 和 active `chunk_count`；默认顶部标题已从 `2024 年度财务报告知识库` 改为 `Agent-Assistant`。真实运行态 smoke 已验证 `测试` 知识库返回 `file_count=1/chunk_count=74`，Retrieval API 可召回真实 PDF chunks，新建 conversation 后提问可返回带引用回答，不再出现 reranker 上游错误。

Step 047 已完成 OpenSearch BM25 中文关键词召回 + IK Analyzer：新增 BM25 client 抽象、OpenSearch `chunks_bm25` mapping、IK 自定义词典配置、索引链路 BM25 upsert、Retrieval 关键词召回替换、删除 indexed 文件时 BM25 文档失效，以及 API/TDD 说明更新。目标后端测试、全量后端测试、ruff、black、mypy、Python 语法检查、Compose 配置、OpenSearch 服务启动、IK 插件检查、中文 analyzer、自定义词典、当前 `测试` 知识库 74 个 active chunks BM25 回填、Retrieval API、非流式 Chat、Chat SSE 和 trace smoke 均已通过。当前关键词召回链路已从 PostgreSQL `simple` full-text 升级为 OpenSearch BM25 + IK Analyzer，PostgreSQL full-text 保留为 `BM25_ENABLED=false` 时的 fallback。

Step 048 已完成文件解析/索引后台推进器：上传和重新解析创建 queued parse_job 后由后端后台任务唤醒推进；应用生命周期启动轻量 in-process worker，按间隔扫描 queued/parsing/normalizing/chunking/embedding 任务并推进；`GET /api/v1/files/{file_id}/status` 已恢复为只读查询，不再通过前端轮询触发 MinerU 提交、结果拉取、标准化、切片、embedding 或索引。当前实现不是独立队列系统，但已把推进职责从状态接口中移出，为后续替换为独立 worker/queue 预留边界。

Step 049 已完成文档结构化摘要、并发 Chunk 抽取与历史回填：新增独立摘要表和 worker，复用现有 OpenAI-compatible LLM/vLLM 配置，默认同时处理 2 篇文档、每篇 8 个 Chunk、全局 16 个模型请求；严格校验 JSON schema 与 evidence 原文片段，按 chunk_index 归并并支持超长文档分层摘要、部分完成、断点恢复、Admin 查询/重试 API 和文件管理页摘要抽屉。当前运行数据库 18 个未删除文件已完成任务初始化，其中 16 个有 active chunks 的文档进入可恢复回填，2 个无 active chunks 的文档标记为 not_ready。

Step 050 已完成知识地图、跨知识库文件关联与社区摘要：当前文档摘要通过现有 Embedding 服务生成文档级向量，按余弦相似度、阈值和 Top-K 维护同库及跨库关系；全局图谱和每个知识库社区摘要使用摘要集合指纹自动更新；普通用户与管理员均可访问知识地图页面，管理员额外可刷新关系或强制重算向量。该能力独立于现有 Retrieval/Chat 主链路。

## 步骤列表

| Step | 名称 | 状态 | 对应进度文件 | 说明 |
|---|---|---|---|---|
| 001 | Phase 0 基础补齐与进度体系初始化 | 已完成 | docs/progress/step-001-phase-0-foundation.md | Alembic/SQLAlchemy 基础、进度文件、后端构建、migration 和测试验证均已完成 |
| 002 | Phase 1-A 用户数据模型与迁移 | 已完成 | docs/progress/step-002-user-models.md | 已创建 users/user_profiles 模型、枚举、migration 和基础测试 |
| 003 | Phase 1-B 认证基础能力 | 已完成 | docs/progress/step-003-auth-basics.md | 已实现 bcrypt、默认 Admin、JWT access/refresh、login、refresh、auth/me |
| 004 | Phase 1-C 用户管理与 RBAC 权限边界 | 已完成 | docs/progress/step-004-users-rbac.md | 已实现 Admin-only 用户列表/创建/更新/禁用/启用/重置密码和权限测试 |
| 005 | Phase 1-D Refresh Token Logout/Revoke | 已完成 | docs/progress/step-005-refresh-token-revoke.md | 已实现 logout 后 refresh token 不可复用，完成 TDD-AUTH-008 |
| 006 | Phase 2-A 知识库模型、CRUD 与审计基础 | 已完成 | docs/progress/step-006-knowledge-bases-audit.md | 已实现 knowledge_bases/audit_logs、知识库 CRUD、软删除、审计写入和审计查询 |
| 007 | Phase 2-B 文件模型、上传校验与 MinIO raw-files 基础 | 已完成 | docs/progress/step-007-files-upload-minio.md | 已实现 files/parse_jobs、文件上传校验、MinIO raw-files、hash 去重、文件状态/列表、软删除和审计 |
| 008 | Phase 3-A MinerU API client 与 parse_job 提交/轮询基础 | 已完成 | docs/progress/step-008-mineru-api-client.md | 已实现 MinerU API client、retry-parse 提交、status 轮询、parsed-results 保存；真实 MinerU 在线验证需配置 token |
| 009 | Phase 3-B document_blocks 与 MinerU 解析产物标准化 | 已完成 | docs/progress/step-009-document-blocks-normalization.md | 已实现 document_blocks、MinerU zip Markdown/JSON 标准化、normalizing 到 chunking 状态推进和 blocks 调试视图 |
| 010 | Phase 3-C chunks_metadata 与基础 chunking | 已完成 | docs/progress/step-010-chunks-metadata.md | 已实现 chunks_metadata、从 document_blocks 生成 active chunks、source_locator/content_hash/token_count、旧 chunks 失效和 chunking 到 embedding 状态推进 |
| 011 | Phase 4-A embedding-service 与 Qdrant 索引基础 | 已完成 | docs/progress/step-011-embedding-qdrant-indexing.md | 已实现 embedding client、Qdrant client、indexing 编排、Qdrant payload、tsv 写入和 embedding 到 indexed 状态推进 |
| 012 | Phase 5-A 检索基础 API | 已完成 | docs/progress/step-012-retrieval-basic-api.md | 已实现 Retrieval API、query embedding、Qdrant vector search、PostgreSQL/full-text search、结果合并去重和知识库过滤防护 |
| 013 | Phase 6-A conversation/message/trace 基础与非流式 Chat Demo | 已完成 | docs/progress/step-013-non-stream-chat-demo.md | 已实现 conversations/messages/citations/traces、非流式消息接口、模板化回答/拒答、引用与 trace 保存、用户会话隔离 |
| 014 | 前端 Chat Demo 真实接口联调 | 已完成 | docs/progress/step-014-frontend-chat-demo.md | 已实现真实登录、知识库加载/创建、conversation 列表/创建/详情、非流式消息发送、assistant answer 与 citation 展示 |
| 015 | 前端文件上传与解析状态联调 | 已完成 | docs/progress/step-015-frontend-files-status.md | 已实现真实文件列表、multipart 上传、Hash 重复强制上传、状态刷新、重新解析、删除和真实 chunks 调试页 |
| 016 | 真实解析索引端到端可用性确认 | 需要人工确认 | docs/progress/step-016-real-e2e-readiness.md | 已确认 MinerU API token 未配置且真实 embedding-service 不存在，真实带引用问答端到端暂不能执行 |
| 017 | 前端知识库管理页面真实接口联调 | 已完成 | docs/progress/step-017-frontend-knowledge-bases.md | 已实现真实知识库列表、keyword/status 查询、创建、编辑、软删除和管理入口 |
| 018 | 前端用户管理与审计日志页面真实接口联调 | 已完成 | docs/progress/step-018-frontend-users-audit.md | 已实现真实用户列表/筛选/创建/编辑/启用禁用/重置密码，以及真实审计日志列表/筛选/详情 |
| 019 | Profile/Auth 状态与导航展示真实化 | 已完成 | docs/progress/step-019-profile-auth-state.md | 已实现 AppLayout 当前用户真实展示、logout、Profile 真实 `/auth/me` 展示 |
| 020 | Helpful/Unhelpful 反馈基础能力 | 已完成 | docs/progress/step-020-feedback-basics.md | 已实现 feedback 表、message feedback API、telemetry 保存、Chat 页面 helpful/unhelpful 按钮 |
| 021 | Chat SSE 流式 Demo | 已完成 | docs/progress/step-021-sse-chat-demo.md | 已实现 `stream=true` SSE、message_created/retrieval/token/done 事件和前端流式渲染 |
| 022 | Reranker Client 与检索重排基础 | 已完成 | docs/progress/step-022-reranker-client-basic.md | 已实现 reranker client 抽象、Retrieval/Chat 接入、trace/feedback reranker_model 保存和 fake reranker 排序测试 |
| 023 | 第一版 Demo 运行说明与验收边界整理 | 已完成 | docs/progress/step-023-demo-runbook-boundary.md | 已新增 Demo 运行说明、SDD MVP 验收矩阵、README 当前状态入口和外部依赖缺口说明 |
| 024 | API Contract / OpenAPI / 前端类型一致性核对 | 已完成 | docs/progress/step-024-api-contract-sync.md | 已同步 Retrieval reranker、Chat SSE、Feedback telemetry、Profile 当前边界和前端 Feedback 类型 |
| 025 | TDD 文档与当前实现差异核对 | 已完成 | docs/progress/step-025-tdd-current-state-sync.md | 已同步 TDD 当前 Demo 状态、完整 MVP 缺口、测试环境边界和关键未完成用例 |
| 026 | 补齐 message trace 中的 reranker_scores | 已完成 | docs/progress/step-026-reranker-scores-trace.md | 已将 Chat trace 写入 reranked_chunk_ids 和 `{chunk_id: score}` 形式 reranker_scores，并通过后端测试验证 |
| 027 | 当前用户删除自己 conversation 接口 | 已完成 | docs/progress/step-027-conversation-delete-api.md | 已实现 `DELETE /api/v1/conversations/{conversation_id}` 软删除、权限边界和后端测试 |
| 028 | 前端 Chat 历史会话删除交互 | 已完成 | docs/progress/step-028-frontend-conversation-delete.md | 已在 Chat 历史会话列表接入删除按钮、确认框、真实 DELETE API 调用和删除后状态切换 |
| 029 | Chat 历史会话搜索过滤 | 已完成 | docs/progress/step-029-chat-conversation-search.md | 已将历史会话搜索输入框接入本地标题过滤、清空按钮和无结果空态 |
| 030 | Chat 历史消息回显 feedback 状态 | 已完成 | docs/progress/step-030-chat-feedback-state-hydration.md | 已在 conversation detail 返回 `feedback_rating`，并在前端打开历史会话时回显 helpful/unhelpful 按钮状态 |
| 031 | 用户管理操作审计日志写入 | 已完成 | docs/progress/step-031-users-audit-logs.md | 已为用户创建/更新/禁用/启用/重置密码写入 audit_logs，并验证不记录密码 |
| 032 | 审计日志前端可读操作文案 | 已完成 | docs/progress/step-032-audit-action-labels.md | 已将常见知识库、文件和用户管理审计 action/resource_type 展示为中文文案，并保留原始 code |
| 033 | indexed 文件删除时 chunks/Qdrant 失效闭环 | 已完成 | docs/progress/step-033-indexed-file-delete-invalidation.md | 已实现删除 indexed 文件时 active chunks 置为 inactive，并将 Qdrant points payload `is_active=false` |
| 034 | 受限 Demo fixture/seed 引用演示路线 | 已完成 | docs/progress/step-034-demo-fixture-citation-seed.md | 已新增开发/演示 seed、local demo embedding/reranker，并通过真实 API smoke 验证 citation 返回 |
| 035 | 第一版 Demo 前端验收固化 | 已完成 | docs/progress/step-035-frontend-demo-acceptance.md | 已新增 Chat 页面稳定 selector 和前端验收清单，并通过 lint/typecheck/build 与真实 API citation+feedback smoke |
| 036 | 第一版 Demo 交付审计与收口 | 已完成 | docs/progress/step-036-demo-delivery-audit.md | 已新增交付验收报告，明确第一版 Demo 可交付边界、SDD 对照矩阵、MinerU API 调用方式和真实外部服务缺口 |
| 037 | 内置浏览器 API 代理与 Failed to fetch 修复 | 已完成 | docs/progress/step-037-in-app-browser-api-proxy.md | 已将前端默认 API 改为同源 `/api/v1` 并通过 Vite proxy 转发后端，修复内置浏览器临时端口下的 API 访问失败 |
| 038 | 真实 MinerU API 文件解析验证 | 已完成 | docs/progress/step-038-real-mineru-api-parse-validation.md | 已增强 MinerU API parse_job 状态、错误日志、parsed-results 保存记录和前端状态展示；真实在线样本解析仍需配置 token 后补跑 |
| 039 | 真实 MinerU 产物标准化与 chunking 优化 | 已完成 | docs/progress/step-039-mineru-normalization-chunking.md | 已增强 Markdown/JSON/assets 元数据标准化、heading_path/source_locator 生成和 heading-aware recursive chunking |
| 040 | API 化 embedding / reranker / LLM 接入 | 已完成 | docs/progress/step-040-api-model-clients.md | 已新增可配置 embedding/reranker/LLM API client、Chat LLM 生成、trace 模型元数据和 evidence gate |
| 041 | 真实端到端验收 | 需要人工确认 | docs/progress/step-041-real-e2e-acceptance.md | 原步骤因缺少真实配置被标记为需要人工确认；Step 045 已完成真实解析/索引补跑，真实问答仍待验收 |
| 042 | 混合检索 RRF 策略补齐 | 已完成 | docs/progress/step-042-rrf-hybrid-retrieval.md | 已将 Vector + Full-text 合并升级为 RRF k=60，默认 50/50 召回并将 merged top 20 送入 reranker |
| 043 | 多模态检索路由与图文召回基础骨架 | 已完成 | docs/progress/step-043-multimodal-query-router-foundation.md | 已新增 QueryRouter、Qwen 多模态 embedding provider 抽象、ImageBlock/Evidence、MultimodalRetriever 和 Weighted RRF 测试骨架 |
| 044 | 运行配置生效与 Demo 信息清理 | 已完成 | docs/progress/step-044-runtime-config-demo-cleanup.md | 已重启后端并确认真实配置生效，关闭 Demo fixture，清理 Demo fixture 运行数据和前端可见 Demo 文案 |
| 045 | Queued 解析自动提交与真实文件索引修复 | 已完成 | docs/progress/step-045-auto-submit-queued-parse-and-runtime-indexing.md | 已修复上传文件停留 queued、清理历史测试知识库、完成用户真实 PDF 到 indexed 的运行态修复 |
| 046 | 真实问答 Reranker、知识库统计与顶部标题修复 | 已完成 | docs/progress/step-046-reranker-kb-stats-and-ui-title-fixes.md | 已修复 DashScope/Qwen reranker API 契约、知识库文件/chunk 统计和顶部硬编码标题 |
| 047 | OpenSearch BM25 中文关键词召回 + IK Analyzer | 已完成 | docs/progress/step-047-opensearch-bm25-ik-retrieval.md | 已完成 OpenSearch + IK Analyzer 启动、74 个真实 active chunks 回填、中文 analyzer 验证、Retrieval/Chat/SSE/trace smoke 和自动化测试 |
| 048 | 文件解析/索引后台推进器 | 已完成 | docs/progress/step-048-backend-parse-job-worker.md | 已将 parse_job 推进从状态接口轮询中移出，上传/重试后由后端后台任务和轻量 worker 推进 |
| 049 | 文档结构化摘要、并发 Chunk 抽取与历史回填 | 已完成 | docs/progress/step-049-document-structured-summaries.md | 已实现严格结构化抽取、单文档 8 路/全局 16 路并发、分层文档摘要、独立状态、Admin API/UI 和 3,408 个历史 Chunk 回填任务 |
| 050 | 知识地图、跨知识库文件关联与社区摘要 | 已完成 | docs/progress/step-050-knowledge-map-community-summaries.md | 已实现文档摘要向量缓存、余弦 Top-K 关系、跨知识库边、社区摘要自动更新和用户/Admin 知识地图 |

## 已完成内容

- 已阅读并确认 `docs/specs/SDD.v0.1.md` 为唯一需求来源。
- 已确认当前仓库 README 声明项目处于 Phase 0。
- 已新增后端数据库基础模块。
- 已新增 Alembic 配置、迁移环境和 Phase 0 最小迁移。
- 已更新后端 Docker 构建与 Compose 挂载，确保容器内可访问 Alembic 配置和 migrations。
- 已新增开发进度总览和 Step 001 进度文件。
- 已执行 Docker Compose 配置验证、Python 3.11 依赖安装、后端镜像构建、Alembic migration、容器内 pytest 和 health 检查。
- 已新增 `users` 与 `user_profiles` SQLAlchemy 模型。
- 已新增用户角色/状态枚举：`admin/user`、`active/disabled`。
- 已新增 `0002_users_profiles` migration，并在 PostgreSQL 中执行成功。
- 已新增模型元数据测试，验证核心字段、唯一约束、检查约束和外键约束。
- 已新增 bcrypt 密码哈希与校验。
- 已新增 JWT access token 与 refresh token。
- 已新增默认 Admin 初始化逻辑。
- 已新增 `POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`。
- 已实现登录失败计数，连续 5 次失败锁定账号 15 分钟。
- 已实现 disabled 用户登录拒绝。
- 已新增统一业务错误响应 envelope 基础。
- 已新增 Admin-only RBAC dependency。
- 已新增 `GET /api/v1/users`、`POST /api/v1/users`、`PATCH /api/v1/users/{user_id}`。
- 已新增 `POST /api/v1/users/{user_id}/disable`、`enable`、`reset-password`。
- 已验证普通 User 访问 Admin API 返回 `403 FORBIDDEN`。
- 已同步 UserCreateRequest 的 `email` 字段到 API contract、OpenAPI、前端类型和 TDD 说明。
- 已新增 `revoked_refresh_tokens` 表和 migration。
- 已新增 refresh token `jti`，并实现 `POST /api/v1/auth/logout` 吊销 refresh token。
- 已验证 logout 后复用 refresh token 返回 `401 UNAUTHORIZED`。
- 已新增 `knowledge_bases` 与 `audit_logs` 表和 migration。
- 已新增 `GET/POST/GET by id/PATCH/DELETE /api/v1/knowledge-bases`。
- 已新增 `GET /api/v1/audit-logs`。
- 已实现 Admin-only 知识库创建、更新、删除和审计查询。
- 已实现 User 只读 active 知识库，User 访问非 active 知识库返回 `404 RESOURCE_NOT_FOUND`。
- 已实现知识库软删除，删除后默认列表隐藏，Admin 可按 `status=deleted` 查询。
- 已实现创建、更新、删除知识库写入 audit_logs。
- 已将知识库状态枚举按 SDD 统一为 `active/deleting/deleted`。
- 已完成后端本地检查、前端类型检查、Docker 构建、migration、容器内测试和 API smoke 验证。
- 已新增 `files` 与 `parse_jobs` 表和 migration。
- 已新增 `GET /api/v1/knowledge-bases/{knowledge_base_id}/files`。
- 已新增 `POST /api/v1/knowledge-bases/{knowledge_base_id}/files/upload`。
- 已新增 `GET /api/v1/files/{file_id}`、`GET /api/v1/files/{file_id}/status`、`DELETE /api/v1/files/{file_id}`。
- 已实现 Admin-only 文件上传、User 禁止上传。
- 已实现知识库 active 状态校验、大小/数量/扩展名校验、SHA-256 hash 计算、同名拒绝、hash 重复 warning 和 force 上传。
- 已实现 MinIO `raw-files` 原始文件保存，并在对象 metadata 中写入 file_id、knowledge_base_id 和 file_hash。
- 已实现上传成功后创建 queued file 与 queued parse_job。
- 已实现文件软删除和 `upload_file`、`delete_file` 审计写入。
- 已将 FileStatus 按 SDD 统一为 `uploaded/queued/processing/indexed/partially_indexed/failed/deleting/deleted`。
- 已完成真实 MinIO 上传 smoke 验证，确认 raw-files 对象存在。
- 已新增 MinerU API client，采用 API 调用方式，参考 MinerU v4 batch upload/result API。
- 已实现 `POST /api/v1/files/{file_id}/retry-parse` 创建新 parse_job 并提交 MinerU。
- 已实现 `GET /api/v1/files/{file_id}/status` 在 latest parse_job 为 parsing 时轮询 MinerU batch result。
- 已实现 MinerU 成功后下载 `full_zip_url` 并保存到 MinIO `parsed-results`。
- 已将 MinerU batch_id、data_id、latest result 和 parsed result location 写入 `parse_jobs.logs`。
- 已验证 MinerU fake submit/poll 成功与失败路径。
- 已验证未配置 `MINERU_API_TOKEN` 时返回明确的 `UPSTREAM_SERVICE_ERROR`。
- 已扩展文件状态接口返回 parse_job `error_code` 与 `logs`，前端文件页可展示 MinerU 最新状态、错误码和 parsed-results 保存提示。
- 已补强 MinerU API 失败隔离：pending/running 保持 parsing，failed/error 写入 `MINERU_PARSE_FAILED`，成功但缺 `full_zip_url` 写入 `MINERU_RESULT_MISSING`，提交阶段上游错误写入 `MINERU_SUBMIT_FAILED`。
- 已将后端 Dockerfile 默认 PyPI 源切换为阿里云镜像，后续容器构建会默认使用 `https://mirrors.aliyun.com/pypi/simple/`。
- 已新增 `document_blocks` 表和 migration。
- 已实现从 MinIO `parsed-results` 读取 MinerU zip。
- 已实现 Markdown/JSON 解析产物标准化写入 document_blocks。
- 已实现 parse_job 从 `normalizing` 推进到 `chunking`。
- 已实现 `GET /api/v1/files/{file_id}/chunks` 的 block-backed 调试视图。
- 已完成真实标准化 smoke，确认 document_blocks 可通过调试接口查看。
- 已新增 `chunks_metadata` 表和 migration。
- 已新增 `ChunkMetadata` SQLAlchemy 模型。
- 已实现从 `document_blocks` 生成 active chunks。
- 已实现 chunk 基础 `source_locator`、`content_hash`、`token_count` 和定位字段写入。
- 已实现重新解析时旧 active chunks 标记为 inactive。
- 已实现 parse_job 从 `chunking` 推进到 `embedding`，progress 推进到 `60`。
- 已将 chunking 策略升级为 `heading_aware_recursive`，支持 heading_path 下小段合并、表格/图片 OCR 边界保留、长文本递归切分和 overlap。
- 已增强 MinerU Markdown/JSON 标准化，支持 heading 层级、Markdown table、JSON pages/blocks/tables/images、父级 page/sheet/row 上下文、source_locator 和 asset path metadata。
- 已将 `GET /api/v1/files/{file_id}/chunks` 切换为读取真实 active chunks。
- 已完成本地后端格式/lint/typecheck/pytest、前端 typecheck、后端 Docker 构建、容器内 migration、PostgreSQL 表结构检查、容器内 pytest 和后端启动健康检查。
- 已新增 embedding-service HTTP client 抽象。
- 已新增 Qdrant HTTP client 抽象。
- 已实现 parse_job 从 `embedding -> indexing -> indexed` 推进，file 状态推进到 `indexed`。
- 已实现 active chunks embedding 请求、Qdrant collection 初始化、Qdrant points 写入和 SDD 核心 payload 构造。
- 已实现 `chunks_metadata.tsv` 基础写入。
- 已通过 fake embedding/Qdrant 测试验证 4 个 chunks 的索引闭环。
- 已通过真实 Qdrant smoke 验证 collection 初始化和 point upsert。
- 已通过镜像源补齐 Qdrant、Redis、Node 镜像，并完成完整 `docker compose up -d` 启动验证。
- 已新增 `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval/search`。
- 已实现 query embedding、Qdrant vector search、PostgreSQL/full-text search、结果合并和 chunk_id 去重。
- 已将 Vector + Full-text 候选合并从简单分数相加升级为 RRF `k=60`，默认召回规模调整为 50/50，并限制 merged top 20 进入 reranker。
- 已新增多模态 QueryRouter，可按问题启用 text/table/image/metadata 多标签路由。
- 已新增 text/image/video embedding provider 抽象和 Qwen 多模态 embedding provider，Qwen 调用封装在 provider 内。
- 已新增 ImageBlock/Evidence 数据结构、MultimodalRetriever 可注入骨架和 Weighted RRF evidence 融合。
- 已将当前运行环境切换到用户提供的真实 MinerU、embedding、reranker、LLM、Qwen 配置，并重启后端确认生效。
- 已关闭 `DEMO_FIXTURE_ENABLED`，删除运行数据中的 Demo fixture 知识库、demo 用户、demo 文件、Demo chunks/Qdrant points/MinIO object 和相关会话数据。
- 已移除前端 Chat 页面可见的 `Demo 知识库` 硬编码名称和 Demo 描述。
- 已修复上传文件后 latest parse_job 长期停留 `queued` 的问题：文件状态轮询会自动提交 MinerU 并推进到 `parsing`。
- 已清理运行数据库中的历史 Step smoke/readiness 测试知识库，当前知识库列表仅保留用户创建的 `测试`。
- 已完成用户真实 PDF 的 MinerU 在线解析、parsed-results 保存、document_blocks 标准化、chunks 生成、Qwen embedding 和 Qdrant 索引，当前文件状态为 `indexed`。
- 已将 Qwen 多模态 embedding provider 接入真实 text chunk 索引链路，并按 `EMBEDDING_BATCH_SIZE=16` 分批请求，满足 DashScope text batch 最大 20 条限制。
- 已重建旧 Demo fixture 遗留的 2 维 Qdrant `chunks` collection，当前 `chunks` collection 为 Qwen 2560 维且包含 74 个真实 points。
- 已将 DashScope/Qwen reranker 接入真实 text rerank endpoint，修复 Chat/Retrieval 中 `UPSTREAM_SERVICE_ERROR: Reranker API request failed.`。
- 已验证当前真实 PDF 的 Retrieval API 和非流式 Chat API 可返回真实 chunks、LLM 回答和 citations。
- 已修复知识库列表/详情统计，`测试` 知识库当前返回 1 个文件、74 个 chunks。
- 已将默认顶部标题从 `2024 年度财务报告知识库` 改为 `Agent-Assistant`。
- 已新增 API 化 embedding client，配置 `EMBEDDING_API_BASE_URL` 后可请求 OpenAI-compatible `/embeddings`，未配置时保留旧 local service `/embed` 契约。
- 已实现 Qdrant search 请求强制携带 `knowledge_base_id` 与 `is_active=true` filter。
- 已实现加载 chunk 详情时再次按 `knowledge_base_id` 过滤，防止跨知识库污染。
- 已同步 Retrieval API 到文字 API contract、OpenAPI 和前端类型。
- 已新增检索测试，验证 hybrid/full_text 来源、跨知识库 chunk 不返回、inactive knowledge base 返回 404。
- 已新增 `conversations`、`messages`、`message_citations`、`message_traces` 表和 migration。
- 已新增 `GET/POST /api/v1/conversations`、`GET /api/v1/conversations/{conversation_id}`。
- 已新增 `POST /api/v1/conversations/{conversation_id}/messages` 非流式 demo 响应。
- 已实现模板化 assistant answer、证据不足拒答模板、citations 保存和 message_trace 保存。
- 已新增 API 化 LLM client，Chat 有最终上下文时通过 LLM client 生成回答；未配置真实 LLM API 时使用明确标记的 template demo client。
- 已新增配置化 evidence gate，配置 `EVIDENCE_MIN_RERANKER_SCORE` 后低于阈值会拒答且不调用 LLM。
- 已验证用户只能访问自己的 conversation。
- 已同步非流式 Chat Demo 到文字 API contract、OpenAPI 和前端类型。
- 已新增前端真实 API client；Step 037 已将默认 API 地址改为同源 `/api/v1`，并继续支持 `VITE_API_BASE_URL` 覆盖。
- 已将登录页接入真实 Auth API，支持默认 Admin 登录、保存 token 和跳转 Chat 页面。
- 已将 Chat 页面接入真实 KnowledgeBase 与 Conversations API。
- 已支持在 Chat 页面创建知识库、创建 conversation、打开历史 conversation、发送 `stream=false` 消息。
- 已在 Chat 页面展示 assistant answer、citation chips 和 citation detail。
- 已补充空知识库无 active indexed chunks 时 retrieval 直接返回空结果的保护，保障 Demo 拒答路径不依赖真实 embedding-service。
- 已完成 Step 014 本地后端格式/lint/typecheck/pytest、前端 typecheck/build、运行服务健康检查和真实接口 smoke 验证。
- 已扩展前端 API client，支持 Files/Chunks API、multipart 上传和后端 error details 保留。
- 已将文件管理页接入真实 Files API，支持知识库切换、文件列表、keyword/status 查询、上传、Hash 重复强制上传、刷新状态、重新解析、删除和 Chunk 跳转。
- 已将 Chunk 调试页接入真实文件详情、文件状态和 active chunks API。
- 已通过真实接口 smoke 验证登录、创建知识库、上传 txt、查询文件列表、查询状态和查询 chunks。
- 已完成 Step 015 前端 typecheck/build、后端 pytest、运行服务健康检查和 Compose 服务状态检查。
- 已重新确认 MinerU 解析阶段按用户要求采用 API 调用方式。
- 已检查当前环境真实端到端依赖：MinerU token 未配置、Compose 无 embedding-service、本机 8200/8300 不可达、Qdrant 可用但 collections 为空。
- 已创建 Step 016 进度文件，将真实解析索引端到端标记为“需要人工确认”。
- 已扩展前端 API client，支持 KnowledgeBase keyword/status 列表查询、编辑和删除。
- 已将 KnowledgeBases 页面接入真实 KnowledgeBase API，支持查询、创建、编辑和软删除。
- 已移除知识库页面中 SDD 未规定的“外部数据源实时同步 / 自动化向量更新”展示。
- 已通过真实接口 smoke 验证知识库创建、更新、active 查询、软删除和 deleted 查询。
- 已扩展前端 API client，支持 Users API 和 Audit Logs API。
- 已将 Users 页面接入真实用户列表、筛选、新建、编辑、禁用/启用和重置密码接口。
- 已将 AuditLogs 页面接入真实审计日志列表、筛选和详情展示接口。
- 已通过真实接口 smoke 验证用户创建、更新、禁用、启用、重置密码、用户列表和审计日志查询。
- 已扩展前端 API client，支持 `/auth/me`、`/auth/logout` 和 refresh token 读取。
- 已将 AppLayout 当前用户、侧边栏头像、role 和顶部当前用户显示切换为真实 `/auth/me` 数据。
- 已将退出登录接入真实后端 logout，并在本地清理 token。
- 已将 Profile 页面切换为真实当前用户只读展示。
- 已通过真实接口 smoke 验证登录、`/auth/me`、logout 和 logout 后 refresh token 不可复用。
- 已新增 `feedback` 表和 `0009_create_feedback` migration。
- 已新增 `POST /api/v1/messages/{message_id}/feedback`。
- 已实现同一用户对同一 assistant message 的 feedback upsert。
- 已实现 feedback telemetry 保存：query_text、retrieved_chunk_ids、final_cited_chunk_ids、model/prompt/embedding/reranker 信息。
- 已在 Chat 页面为 assistant message 增加 helpful/unhelpful 反馈按钮。
- 已通过真实接口 smoke 验证 helpful 提交和 unhelpful 更新。
- 已实现 `POST /api/v1/conversations/{conversation_id}/messages` 的 `stream=true` SSE 分支。
- 已新增 SSE events：`message_created`、`retrieval`、`token`、`done`。
- 已将前端 Chat 页面发送消息切换为 POST SSE 流式渲染。
- 已通过真实接口 smoke 验证 SSE 返回 `text/event-stream`，并包含 `message_created`、`token`、`done` 和空知识库拒答文本。
- 已新增 reranker-service HTTP client 抽象，默认调用 `POST /rerank`。
- 已新增 `reranker_service_url` 与 `reranker_model` 配置项。
- 已将 reranker 接入 Retrieval API 的 vector/full-text merge 后重排路径。
- 已将 reranker 接入 Chat message 检索路径，并在 trace/feedback telemetry 中保存 `reranker_model`。
- 已新增 fake reranker 排序测试，验证 reranker score 会改变 Retrieval API 返回顺序。
- 已完成 Step 022 后端格式/lint/typecheck/pytest、Compose 配置、运行服务状态、后端健康检查和前端运行检查。
- 已新增 `docs/demo/first-version-demo.md`，记录第一版 Demo 启动方式、默认 Admin、可演示流程、SDD MVP 验收矩阵和当前不能验收为完整 MVP 的原因。
- 已更新根 README，将过期 Phase 0 描述调整为第一版 Web Demo 阶段，并指向 Demo 文档。
- 已完成 Step 023 文档存在性、README 入口、进度索引、SDD 边界关键词、Compose 配置、运行服务状态、后端健康检查和前端访问检查。
- 已同步 `docs/api/frontend-backend-api-contract.md` 中 Retrieval reranker、Chat SSE、Feedback telemetry 和 Profile 当前边界。
- 已同步 `docs/api/openapi.v0.1.yaml` 中 message SSE response、Feedback schema，并移除当前未实现的 `/users/me/profile` active path/schema。
- 已同步 `frontend/src/api/types.ts` 中 Feedback response 类型，并移除当前未实现的 profile 类型。
- 已完成 Step 024 旧契约关键字扫描、OpenAPI YAML 解析、前端 typecheck 和前端 build。
- 已更新 `docs/tests/TDD.v0.1.md`，新增当前实现与测试状态、当前基础 Demo Compose 栈、完整 MVP 未解除缺口、第一版基础 Web Demo 可操作验收门槛和关键 TDD 用例当前状态。
- 已更新 `docs/tests/README.md`，增加 Demo 运行说明和进度总览入口。
- 已完成 Step 025 文档存在性、过期描述扫描、新状态关键字扫描、Compose 配置、运行服务状态和后端健康检查验证。
- 已将 Chat assistant message trace 的 `reranked_chunk_ids` 从 `None` 补齐为重排后的 chunk id 顺序。
- 已将 Chat assistant message trace 的 `reranker_scores` 补齐为 `{chunk_id: score}` 结构。
- 已扩展 conversation API fake reranker 测试，验证固定 reranker score 能写入 trace。
- 已完成 Step 026 目标测试、black、ruff、mypy、完整后端 pytest、Compose 配置、运行服务状态和后端健康检查验证。
- 已新增 `DELETE /api/v1/conversations/{conversation_id}`。
- 已实现当前用户软删除自己的 conversation，删除后列表和详情默认不可见。
- 已验证其他用户删除不属于自己的 conversation 返回 `404 RESOURCE_NOT_FOUND`。
- 已更新 TDD 中 `TDD-CONV-003` 当前状态，标记删除会话基础测试已实现。
- 已完成 Step 027 目标测试、black、ruff、mypy、完整后端 pytest、Compose 配置、运行服务状态和后端健康检查验证。
- 已在前端 API client 中新增 `deleteConversation()`。
- 已在 Chat 历史会话列表中新增删除按钮和确认框。
- 已实现删除成功后从列表移除会话；删除当前会话时自动切换到下一条或清空消息区。
- 已更新 `docs/demo/first-version-demo.md`，补充历史会话删除可演示流程和软删除边界。
- 已完成 Step 028 前端 typecheck、前端 build、前端访问检查、后端健康检查、运行服务检查和真实删除会话接口 smoke 验证。
- 已将 Chat 页面历史会话搜索输入框接入 `v-model` 和 clearable 清空按钮。
- 已新增 `filteredConversations`，按会话标题进行本地过滤。
- 已新增“暂无历史会话”和“没有匹配会话”空态。
- 已处理切换知识库、新建会话、创建知识库和删除当前会话时的搜索词/可见会话边界。
- 已更新 `docs/demo/first-version-demo.md`，补充历史会话搜索可演示流程。
- 已完成 Step 029 前端 typecheck、前端 build、前端访问检查、后端健康检查、运行服务检查和源码关键字扫描。
- 已在 `MessageResponse` 中新增 `feedback_rating` 字段。
- 已在 conversation detail 中按当前用户批量加载 messages 的 feedback rating。
- 已在前端 Chat 打开历史 conversation 时同步 helpful/unhelpful 按钮状态。
- 已在提交 feedback 成功后同步更新当前 message 的 `feedback_rating`。
- 已同步 API contract、OpenAPI 和前端 Message 类型。
- 已更新 Demo/TDD 当前状态，补充历史会话 feedback 状态回显。
- 已完成 Step 030 目标测试、black、ruff、mypy、完整后端 pytest、前端 typecheck/build、OpenAPI YAML 解析、运行服务检查和源码关键字扫描。
- 已为 Users API 的创建、更新、禁用、启用和重置密码操作写入 audit_logs。
- 已记录用户管理操作前后快照，重置密码仅记录 `password_changed=true`，不记录明文密码或 password hash。
- 已更新 TDD 和 Demo 文档，标记用户管理审计已实现。
- 已完成 Step 031 目标测试、black、ruff、mypy、完整后端 pytest、后端健康检查和运行服务检查。
- 已将审计日志页面常见 action/resource_type 从原始英文枚举展示为中文文案，同时保留原始 code 便于排查。
- 已完成 Step 032 前端 typecheck、前端 build、前端访问检查、后端健康检查、运行服务检查和源码关键字扫描。
- 已实现删除 indexed 文件时 Qdrant points payload `is_active=false`，并将该文件 active chunks 标记为 inactive。
- 已扩展删除文件审计 details，记录 inactive chunk 数量、Qdrant 失效 point 数量和 collection。
- 已完成 Step 033 目标测试、black、ruff、mypy、完整后端 pytest、Compose 配置、migration 状态、后端健康检查、运行服务检查、后端镜像构建和源码关键字扫描。
- 已新增 `DEMO_FIXTURE_ENABLED` 开发/演示开关，默认关闭；当前本地 `.env` 已打开用于第一版 Demo 演示。
- 已新增受限 Demo fixture seed 命令 `python -m app.dev.seed_demo_fixture`。
- 已生成 `Demo Fixture 知识库`、`demo-rag-fixture.txt`、`demo_user`、indexed parse_job、3 个 active chunks、Qdrant points 和 MinIO raw file object。
- 已新增 local demo embedding/reranker，仅在 `DEMO_FIXTURE_ENABLED=true` 时使用。
- 已通过真实 HTTP API smoke 验证 `demo_user` 发送推荐问题后 assistant answer 包含 `[1]`，并返回 file_name/source_locator/excerpt/chunk_id citation。
- 已完成 Step 034 新增测试、black、ruff、mypy、完整后端 pytest、Compose 配置、seed、真实 API citation smoke、migration 状态、后端健康检查、前端访问检查、运行服务检查、后端镜像构建、前端 typecheck/build 和源码关键字扫描。
- 已新增 Chat 页面稳定 `data-testid` selector，覆盖知识库选择、会话、消息、citation、引用详情和 feedback 按钮。
- 已新增 `docs/demo/frontend-acceptance-checklist.md`，固化 `demo_user` 前端 citation/feedback 验收流程。
- 已优化 Chat 页面刷新 conversation list 后保留当前 active conversation，提高发送消息后的验收稳定性。
- 已完成 Step 035 前端 lint、typecheck、build、运行服务检查、后端健康检查、前端访问检查、真实 API citation+feedback smoke 和 selector 文档扫描。
- 已新增 `docs/demo/first-version-demo-acceptance-report.md`，完成第一版 Demo 交付审计与收口。
- 已对照 SDD v0.1 整理第一版 Demo 验收矩阵，明确“Demo 通过”“部分通过”“真实链路待验收”的边界。
- 已确认 MinerU 后端逻辑采用 API 调用方式，并记录当前批量签名上传/批量结果查询实现与 MinerU API 文档的对应关系。
- 已为 Step 036 验证补齐后端 SSE helper 类型标注、测试替身协议方法和测试 JSON 字段类型收窄，使后端 mypy 可通过。
- 已完成 Step 036 Python/Docker/Compose/服务检查、后端格式/lint/typecheck/pytest、前端 lint/typecheck/build、migration 状态、Demo fixture seed、真实 API citation+feedback smoke 和 Chat SSE smoke 验证。
- 已新增 OpenSearch BM25 + IK Analyzer 中文关键词召回实现，包含 `chunks_bm25` mapping、`ik_max_word` 索引分词、`ik_smart` 搜索分词、BM25 client、索引 upsert、检索 search、删除失效和 PostgreSQL full-text fallback。
- 已新增 IK 自定义词典配置，预置 `井下落鱼`、`可视化工具`、`光电复合缆`、`防爆计算机`、`地面控制工具`、`井下工具`、`VONETS`、`LED控制` 等领域词。
- 已完成 Step 047 目标后端测试、全量后端测试、ruff、black、mypy、Python 语法检查、Compose 配置检查、OpenSearch 运行态启动、IK 插件检查、自定义词典 `_analyze` 验证、当前 74 active chunks BM25 回填、Retrieval API、非流式 Chat、Chat SSE 和 trace smoke。

## 待完成内容

- Step 041 真实端到端问答验收：当前真实 PDF 已 indexed，非流式 Retrieval/Chat 已通过；下一步需要验证前端 SSE、citation 展示、feedback 和 trace 回显。
- 真实前端问答体验验收：在浏览器中用 `测试` 知识库提问，确认 SSE 流式回答、引用详情和反馈交互。
- 真实图片资产与 ImageBlock 生成：需要从 MinerU zip/assets/metadata 中提取图片资源并保存到 MinIO `assets`。
- 多模态检索接入 Retrieval/Chat：需要把 MultimodalRetriever 接入现有检索与问答链路。
- 真实图片向量、caption/OCR/surrounding text 检索、image evidence 和图片引用验收。
- 前端 citation 图片预览和 image evidence 展示。
- 后续 Phase 6-B/6-C：真实 LLM、引用编号增强。
- feedback bad case 查询接口可选项。
- Playwright/Cypress 等浏览器自动化测试体系。
- cleanup job、异步清理 MinIO/Qdrant 残留对象和知识库删除级联清理。

## 阻塞问题

- Step 016 真实带引用问答端到端存在人工确认项：需要提供 `MINERU_API_TOKEN`，并提供/允许新增真实 embedding-service、reranker-service 和 LLM Provider 后重新验收。
- Step 041 原先因缺少真实外部配置标记为“需要人工确认”；Step 044 已补齐真实配置，Step 045 已完成真实 PDF 解析与索引，但真实带引用问答仍需继续补跑。
- 注意：系统默认 `python`/`python3` 仍为 Python 3.6.8；本项目验证使用明确的 `python3.11` 和 `backend/.venv`，容器内 Python 为 3.11.x。
- 注意：Docker Hub 直连曾超时，本次通过镜像代理拉取基础镜像，并通过 Dockerfile `PIP_INDEX_URL` 构建参数使用可用 PyPI 镜像源完成构建。
- 注意：本地 `.env` 当前仍可能使用短 JWT secret。`.env.example` 已更新为较长开发密钥；生产部署必须设置安全的 `JWT_SECRET_KEY`。
- 注意：SDD 与原 API contract/TDD/前端类型对知识库状态存在冲突。本步骤已按 SDD 优先原则统一为 `active/deleting/deleted`。
- 注意：删除知识库后创建 cleanup job 尚未实现，因为当前还没有 cleanup_jobs 表或任务系统；该项需在后续清理任务阶段补齐。
- 注意：SDD 与原 API contract 对 FileStatus 存在差异。本步骤已按 SDD 将 FileStatus 统一为 `uploaded/queued/processing/indexed/partially_indexed/failed/deleting/deleted`，parse 阶段细分保留在 ParseJobStatus。
- 注意：Docker Hub 直连 MinIO 镜像失败，本步骤使用 `quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z` 拉取同版本镜像并 tag 到 Compose 所需镜像名后完成验证。
- 注意：Step 008 当时通过 fake MinerU client 覆盖提交、轮询、结果保存和失败路径；Step 045 已补跑真实 PDF 在线解析。
- 注意：Step 038 已增强真实 MinerU API parse_job 状态、错误日志和 parsed-results 记录；Step 045 已补跑真实 PDF 在线解析，`.docx/.txt` 在线样本仍可后续补充。
- 注意：Step 038 将后端 Dockerfile 默认 `PIP_INDEX_URL` 改为阿里云 PyPI 镜像，以符合当前环境安装依赖的要求。
- 注意：Step 039 已将 chunking 从 `one_block_one_chunk` 升级为 `heading_aware_recursive`，旧 demo/fake 样本的 chunk 数量可能减少，但 chunk 语义边界更接近真实 RAG 使用。
- 注意：Step 039 尚未把 MinerU assets 图片文件单独保存到 MinIO `assets` bucket；当前只保留 source/asset metadata。
- 注意：Step 040 已按用户确认将 embedding/reranker/LLM 推进为 API 化接入方向；这偏离 SDD 原文“本地 bge-m3 / 本地 BGE reranker”的要求，后续验收需继续明确该边界。
- 注意：Step 040 未配置真实模型 API key 时仍会使用 demo/template client，不能作为真实 RAG 质量验收结果。
- 注意：Step 042 已补齐 RRF `k=60` 混合召回策略，但真实排序质量仍需配置真实 embedding/reranker/LLM API 后通过 Step 041 样本文档端到端验收。
- 注意：Step 043 是多模态基础骨架，不改变现有 Chat/Retrieval 主链路；当前页面问答不会自动具备真实图片召回能力。
- 注意：Step 043 未新增数据库表，`ImageBlock` 当前仅为 Pydantic 数据结构；真实图片索引和 Qdrant 写入需后续步骤实现。
- 注意：Step 043 新增 Qwen provider 但未执行真实在线调用；真实验收需配置 `QWEN_API_KEY` 并确认供应商 payload/response。
- 注意：Step 044 已关闭 Demo fixture；后续 indexed chunks 会走真实 embedding/reranker/LLM API，不再使用 local demo clients。
- 注意：Step 044 只清理运行数据中的 Demo fixture 和前端可见 Demo 文案；历史进度/Demo 文档仍保留 Step 034-036 的开发记录，用于说明项目历史边界。
- 注意：`.env` 当前包含真实 token/key，不应提交到公共仓库或复制到 `.env.example`。
- 注意：Step 045 已确认真实 MinerU PDF 解析与 Qwen embedding/Qdrant 索引可用；当前 `测试` 知识库中的 PDF 已 indexed。
- 注意：Step 045 清理了运行数据库中的历史 Step smoke/readiness 知识库，当前知识库列表仅保留 `测试`。
- 注意：Step 045 删除并重建了只包含 inactive Demo fixture points 的 Qdrant `chunks` collection；当前 collection 维度为 2560。
- 注意：当前任务推进仍由文件状态接口轮询触发，尚未引入独立后台 worker。
- 注意：Step 046 已验证 DashScope/Qwen text reranker 可用；如后续做图片/多模态 rerank，需要新增 multimodal rerank provider。
- 注意：Step 046 已验证非流式 Chat API 可返回带引用回答；Step 047 已补充 Chat SSE smoke，但前端浏览器手动点击验收仍建议后续单独执行。
- 注意：知识库统计当前实时查询 files/chunks；后续大数据量场景可考虑缓存或聚合表。
- 注意：Step 047 已将 BM25 作为 `BM25_ENABLED=true` 时的正式关键词召回通道，PostgreSQL `simple` full-text 保留为 fallback。
- 注意：Step 047 当前 `.env` 已设置 `BM25_ENABLED=true`，backend-api 已重启并确认 OpenSearch BM25 配置生效；如果后续 fresh Compose 中 OpenSearch 不可用，索引/检索会按严格策略返回 BM25 上游错误。
- 注意：Step 047 当前 OpenSearch 为单节点 dev 配置，cluster health 可能因 replica 未分配显示 yellow；主分片、索引、analyzer 和检索均已通过本地验证。
- 注意：Step 010 已将 `GET /files/{file_id}/chunks` 切换为真实 active chunks 查询，但 schema 名称仍为 `ChunkDebugResponse` / `ChunkDebugListResponse`；后续正式 API contract 更新时建议统一命名。
- 注意：Step 010 当前采用 `one_block_one_chunk` MVP chunking 策略；后续可在不破坏表结构的前提下升级为按 token 上限、标题层级和滑窗重叠切片。
- 注意：Step 010 的 `token_count` 为基础正则统计，不是 embedding 模型 tokenizer 的真实 token 数。
- 注意：Step 011 已通过可用镜像源补齐 Redis/Qdrant/Node 镜像，完整 `docker compose up -d` 已通过。但后续环境如果重新拉镜像，仍可能遇到 Docker Hub 直连超时。
- 注意：SDD 规定 embedding-service 是独立服务，但未规定 HTTP API 契约。Step 011 采用 `POST /embed` 的最小合理假设，并兼容多种响应形态；真实 embedding-service 接入时需再次对齐。
- 注意：当前 Compose 尚未定义真实 embedding-service 容器，真实 bge-m3 在线索引未执行。
- 注意：当前 indexing 通过 `GET /files/{file_id}/status` 同步推进；后续接入 Celery worker 后应迁移为异步任务。
- 注意：Step 012 的 Retrieval API 是基础检索入口，不替代后续 Chat API。
- 注意：Step 022 已在 score 合并后接入 reranker client；但真实 reranker-service 尚未提供，排序质量仍未经过真实 BGE reranker 在线验证。
- 注意：Step 012 尚未保存 retrieval trace，不满足 Phase 5 完整“保存 retrieved_chunk_ids”验收。
- 注意：Step 012 PostgreSQL full-text 使用 `simple` 配置，中文检索质量可能需要后续优化。
- 注意：Step 013 已通过 message_trace 保存 query_text、retrieved_chunk_ids、final_context_chunk_ids 和 final_cited_chunk_ids；Step 026 已补齐 reranked_chunk_ids 和 reranker_scores，但真实 token usage 和 prompt snapshot 仍未接入。
- 注意：Step 013 当前回答是模板化 demo，不是 LLM 生成回答，不代表最终回答质量。
- 注意：Step 013 当前 `stream=true` SSE 目标仍未实现；API contract 已注明 Phase 6-A 当前是非流式 JSON demo。
- 注意：Step 014 已完成前端 Chat 页面真实接口联调，但仍使用 `stream=false` 非流式 JSON demo，不是最终 SSE。
- 注意：Step 014 登录 token 当前只做 Demo 级本地保存，尚未实现 refresh token 自动续期。
- 注意：Step 029 已实现 Chat 页面搜索历史会话输入框的本地标题过滤逻辑；搜索范围仅限当前已加载的前 50 条 conversation。
- 注意：Step 014 空知识库拒答路径已通过真实接口 smoke；带 indexed chunks 的真实问答仍依赖 embedding-service、reranker-service 和 LLM Provider 后续补齐。
- 注意：Step 014 前端构建存在第三方 `@vueuse/core` pure annotation warning，构建结果成功，当前不作为阻塞。
- 注意：Step 015 文件上传页面已接真实 API，但上传后 parse_job 当前保持 queued，真实解析仍需通过重新解析触发 MinerU API。
- 注意：Step 015 当时环境未配置 `MINERU_API_TOKEN`；当前 Step 044/045 已补齐配置并验证真实 PDF 可解析索引。
- 注意：Step 015 文件列表当前固定读取前 50 条，Chunk 调试页当前固定读取前 100 条，完整分页 UI 后续补齐。
- 注意：Step 015 Chunk 页面展示真实 active chunks；未完成索引的文件会显示空 chunks。
- 注意：Step 016 已确认 Compose 中不存在 `embedding-service`，本机 `localhost:8200` 和 `localhost:8300` 均不可达。
- 注意：Step 016 已确认 Qdrant 服务正常，但当前 collections 为空。
- 注意：Step 017 KnowledgeBases 页面已接入真实 API，但完整分页 UI 尚未实现，当前读取前 50 条。
- 注意：Step 017 前端还未根据当前用户角色隐藏 Admin-only 操作；权限仍由后端强制控制。
- 注意：Step 018 Users/AuditLogs 页面已接入真实 API，但完整分页 UI 尚未实现，当前读取前 50 条。
- 注意：Step 032 已支持审计日志前端可读中文文案，并保留原始 action/resource_type code 便于排查。
- 注意：Step 033 选择 Qdrant payload 失效而非物理删除 points；真实 indexed 文件在线失效验证仍依赖真实 MinerU/embedding 样本文档链路。
- 注意：Step 033 首次后端镜像构建使用默认 PyPI 源时依赖下载长期无进展并被中断；随后使用 Dockerfile 既有 `PIP_INDEX_URL` 构建参数指定可用镜像源复跑成功。
- 注意：Step 034 的 Demo fixture 只用于开发/演示 citation UI，不代表真实 MinerU、真实 embedding、真实 reranker 或真实 LLM 的生产质量。
- 注意：Step 034-036 阶段本地 `.env` 曾设置 `DEMO_FIXTURE_ENABLED=true` 用于受限 Demo fixture；Step 044 已将当前 `.env` 改回 `false` 并清理运行数据中的 Demo fixture。
- 注意：Step 035 未引入 Playwright/Cypress；当前以前端稳定 selector、文档化验收清单、构建检查和真实 API smoke 固化前端验收。
- 注意：Step 018 审计日志 response 当前没有 request_id 字段，页面展示并复制的是日志 ID。
- 注意：Step 019 Profile 页面当前只读，尚未实现用户自助编辑 display_name 或 profile 偏好。
- 注意：Step 019 前端仍没有集中式 auth store；当前采用页面/布局按需读取 `/auth/me` 的简单实现。
- 注意：Step 019 access token 过期时会跳转登录页，不会自动 refresh。
- 注意：Step 020 Feedback API 已实现基础提交和 telemetry 保存，但尚未实现 feedback 列表或 bad case 查询接口；SDD 中该项为可选。
- 注意：Step 020 Chat 页面当前只提交 rating，不提供 comment 输入框。
- 注意：Step 030 已通过 `feedback_rating` 补齐 Chat 页面加载历史 conversation 时的 helpful/unhelpful 状态回显；当前仍不回显 feedback comment。
- 注意：Step 021 SSE 流式传输的是模板化 demo answer，不是真实 LLM token streaming。
- 注意：Step 021 当前 SSE `retrieval` event 只返回数量，不返回详细 trace。
- 注意：Step 022 默认 reranker-service 契约为 `POST /rerank`，请求体包含 `model`、`query`、`documents`；SDD 未规定该 HTTP 契约，真实服务接入时需要再次对齐。
- 注意：Step 022 当前 Compose 尚未定义真实 reranker-service；有 active indexed chunks 时，如果真实 reranker-service 不可达，Retrieval/Chat 会返回上游服务错误。空知识库拒答路径不会调用 reranker。
- 注意：Step 026 已保存每个可展示 chunk 的 `reranker_scores` 到 message trace；若后续需要严格保存重排前候选集，需要扩展 Retrieval service 内部 trace 输出。
- 注意：Step 023 仅整理 Demo 运行和验收边界，不解除 Step 016 真实端到端人工确认项。
- 注意：Step 023 已更新 README 当前状态，但 API contract、OpenAPI 和前端类型是否完全同步到当前实现仍需后续专项核对。
- 注意：Step 024 已同步 API contract、OpenAPI 和前端类型的主要差异，但未对 OpenAPI 与 FastAPI 自动 schema 做机器级 diff。
- 注意：Step 024 移除了当前未实现的 `/users/me/profile` active contract；如后续恢复用户偏好编辑，需要重新新增后端接口、前端 API、OpenAPI 和测试。
- 注意：Step 025 已将 TDD 从旧的“文档和类型阶段”状态更新为当前基础 Web Demo 状态，但 TDD 仍按完整 SDD MVP 保留严格 P0/P1 验收门槛。
- 注意：Step 025 明确当前基础 Web Demo 可操作不等于完整 SDD MVP 内测通过；真实 MinerU、embedding、reranker、LLM 和样本文档 RAG 端到端仍未验收。
- 注意：Step 026 的 `reranker_scores` 来源于 Retrieval 返回的重排后可展示结果；如后续需要严格保存重排前候选集，需要扩展 Retrieval service 内部 trace 输出。
- 注意：Step 026 不改变前端响应结构，不新增数据库 migration；`message_traces.reranker_scores` 字段此前已经存在。
- 注意：Step 027 只实现后端删除会话接口，不删除 messages/citations/traces/feedback 历史数据。Step 028 已接入前端删除按钮。
- 注意：Step 028 未执行 Playwright 自动化点击测试；当前仓库尚未配置 Playwright，已通过 typecheck/build 和真实接口 smoke 进行最小验证。
- 注意：Step 029 未执行 Playwright 自动化输入测试；当前仓库尚未配置 Playwright，已通过 typecheck/build 和源码关键字扫描进行最小验证。
- 注意：Step 030 新增 `feedback_rating` 响应字段并已同步前端类型、中文 API contract 和 OpenAPI；老客户端忽略该字段不受影响。

## 外部接口实现备注

- MinerU 解析阶段按用户指定采用 API 调用方式实现。
- 已查阅 MinerU API 文档：`https://mineru.net/apiManage/docs`。
- 当前实现采用 MinerU 批量本地文件上传解析方式：`POST /api/v4/file-urls/batch` 申请上传链接，随后通过 signed `PUT` 上传文件，再通过 `GET /api/v4/extract-results/batch/{batch_id}` 查询结果，完成后下载 `full_zip_url` 产物。
- 当前已配置 `MINERU_API_TOKEN`，并已用用户上传的真实 PDF 完成在线解析与 parsed-results 保存。
- 当前 Qwen `qwen3-vl-embedding` 已通过 DashScope 多模态 embedding endpoint 完成真实 text chunk 向量化，当前向量维度为 2560。
- 当前 Qwen `qwen3-vl-rerank` 已通过 DashScope text rerank endpoint 完成真实重排验证。
- 当前生成式、意图识别、知识检索分类和图片描述统一使用
  `qwen3.6-flash-2026-04-16`；该模型已通过真实非流式 Chat API smoke 验证。
- 当前 OpenSearch BM25 + IK Analyzer 已完成代码、测试和运行态验证；当前 `测试` 知识库 74 个 active chunks 已写入 `chunks_bm25`，中文关键词检索可返回 `full_text`/`hybrid` 来源并参与带引用问答。

## 下一步开发建议

建议进入 Step 049：真实前端问答体验与引用展示收口。在浏览器中使用 `测试` 知识库提问，确认 SSE 流式回答、citation detail、feedback 回显和 trace 数据，并观察 OpenSearch BM25 命中是否在真实 UI 闭环中稳定体现。

多模态链路的 Qwen 配置已写入并完成 text chunk embedding 验证；后续应继续补跑真实图片向量、caption/OCR/surrounding text 检索、image evidence、图片引用和前端预览验收。
