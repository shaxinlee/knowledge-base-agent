# 知识库 Agent 助手 v0.1 TDD

本文档是知识库 Agent 助手 v0.1 的 TDD（Test Design Document）主测试设计文档。它把 `SDD.v0.1.md`、API 契约和上传的真实业务样本转化为可执行的测试范围、测试数据、测试用例和验收门槛。

| 字段 | 内容 |
| --- | --- |
| 版本 | v0.1 |
| 定位 | 测试设计与内测验收基准 |
| 上游规范 | `docs/specs/SDD.v0.1.md` |
| API 契约 | `docs/api/frontend-backend-api-contract.md`、`docs/api/openapi.v0.1.yaml` |
| 目标读者 | 测试 Agent、后端开发 Agent、前端开发 Agent、RAG / 检索链路开发 Agent、验收人员 |
| 测试策略 | 规范驱动测试、接口契约测试、真实样本文档解析测试、RAG 证据链测试、端到端验收测试 |

⸻

## 0. 当前实现与测试状态

本 TDD 仍然是 SDD v0.1 完整 MVP 的测试设计与内测验收基准。当前仓库到 Step 034 为止已经具备第一版基础 Web Demo，并可通过受限 Demo fixture 演示 citation UI，但尚未满足完整 MVP 内测门槛。

当前已验证的基础 Demo 能力：

- Docker Compose 基础栈可运行：frontend、backend-api、PostgreSQL、Redis、Qdrant、MinIO。
- 后端健康检查可访问：`GET /api/v1/health`。
- 后端自动化测试在 Step 034 验证通过：`42 passed, 60 warnings`。
- 前端类型检查和生产构建在 Step 034 验证通过。
- OpenAPI YAML 可解析，API contract、OpenAPI、前端类型已同步当前主要实现。
- 前端可操作路径包括登录、当前用户展示、知识库管理、文件上传/状态、用户管理、审计日志、Chat SSE 拒答、feedback。
- 受限 Demo fixture 路线可生成 `Demo Fixture 知识库`、indexed file、chunks 和 Qdrant points，并已通过真实 API smoke 验证 Chat citation 返回。
- Step 035 已新增 `docs/demo/frontend-acceptance-checklist.md`，并在 Chat 页面补充稳定 `data-testid` selector，用于固化第一版 Demo 前端验收。
- Step 036 已新增 `docs/demo/first-version-demo-acceptance-report.md`，明确第一版基础 Web Demo 可交付演示，但完整 SDD v0.1 MVP 仍需真实 MinerU、embedding-service、reranker-service、LLM 和真实样本文档端到端验收。
- Step 043 已新增多模态 QueryRouter、Qwen 多模态 embedding provider 抽象、ImageBlock/Evidence、MultimodalRetriever 骨架和 Weighted RRF 单元测试；该能力当前是可测试基础骨架，尚未接入真实 Chat/Retrieval 主链路。
- Step 047 已完成 OpenSearch BM25 + IK Analyzer 中文关键词召回实现，保留 PostgreSQL full-text 作为 `BM25_ENABLED=false` fallback；BM25 client、索引接入、检索接入、删除失效、mock 单元测试、OpenSearch/IK 运行态验证、`_cat/plugins`、`_analyze`、真实 74 个 chunks BM25 回填、Retrieval API、非流式 Chat、Chat SSE 和 trace smoke 均已通过。

当前尚未解除的完整 MVP 验收缺口：

- 当前真实 MinerU PDF 解析、Qwen embedding、Qdrant 写入、OpenSearch BM25 + IK Analyzer、Qwen reranker、非流式 LLM 带引用回答和 Chat SSE smoke 已通过运行态验证；完整前端浏览器 citation/feedback 路径仍需继续验收。
- OpenSearch BM25 + IK Analyzer 当前已完成运行态验证：`analysis-ik 2.18.0` 插件可见，`kb_ik_search` 能识别 `井下落鱼`、`可视化工具`、`光电复合缆`、`地面控制工具` 等领域词，`chunks_bm25` 当前写入 74 条真实 active chunk 文档。
- 当前 Chat 在 fresh Compose 环境中若启用 `BM25_ENABLED=true`，需要 OpenSearch 可用；否则关键词召回/索引会按严格策略失败。
- 尚未落地 Playwright E2E 自动化测试；当前 Step 035 先提供稳定 selector 和文档化验收清单。
- 尚未落地 schemathesis 或等价 OpenAPI 机器级契约测试。
- 尚未执行真实 RAG 样本评估测试。
- 尚未完成真实图片 assets 落库、ImageBlock 持久化/索引、Qwen 多模态 embedding 在线调用、图片向量入 Qdrant、图片 evidence 接入 Chat 和前端图片引用预览。

因此，本 TDD 中 P0/P1 用例仍按完整 MVP 目标保留；凡当前 Demo 未实现或未验证的能力，在对应章节以“当前状态”记录，不视为已通过。

⸻

## 1. 测试目标

v0.1 测试必须证明系统满足以下目标：

1. 系统可通过 Docker Compose 启动并暴露健康检查。
2. Admin、User、权限边界和 JWT 生命周期符合 SDD。
3. Admin 可创建知识库并上传支持格式文件。
4. 文件上传校验覆盖大小、数量、扩展名、同名、hash 重复和知识库状态。
5. 支持格式文件可完成解析、标准化、chunking、embedding、索引和状态流转。
6. 检索必须强制限定在单个 knowledge_base_id 内，不能跨知识库污染。
7. 问答必须通过 SSE 返回，最终回答必须基于 final context chunks。
8. 引用必须包含引用编号、文件名、source_locator、原文片段和 chunk_id。
9. 证据不足时必须拒答，不得使用通用知识补全。
10. 会话、消息、引用、trace、反馈和审计日志必须按 SDD 保存。
11. 前端核心页面可完成登录、管理、上传、状态轮询、问答、引用展示和反馈。

⸻

## 2. 测试范围

### 2.1 范围内

- 后端单元测试。
- 后端 API 集成测试。
- OpenAPI 契约测试。
- 文件上传与解析链路测试。
- MinIO、PostgreSQL、Qdrant、Redis、Celery 集成测试。
- Embedding、Reranker、MinerU、LLM client mock 测试。
- 多模态 QueryRouter、Embedding provider、Evidence 融合和 MultimodalRetriever mock 测试。
- 真实模型服务可用时的全链路冒烟测试。
- RAG 检索、重排、引用和拒答测试。
- SSE 流式响应测试。
- 前端组件、状态管理和页面流程测试。
- Playwright 端到端测试。
- RBAC、安全和审计测试。
- Docker Compose 内测验收测试。

### 2.2 范围外

以下能力属于 SDD v0.1 明确排除项，不编写正向测试：

- 跨知识库查询。
- GraphRAG 实际召回。
- 实体抽取、关系抽取、社区摘要和图谱可视化。
- 文件版本管理。
- 文档级权限。
- OpenAI-compatible 对外网关。
- Text2SQL。
- 复杂 Excel / CSV 聚合计算。
- 手动编辑 chunk。
- Editor 角色、用户组和团队空间。
- 支付、计费和套餐系统。

如以上能力出现，只能作为“不得出现”的负向测试。

⸻

## 3. 测试数据

### 3.1 外部样本包

用户提供的真实业务样本包可作为文件上传、解析、chunking、检索和引用测试数据：

```text
/root/.codex/attachments/9a28c783-b898-4c24-900f-e6657fda984b/作业单位各类型测试文件-操作手册类.rar
```

该样本包不提交到项目仓库。自动化测试若需要使用它，应通过环境变量传入路径：

```text
TEST_FIXTURE_ARCHIVE=/root/.codex/attachments/9a28c783-b898-4c24-900f-e6657fda984b/作业单位各类型测试文件-操作手册类.rar
```

### 3.2 样本包格式分布

| 扩展名 | 数量 | SDD v0.1 支持状态 | 测试用途 |
| --- | ---: | --- | --- |
| `.pdf` | 8 | 支持 | 正向上传、解析、页码 source_locator、检索引用 |
| `.docx` | 5 | 支持 | 正向上传、解析、段落/标题 chunking |
| `.xls` | 4 | 支持 | 正向上传、表格区域 source_locator |
| `.xlsx` | 4 | 支持 | 正向上传、表格区域 source_locator |
| `.pptx` | 2 | 支持 | 正向上传、slide source_locator |
| `.doc` | 5 | 不支持 | 负向上传，期望 `UNSUPPORTED_FILE_TYPE` |
| `.ppt` | 3 | 不支持 | 负向上传，期望 `UNSUPPORTED_FILE_TYPE` |

注意：样本包中 `pptx/RTTS封隔器解卡方法探讨.pdf` 的实际扩展名是 `.pdf`，应按 PDF 样本处理。

### 3.3 样本文件清单

| 类型 | 文件 |
| --- | --- |
| `.doc` | `7.S2H型砾石充填转换工具.doc`、`DQ2-1使用说明书.doc`、`SB-PLUG SB堵塞器作业流程.doc`、`打捞规程.doc`、`第三章井口设备.doc` |
| `.docx` | `可回收式服务工具手册（操作部分）.docx`、`多轮强磁打捞器操作规范----侯庆雪.docx`、`工具说明书（新）.docx`、`弃井手册推荐做法-双层套管处理请以此为准.docx`、`打捞Halliburton隔离封隔器的方法.docx` |
| `.pdf` | `1.井下落鱼可视化工具使用说明书_1.5.pdf`、`ADM30528.pdf`、`SPE-116771-MS.pdf`、`SY-T 5106-1998 油气田用封隔器通用技术条件.pdf`、`塔里木油田高效套铣工具的研究与应用_魏军会.pdf`、`射孔工具新手册050818.pdf`、`库车山前高温高压气井完井封隔器失效控制措施_王克林.pdf`、`RTTS封隔器解卡方法探讨.pdf` |
| `.ppt` | `JS04-1-井下工艺应用技术(正式）2003.ppt`、`JS08-平台集约化水力压裂技术的应用(赵战江）.ppt`、`常用打捞工具原理介绍.ppt` |
| `.pptx` | `51 锦州25-1油田6 11井区两口大位移井合成基钻井液使用成功总结9.6.pptx`、`大修工艺技术.pptx` |
| `.xls` | `KL10-1-A25井外租工具出料单1114.xls`、`毛细管基础数据表.xls`、`渤南出海物资申请表2019.10.23.xls`、`钻杆钢级及强度.xls` |
| `.xlsx` | `3.4套管堵漏数据项.xlsx`、`KL-A25防砂磨铣通井.xlsx`、`工具标准化文件台账--井筒干预技术中心.xlsx`、`过电缆封隔器遇卡、拔脱处理方式汇集.xlsx` |

### 3.4 生成型负向数据

除真实样本包外，测试还必须生成以下负向数据：

| 数据 | 生成方式 | 预期 |
| --- | --- | --- |
| 超 50MB 文件 | 创建 51MB 临时文件 | `413 FILE_TOO_LARGE` |
| 单次 51 个文件 | 创建 51 个小型 `.txt` 文件 | `400 TOO_MANY_FILES` |
| 同名不同内容文件 | 同一知识库重复上传同名文件 | `409 DUPLICATE_FILE_NAME` |
| 不同名同 hash 文件 | 复制同一文件并改名 | `409 DUPLICATE_FILE_HASH`，`can_force_upload=true` |
| 空文件 | 创建 0 字节 `.txt` 文件 | 后端应拒绝或 parse_job failed，具体行为必须稳定记录 |
| 损坏文件 | 截断 `.pdf/.docx/.xlsx` | parse_job failed，不污染 active 检索集合 |
| 不支持扩展名 | `.doc/.ppt/.exe/.zip` | `400 UNSUPPORTED_FILE_TYPE` |

⸻

## 4. 测试环境

### 4.1 本地集成环境

完整 MVP 目标环境应使用 Docker Compose 启动：

- backend-api
- frontend
- PostgreSQL
- Redis
- Qdrant
- MinIO
- Celery worker
- embedding-service
- reranker-service

当前第一版基础 Web Demo 已验证的 Compose 栈包括：

- backend-api
- frontend
- PostgreSQL
- Redis
- Qdrant
- MinIO

当前 Compose 尚未包含 Celery worker、本地 embedding-service、本地 reranker-service。MinerU、embedding、reranker、LLM 均已按用户确认方向改为 API 化接入。Step 047 已新增并验证 OpenSearch 服务用于 BM25 中文关键词召回，当前本地 dev 栈包含 frontend、backend-api、PostgreSQL、Redis、Qdrant、MinIO、OpenSearch。

### 4.2 Mock 环境

CI 和快速回归允许使用 mock：

- Mock MinerU：返回固定 markdown/json/assets。
- Mock Embedding：返回确定性向量。
- Mock Reranker：返回确定性 score。
- Mock LLM：返回可预测 SSE token、done 和 error 事件。

Mock 环境必须仍然校验数据库写入、状态流转、trace、引用结构和权限边界。

### 4.3 真实链路环境

内测前必须至少执行一次真实链路冒烟：

- 使用真实 MinerU 解析样本包中的支持格式文件。
- 使用本地 bge-m3 embedding。
- 使用本地 BGE Reranker。
- 使用配置的 LLM Provider。
- 如启用多模态链路，使用配置的 Qwen 多模态 embedding provider，并验证图片向量、caption/OCR/surrounding text、image evidence 和图片引用。
- 通过前端完成上传、问答、引用和反馈。

⸻

## 5. 测试优先级

| 优先级 | 含义 | 失败处理 |
| --- | --- | --- |
| P0 | 阻塞内测，核心链路或安全边界 | 必须修复 |
| P1 | 影响主要功能或验收可信度 | 内测前修复 |
| P2 | 影响体验、可维护性或边界场景 | 可排期修复 |
| P3 | 低风险优化或观察项 | 记录即可 |

⸻

## 6. 用例设计

### 6.1 启动与健康检查

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-BOOT-001 | P0 | Docker Compose 启动 | 执行完整启动流程 | 所有基础服务启动成功 |
| TDD-BOOT-002 | P0 | 后端健康检查 | 请求 `GET /api/v1/health` | 返回 `status=ok`、`service=backend-api`、`version=0.1.0` |
| TDD-BOOT-003 | P1 | 前端访问 | 打开前端地址 | 登录页可访问，无控制台阻塞错误 |
| TDD-BOOT-004 | P0 | Alembic migration | 初始化数据库并执行 migration | migration 成功，核心表存在 |

### 6.2 认证、用户与权限

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-AUTH-001 | P0 | Admin 登录 | 使用默认 Admin 登录 | 返回 access_token、refresh_token 和 admin 用户信息 |
| TDD-AUTH-002 | P0 | User 登录 | Admin 创建 user 后登录 | 返回 user 角色 token |
| TDD-AUTH-003 | P0 | 禁用用户 | Admin 禁用 user 后尝试登录 | 返回 `ACCOUNT_DISABLED` |
| TDD-AUTH-004 | P0 | 登录锁定 | 连续 5 次错误密码 | 账号锁定 15 分钟，返回 `ACCOUNT_LOCKED` |
| TDD-AUTH-005 | P0 | Admin API 权限 | user 请求 `GET /users` | 返回 `403 FORBIDDEN` |
| TDD-AUTH-006 | P0 | Token 缺失 | 不带 token 请求业务接口 | 返回 `401 UNAUTHORIZED` |
| TDD-AUTH-007 | P1 | Refresh token | 使用 refresh token 调用刷新接口 | 返回新 access token |
| TDD-AUTH-008 | P1 | Logout | 调用 logout 后复用 refresh token | refresh token 不可继续使用 |

说明：因 SDD v0.1 `users.email` 为 `UNIQUE NOT NULL`，Admin 创建 user 的测试数据必须包含唯一 email。
说明：logout 用例要求服务端记录 refresh token 吊销状态，复用已 logout 的 refresh token 必须返回 `UNAUTHORIZED`。

### 6.3 知识库管理

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-KB-001 | P0 | Admin 创建知识库 | `POST /knowledge-bases` | 返回 `201` 和 active 知识库 |
| TDD-KB-002 | P0 | User 只读知识库 | user 请求知识库列表 | 可查看 active 知识库 |
| TDD-KB-003 | P0 | User 禁止创建知识库 | user 请求创建知识库 | 返回 `403 FORBIDDEN` |
| TDD-KB-004 | P1 | 更新知识库 | Admin 修改名称、描述、状态 | 返回更新后的对象 |
| TDD-KB-005 | P0 | 删除知识库 | Admin 删除知识库 | 软删除、创建 cleanup job、写入 audit log |
| TDD-KB-006 | P0 | inactive 知识库上传 | 对 deleting/deleted 知识库上传文件 | 返回 `KNOWLEDGE_BASE_INACTIVE` |

当前状态：知识库软删除和 audit log 已实现；`TDD-KB-005` 中 cleanup job 尚未实现，因为当前还没有 cleanup_jobs 表或任务系统。

### 6.4 文件上传校验

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-FILE-001 | P0 | Admin 上传支持格式 | 上传样本包中的 `.pdf/.docx/.xls/.xlsx/.pptx` | 返回 `202`，每个文件创建 file 和 parse_job |
| TDD-FILE-002 | P0 | User 禁止上传 | user 上传任意支持格式文件 | 返回 `403 FORBIDDEN` |
| TDD-FILE-003 | P0 | 超 50MB | 上传 51MB 文件 | 返回 `413 FILE_TOO_LARGE` |
| TDD-FILE-004 | P0 | 单次超过 50 个 | 一次上传 51 个文件 | 返回 `TOO_MANY_FILES` |
| TDD-FILE-005 | P0 | 不支持 `.doc` | 上传样本包中的 `.doc` 文件 | 返回 `UNSUPPORTED_FILE_TYPE` |
| TDD-FILE-006 | P0 | 不支持 `.ppt` | 上传样本包中的 `.ppt` 文件 | 返回 `UNSUPPORTED_FILE_TYPE` |
| TDD-FILE-007 | P0 | 同名文件 | 同一知识库重复上传同名文件 | 返回 `DUPLICATE_FILE_NAME`，不创建新 file |
| TDD-FILE-008 | P0 | hash 重复 | 同一知识库上传不同名同内容文件 | 返回 `DUPLICATE_FILE_HASH`，details 包含 duplicates |
| TDD-FILE-009 | P1 | force 上传 | 对 hash 重复文件使用 `force=true` | 上传成功并创建 parse_job |
| TDD-FILE-010 | P0 | MinIO 原始文件 | 上传成功后检查 MinIO `raw-files` | 存在原始对象，metadata 可追溯 file_id |
| TDD-FILE-011 | P1 | 文件列表筛选 | 按 keyword/status 查询文件列表 | 分页、筛选和 total 正确 |
| TDD-FILE-012 | P0 | 文件删除 | Admin 删除 indexed 文件 | file 软删除，chunks inactive，Qdrant points 失效或清理，写 audit log |

当前状态：文件上传校验、MinIO raw-files、文件软删除和审计已实现；Step 033 已补齐 indexed 文件删除时 active chunks 置为 inactive，并通过 fake Qdrant client 验证 points payload `is_active=false`。真实 Qdrant 在线删除/失效验证仍依赖真实索引样本文档链路。

### 6.5 解析、标准化与 Chunking

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-PARSE-001 | P0 | parse_job 创建 | 上传支持格式文件 | parse_job 初始状态为 `queued` |
| TDD-PARSE-002 | P0 | 状态流转 | 轮询 `GET /files/{file_id}/status` | 状态按 queued/parsing/normalizing/chunking/embedding/indexing/indexed 或 failed 流转 |
| TDD-PARSE-003 | P0 | PDF source_locator | 解析 PDF 样本 | chunks 存在，locator 形如 `pdf:p12` 或 `pdf:p12-p13` |
| TDD-PARSE-004 | P0 | DOCX chunking | 解析 DOCX 样本 | 生成 document_blocks 和 chunks，内容非空 |
| TDD-PARSE-005 | P0 | XLS/XLSX locator | 解析表格样本 | locator 包含 sheet 和单元格范围，例如 `xls:Sheet1!A1:F20` 或 `xlsx:Sheet1!A1:F20` |
| TDD-PARSE-006 | P0 | PPTX locator | 解析 PPTX 样本 | locator 形如 `pptx:slide-8` |
| TDD-PARSE-007 | P0 | 解析失败隔离 | 上传损坏文件 | parse_job failed，error_message 保留，不产生 active chunks |
| TDD-PARSE-008 | P0 | retry-parse | 对 failed 文件调用 retry | 创建新的 parse_job，旧失败日志保留 |
| TDD-PARSE-009 | P1 | 最新成功产物 | 对同一文件多次解析 | 只有最新成功 job 的产物进入 active 检索 |
| TDD-PARSE-010 | P1 | token/content hash | 检查 chunks_metadata | token_count、content_hash、is_active 正确 |

### 6.6 Embedding、索引与检索

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-INDEX-001 | P0 | Embedding 调用 | chunking 后进入 embedding | 每个 active chunk 调用 embedding-service |
| TDD-INDEX-002 | P0 | Qdrant 写入 | indexing 完成后检查 Qdrant | points 存在，payload 包含 knowledge_base_id、file_id、chunk_id、is_active |
| TDD-INDEX-003 | P0 | OpenSearch BM25 中文关键词索引 | indexed 后查询 `chunks_bm25` | OpenSearch docs 存在，IK Analyzer 使用 `ik_max_word` / `ik_smart`，并限定 knowledge_base_id/is_active |
| TDD-INDEX-004 | P0 | 单知识库过滤 | 两个知识库上传不同样本后检索 | 结果只来自指定 knowledge_base_id |
| TDD-INDEX-005 | P0 | 删除后不参与检索 | 删除文件后再次检索相关关键词 | 已删除文件 chunks/vectors/BM25 docs 不返回 |
| TDD-INDEX-006 | P1 | 混合召回 | 查询领域关键词 | 结果合并 vector + BM25 full_text，RRF 去重 chunk_id |
| TDD-INDEX-007 | P0 | Reranker 重排 | 执行检索链路 | reranked_chunk_ids 和 reranker_scores 写入 trace |
| TDD-INDEX-008 | P1 | top_k 截断 | 召回大于 top_k | final_context_count 不超过配置上限 |

当前状态：reranker client 已接入 Retrieval/Chat 的合并结果后重排路径，并记录 `reranker_model`、`reranked_chunk_ids` 和 `{chunk_id: score}` 形式的 `reranker_scores`。Step 047 已实现并验证 BM25/OpenSearch client、索引接入、检索接入和删除失效测试；`TDD-INDEX-003` 已通过真实服务 smoke，当前 `chunks_bm25` 有 74 条真实 active chunk 文档，中文 analyzer 与领域词典验证通过。

### 6.7 RAG 问答、SSE 与引用

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-CHAT-001 | P0 | 创建会话 | user 创建绑定知识库的会话 | 返回 conversation，绑定单个 knowledge_base_id |
| TDD-CHAT-002 | P0 | SSE 事件顺序 | 发送问题并监听 SSE | 依次出现 `message_created`、`retrieval`、`token`、`done` 或 `error` |
| TDD-CHAT-003 | P0 | 引用编号 | 对已入库样本提问 | 最终 answer 包含 `[1]` 等引用编号 |
| TDD-CHAT-004 | P0 | 引用结构 | 检查 done.citations | 每条 citation 包含 file_name、source_locator、excerpt、chunk_id |
| TDD-CHAT-005 | P0 | 证据约束 | 提问当前知识库无关问题 | 返回 `INSUFFICIENT_EVIDENCE` 或拒答模板 |
| TDD-CHAT-006 | P0 | 不跨知识库回答 | A/B 知识库分别入库，向 A 会话问 B 专属内容 | 不返回 B 的 chunk，不引用 B 的文件 |
| TDD-CHAT-007 | P0 | trace 保存 | 完成一次问答 | 保存 query_text、retrieved_chunk_ids、reranked_chunk_ids、final_context_chunk_ids、final_cited_chunk_ids 等 |
| TDD-CHAT-008 | P1 | 网络中断 | 中断 SSE 连接后重新发送 | 前端不崩溃，允许重新提问 |
| TDD-CHAT-009 | P1 | 用户画像风格 | 修改 answer_style/language 后提问 | 只影响表达风格，不影响事实、引用和证据阈值 |

当前状态：SSE transport、事件顺序、空知识库拒答、message/citation/trace 基础保存已实现；当前 answer 是模板化 Demo 文本，不是真实 LLM 输出。`TDD-CHAT-009` 的用户画像 answer_style/language 偏好尚未接入当前 Demo，当前 Profile 使用 `/api/v1/auth/me` 只读展示。

建议真实样本查询：

| 查询 | 目标样本 | 验证重点 |
| --- | --- | --- |
| `井下落鱼可视化工具的使用步骤是什么？` | `1.井下落鱼可视化工具使用说明书_1.5.pdf` | PDF 检索、页码引用、拒绝编造 |
| `封隔器通用技术条件中有哪些关键要求？` | `SY-T 5106-1998 油气田用封隔器通用技术条件.pdf` | 标准类 PDF 引用 |
| `多轮强磁打捞器操作规范有哪些注意事项？` | `多轮强磁打捞器操作规范----侯庆雪.docx` | DOCX 解析和中文检索 |
| `防砂磨铣通井相关数据有哪些？` | `KL-A25防砂磨铣通井.xlsx` | 表格解析和 sheet locator |
| `大修工艺技术里介绍了哪些工艺？` | `大修工艺技术.pptx` | PPTX slide 引用 |

### 6.8 会话、消息与反馈

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-CONV-001 | P0 | 会话列表隔离 | user A/B 各自创建会话 | 用户只能看到自己的会话 |
| TDD-CONV-002 | P1 | 会话详情 | 获取 conversation detail | 返回 messages 和 citations |
| TDD-CONV-003 | P1 | 删除会话 | 当前用户删除自己的会话 | 返回 `204`，其他用户不可删除 |
| TDD-FB-001 | P0 | helpful 反馈 | 对 assistant message 点赞 | 返回 feedback，关联 message_trace |
| TDD-FB-002 | P0 | unhelpful 反馈 | 对 assistant message 点踩并填写 comment | 保存 rating/comment |
| TDD-FB-003 | P1 | 重复反馈 | 同一用户对同一 message 再次反馈 | 更新原反馈，不重复创建 |
| TDD-FB-004 | P0 | 禁止反馈 user message | 对 user message 反馈 | 返回业务错误 |

当前状态：会话列表隔离、会话详情、删除会话、feedback upsert、历史会话 feedback 状态回显和禁止反馈 user message 已实现基础测试。删除会话采用软删除，删除后当前用户列表和详情默认不可见，其他用户删除返回 `RESOURCE_NOT_FOUND`。

### 6.9 审计日志

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-AUDIT-001 | P0 | 删除知识库审计 | Admin 删除知识库 | 写入 audit_logs |
| TDD-AUDIT-002 | P0 | 删除文件审计 | Admin 删除文件 | 写入 audit_logs |
| TDD-AUDIT-003 | P1 | 用户管理审计 | Admin 禁用/启用/重置密码 | 写入 audit_logs |
| TDD-AUDIT-004 | P0 | User 禁止查看审计 | user 请求 `GET /audit-logs` | 返回 `403 FORBIDDEN` |
| TDD-AUDIT-005 | P1 | 审计列表筛选 | 按 actor/action/resource_type 查询 | 分页和筛选正确 |

当前状态：知识库、文件和用户管理相关审计已实现；Admin 创建/更新/禁用/启用/重置密码用户会写入 audit_logs，重置密码审计只记录 `password_changed=true`，不记录明文密码或 password hash。

### 6.10 前端端到端

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-FE-001 | P0 | 登录页 | 输入 Admin 账号密码 | 登录成功进入系统 |
| TDD-FE-002 | P0 | 权限菜单 | Admin/User 分别登录 | Admin 看到管理入口，User 不看到上传和管理入口 |
| TDD-FE-003 | P0 | 创建知识库 | Admin 通过页面创建知识库 | 列表出现新知识库 |
| TDD-FE-004 | P0 | 文件上传 | Admin 上传支持格式样本 | 页面显示上传结果和状态轮询 |
| TDD-FE-005 | P0 | 上传错误提示 | 上传 `.doc/.ppt` 或超限文件 | 根据 error.code 展示稳定错误文案 |
| TDD-FE-006 | P0 | 对话页 SSE | User 提问 | token 流式展示，done 后展示最终回答 |
| TDD-FE-007 | P0 | 引用展示 | 问答完成后查看引用 | 展示文件名、locator、片段 |
| TDD-FE-008 | P0 | 反馈按钮 | 对回答点赞/点踩 | 请求成功，按钮状态更新 |
| TDD-FE-009 | P1 | 网络异常 | 后端返回 500 或 SSE 中断 | 页面有错误提示，不出现空白页 |

### 6.11 安全与边界

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| TDD-SEC-001 | P0 | 默认不开放注册 | 请求注册类接口 | 不存在或返回不允许 |
| TDD-SEC-002 | P0 | Secret 不 hardcode | 扫描配置和代码 | API key、数据库密码、JWT secret 不在代码中硬编码 |
| TDD-SEC-003 | P0 | SQL 注入基础防护 | keyword/query 输入 SQL 片段 | 不报错、不越权、不泄露数据 |
| TDD-SEC-004 | P0 | 路径穿越文件名 | 上传包含 `../` 的文件名 | 后端规范化或拒绝，不写出 MinIO 预期路径外 |
| TDD-SEC-005 | P0 | XSS 基础防护 | 文档内容或问题包含脚本片段 | 前端按文本展示，不执行脚本 |
| TDD-SEC-006 | P0 | 检索强制过滤 | 绕过前端直接构造请求 | 后端仍强制 knowledge_base_id 过滤 |

⸻

## 7. 自动化测试分层

| 层级 | 工具 | 目标 | 最低要求 |
| --- | --- | --- | --- |
| 后端单元测试 | pytest | services、repositories、schemas、权限依赖 | 核心业务逻辑必须覆盖 |
| 后端集成测试 | pytest + testcontainers 或 Docker Compose | API、数据库、MinIO、Qdrant、Redis | P0 API 必须覆盖 |
| OpenAPI 契约测试 | schemathesis 或等价工具 | 请求/响应结构与 OpenAPI 一致 | P0/P1 接口必须覆盖 |
| 前端单元测试 | Vitest | stores、utils、API client、错误映射 | 鉴权和错误处理必须覆盖 |
| 前端 E2E | Playwright | 登录、管理、上传、问答、反馈 | P0 用户路径必须覆盖 |
| RAG 评估测试 | pytest + 固定样本集 | 检索、引用、拒答、trace | 内测前必须执行 |
| Docker 冒烟 | shell/CI job | 一键启动、健康检查、基础链路 | 每次发布前必须执行 |

⸻

## 8. 验收门槛

### 8.1 第一版基础 Web Demo 可操作验收

当前基础 Demo 可操作验收以 `docs/demo/first-version-demo.md` 为准，最低需要满足：

1. Docker Compose 基础栈可启动。
2. 后端 health 返回正常。
3. 前端登录页可访问。
4. 默认 Admin 可登录并进入主应用。
5. 知识库、文件、用户、审计、Chat SSE 拒答和 feedback 页面可通过真实 API 操作。
6. 当前未配置外部服务时，真实解析/索引/带引用回答缺口必须在 Demo 文档和进度文件中明确记录。
7. 如启用 `DEMO_FIXTURE_ENABLED=true` 并执行 `python -m app.dev.seed_demo_fixture`，可通过受限 Demo fixture 演示 citation UI；该结果不得作为完整真实 RAG 验收。
8. 第一版 Demo 前端 fixture citation 验收步骤以 `docs/demo/frontend-acceptance-checklist.md` 为准。

### 8.2 完整 SDD MVP 进入内测前必须满足

1. 所有 P0 用例通过。
2. P1 用例通过率不低于 95%，未通过项必须有缺陷单和规避说明。
3. Docker Compose 一键启动通过。
4. 样本包中所有 SDD 支持格式文件至少各成功解析 1 个。
5. 样本包中 `.doc/.ppt` 按当前 SDD 返回不支持，不得静默成功。
6. 至少 5 个真实样本问题完成 RAG 问答，回答均包含可回溯引用。
7. 至少 2 个无关问题触发证据不足拒答。
8. 普通 User 无法访问 Admin API、上传、删除、重解析和审计日志。
9. 删除文件后相关 chunks、vectors 和 BM25 documents 不再参与检索。
10. Admin 高危操作进入 audit_logs。

当前状态：完整 SDD MVP 内测门槛尚未满足。真实 MinerU PDF 解析、Qwen embedding、Qdrant 写入、OpenSearch BM25 + IK Analyzer、Qwen reranker、非流式 LLM 带引用回答和 Chat SSE smoke 已通过运行态验证；但前端浏览器 SSE/citation/feedback 全路径、多模态图片召回和完整 RAG 样本评估仍需继续验收。

### 8.3 发布阻断条件

出现以下任一问题，禁止进入内测：

- 任何 P0 用例失败。
- User 可上传、删除或重解析文件。
- 跨知识库检索污染。
- 回答引用不存在、引用未进入 final context，或引用文件名/source_locator 编造。
- 证据不足时仍然自由回答。
- 删除文件后仍可被检索或引用。
- 登录、JWT、密码哈希或 secret 管理存在高危问题。
- Docker Compose 无法启动核心服务。

⸻

## 9. 缺陷分级

| 等级 | 定义 | 示例 |
| --- | --- | --- |
| Blocker | 阻塞启动、登录、上传、检索、问答或安全边界 | Docker 启动失败、Admin 无法登录、跨知识库污染 |
| Critical | 核心功能错误但有局部规避 | 支持格式解析失败、SSE done 丢失、trace 不保存 |
| Major | 主要体验或边界错误 | 错误提示不准确、分页 total 错误 |
| Minor | 轻微展示或低风险问题 | 文案不统一、非核心字段排序问题 |

⸻

## 10. 变更规则

1. SDD 变更后必须评估 TDD 是否同步更新。
2. API 契约变更后必须同步更新接口测试、OpenAPI 契约测试和前端 E2E。
3. 支持文件格式变更后必须同步更新样本包格式状态表和上传测试。
4. RAG 策略变更后必须同步更新检索、引用、拒答和 trace 测试。
5. 每个线上或内测缺陷修复都必须新增或更新至少一个回归用例。

⸻

## 11. 当前注意事项

1. 当前真实样本包包含 `.doc` 和 `.ppt`，但 SDD v0.1 未列为支持格式；测试应按不支持处理。
2. 当前项目已完成第一版基础 Web Demo 的主要页面和真实 API 联调；本 TDD 仍是完整 SDD MVP 的后续实现、自动化测试和内测验收基准。
3. 样本包路径位于 Codex 附件目录，不应假设在其他环境一定存在；CI 环境需要单独配置 `TEST_FIXTURE_ARCHIVE`。
4. 表格文件测试只验证解析、切片、定位和检索，不验证复杂公式、跨表 join、聚合统计或 Text2SQL。
5. 真实 LLM 输出具有波动性，RAG 测试应优先校验证据链、引用结构、拒答策略和 trace，而不是逐字匹配回答文本。
6. 当前已验证的自动化测试结果包括：后端 pytest `42 passed, 60 warnings`、前端 typecheck/build 通过、Compose 配置/服务状态/health 检查通过、后端镜像构建通过、Demo fixture 真实 API citation/feedback smoke 通过。
7. 当前真实外部链路已按 API 化方向补齐 MinerU、embedding、reranker、LLM 配置；OpenSearch BM25 + IK Analyzer 已完成运行态验收并接入混合召回。Step 034 的 Demo fixture 路线只用于历史开发/演示记录，不解除完整 MVP 的真实端到端验收要求。
8. 当前 API contract 已移除未实现的 `/users/me/profile` active path；Profile 页面使用 `/api/v1/auth/me` 只读展示当前用户。
