# 第一版 Demo 交付验收报告

本文档记录第一版 Demo 的交付审计结论。它只确认当前仓库在已记录边界内可以作为第一版 Web Demo 演示，不把受限 fixture、fake client 或模板回答解释为完整 SDD v0.1 MVP 验收通过。

## 1. 验收结论

当前项目可以标记为：

> 第一版基础 Web Demo 已完成，可在本地 Docker Compose 基础栈中运行，并能演示登录、用户管理、知识库管理、文件上传与状态查看、审计日志、Chat SSE、拒答、会话/trace/feedback 保存，以及受限 Demo fixture 下的 citation UI。

当前项目不能标记为：

> SDD v0.1 完整 MVP 已完成。

原因是完整 MVP 的真实外部服务链路仍缺少在线验收条件：

- 当前环境未配置 `MINERU_API_TOKEN`，真实 MinerU 在线解析未执行。
- Compose 当前未提供真实 `embedding-service`，真实 bge-m3 embedding 未执行。
- Compose 当前未提供真实 `reranker-service`，真实 BGE reranker 在线重排未执行。
- 当前 Chat answer 是模板化 Demo 文本，不是真实 LLM 生成。
- 尚未执行真实样本文档的“上传 -> MinerU API 解析 -> chunks -> embedding -> Qdrant -> reranker -> LLM -> 带引用回答”端到端验收。

## 2. SDD 对照验收矩阵

| SDD v0.1 核心要求 | 第一版 Demo 状态 | 证据 | 结论 |
|---|---|---|---|
| Admin 登录与用户管理 | 已实现 | Auth/Users API、前端 Users 页面、后端测试、真实 API smoke | Demo 通过 |
| Admin 创建、编辑、删除知识库空间 | 已实现 | KnowledgeBase API、前端知识库页面、软删除与审计日志 | Demo 通过 |
| Admin 上传多格式文件 | 已实现基础能力 | Files API、前端文件页、白名单/大小/同名/hash 校验、MinIO raw-files | Demo 通过 |
| 原始文件保存到 MinIO | 已实现 | `raw-files` bucket 写入已在前序步骤验证 | Demo 通过 |
| 使用 MinerU 解析文件 | API client 已实现，真实在线未验收 | `backend/app/services/mineru.py` 使用 MinerU 批量签名上传与批量结果查询 API；无 token | 部分通过 |
| 解析结果持久化 | fake/fixture 路径已验证 | `parsed-results`、document_blocks 标准化流程 | 部分通过 |
| blocks 标准化与 chunks 生成 | 已实现基础能力 | document_blocks、chunks_metadata、chunks 调试接口 | Demo 通过 |
| bge-m3 embedding 与 Qdrant 写入 | client/索引编排/fixture 已实现 | embedding client、Qdrant client、Demo fixture Qdrant points | 部分通过 |
| PostgreSQL full-text 与混合召回 | 已实现基础能力 | Retrieval API vector + full-text merge | Demo 通过 |
| BGE reranker 重排 | client/fixture 已实现，真实在线未验收 | reranker client、fake/local demo reranker 测试 | 部分通过 |
| User 基于单知识库提问 | 已实现 | Conversation 绑定 knowledge_base_id，权限隔离 | Demo 通过 |
| SSE 流式返回回答 | 已实现 Demo 流式 | SSE events：message_created/retrieval/token/done | Demo 通过 |
| 回答带引用编号 | fixture 路线已验证 | Demo fixture 推荐问题返回 `[1]`，citation_count 为 3 | Demo 通过，真实链路待验收 |
| 引用包含文件名、定位信息、原文片段 | fixture 路线已验证 | citation 包含 `file_name`、`source_locator`、`excerpt`、`chunk_id` | Demo 通过，真实链路待验收 |
| 证据不足时拒答 | 已实现 | 空知识库/无证据路径返回拒答 | Demo 通过 |
| 保存会话、消息、引用、trace | 已实现基础能力 | conversations/messages/message_citations/message_traces | Demo 通过 |
| helpful / unhelpful 反馈 | 已实现 | Feedback API、前端按钮、历史会话 feedback 回显 | Demo 通过 |
| 高危操作审计日志 | 已实现基础能力 | 知识库、文件、用户管理操作写入 audit_logs | Demo 通过 |
| Docker Compose 一键启动完整系统 | 基础栈可启动 | backend-api、frontend、Postgres、Redis、Qdrant、MinIO | Demo 通过，完整 MVP 缺模型服务 |

## 3. MinerU API 调用方式确认

用户已明确要求 MinerU 部分通过 API 调用方式实现。当前实现满足该方向：

- `MineruApiClient.submit_file()` 调用 `POST /api/v4/file-urls/batch` 申请批量文件上传链接。
- 后端使用 MinerU 返回的签名 URL 通过 `PUT` 上传文件内容。
- `MineruApiClient.get_batch_result()` 调用 `GET /api/v4/extract-results/batch/{batch_id}` 查询批量解析结果。
- `MineruApiClient.download_result()` 下载 `full_zip_url` 产物，并由后续流程保存到 MinIO `parsed-results`。

参考来源：MinerU API 文档 `https://mineru.net/apiManage/docs` 中“批量本地文件上传解析”流程。

当前未配置 `MINERU_API_TOKEN`，因此本报告只确认代码调用方式与文档路线一致，不确认真实 MinerU 在线解析已经通过。

## 4. 第一版 Demo 可演示路径

基础 Admin 路径：

1. 打开 `http://localhost:5173`。
2. 使用 `admin` / `AdminPassword123` 登录。
3. 验证当前用户展示、Profile、logout。
4. 创建/编辑/删除知识库。
5. 上传 SDD 白名单格式文件，查看文件列表、状态和 chunks 调试页。
6. 创建/编辑/禁用/启用/重置用户。
7. 查看审计日志。

Demo fixture citation 路径：

1. 确认 `.env` 中 `DEMO_FIXTURE_ENABLED=true`。
2. 执行 `docker compose exec backend-api python -m app.dev.seed_demo_fixture`。
3. 打开 `http://localhost:5173`。
4. 使用 `demo_user` / `DemoUserPassword123` 登录。
5. 选择 `Demo Fixture 知识库`。
6. 新建会话并发送：`井下落鱼可视化工具 使用步骤是什么？`
7. 验证 assistant answer 包含 `[1]`。
8. 点击 citation chip，验证引用详情包含 `demo-rag-fixture.txt`、`demo:section-1` 和原文片段。
9. 提交 helpful/unhelpful feedback，并重新打开历史会话确认状态回显。

完整前端验收清单见 `docs/demo/frontend-acceptance-checklist.md`。

## 5. 本次收口验证结果

Step 036 的最终验证结果记录在 `docs/progress/step-036-demo-delivery-audit.md`。

## 6. 交付边界

第一版 Demo 交付边界：

- 可以作为本地可运行 Web Demo 演示。
- 可以证明主要页面已接真实后端 API。
- 可以通过受限 fixture 演示 citation UI、feedback 和 trace 数据结构。
- 可以为后续真实外部服务接入提供稳定基础。

不在第一版 Demo 交付边界内：

- 真实 LLM 回答质量。
- 真实 MinerU 在线解析质量。
- 真实 embedding/reranker 模型效果。
- 真实样本文档 RAG 评估。
- 生产部署、安全密钥、对象清理任务和完整异步 worker 架构。

## 7. 后续建议

下一阶段建议进入真实外部服务接入与端到端验收，而不是继续扩大 Demo fixture：

1. 配置 `MINERU_API_TOKEN` 并复跑真实 MinerU 在线解析。
2. 提供或新增真实 bge-m3 `embedding-service`。
3. 提供或新增真实 BGE `reranker-service`。
4. 接入 LLM Provider。
5. 使用 SDD/TDD 样本文档执行真实“上传到带引用回答”端到端验收。
6. 在真实链路稳定后，再补浏览器自动化测试和真实 RAG 样本评估。
