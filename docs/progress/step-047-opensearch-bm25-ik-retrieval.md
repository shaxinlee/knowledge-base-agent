# Step 047：OpenSearch BM25 中文关键词召回 + IK Analyzer

## 1. 本步骤目标

本步骤目标是把当前 PostgreSQL `simple` full-text 关键词召回升级为 OpenSearch BM25 中文关键词召回，并使用 IK Analyzer 做中文分词。

目标链路为：

```text
Qwen Embedding + Qdrant 向量召回 top 50
+
OpenSearch BM25 + IK Analyzer 中文关键词召回 top 50
↓
RRF 融合
↓
Qwen Reranker 重排 top 20
↓
LLM 带引用回答
```

本步骤当前状态：已完成。

代码实现、自动化测试、静态检查和运行态 OpenSearch + IK Analyzer 验证均已完成。当前 `测试` 知识库 74 个 active chunks 已回填到 `chunks_bm25`，精确关键词 Retrieval/Chat/SSE smoke 已通过。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：RAG 主链路需要完成向量召回、全文召回、Reranker 重排、引用回答。
- SDD v0.1 8.4：chunks embedding 与全文检索索引构建。
- SDD v0.1 9：检索与问答流程，包括 Qdrant vector search、全文检索、混合召回、Reranker。
- 用户确认的新增方向：将关键词召回从 PostgreSQL `simple` full-text 升级为 OpenSearch BM25 + IK Analyzer 中文分词；索引分词固定 `ik_max_word`，搜索分词固定 `ik_smart`。

说明：SDD 原文要求 PostgreSQL tsvector 全文检索。本步骤保留 PostgreSQL full-text 作为 `BM25_ENABLED=false` 时的 fallback，但当 `BM25_ENABLED=true` 时正式使用 OpenSearch BM25 作为关键词召回通道。这是用户确认后的实现方向变更。

## 3. 本步骤完成内容

- 新增 OpenSearch BM25 client 抽象：
  - `BM25ChunkDocument`
  - `BM25SearchHit`
  - `BM25IndexClientProtocol`
  - `OpenSearchBM25IndexClient`
  - `DisabledBM25IndexClient`
  - `get_bm25_index_client()`
- 新增 OpenSearch index mapping：
  - index name：`chunks_bm25`
  - index analyzer：`ik_max_word`
  - search analyzer：`ik_smart`
  - 检索字段：`content^3`、`heading_path^2`、`file_name`
  - filter：`knowledge_base_id`、`is_active=true`
- 新增 Compose OpenSearch 单节点服务：
  - service name：`opensearch`
  - internal URL：`http://opensearch:9200`
  - local/dev security disabled
  - heap：1g
  - data volume：`opensearch-data`
- 新增 IK Analyzer Dockerfile 和自定义词典：
  - `opensearch/ik/custom.dic`
  - `opensearch/ik/stopword.dic`
  - `opensearch/ik/IKAnalyzer.cfg.xml`
  - `opensearch/ik/main.dic`
  - `opensearch/ik/surname.dic`
  - `opensearch/ik/quantifier.dic`
  - `opensearch/ik/suffix.dic`
  - `opensearch/ik/preposition.dic`
- OpenSearch 镜像构建修复：
  - GitHub release 插件下载在当前环境超时，已切换为 `https://get.infini.cloud/opensearch/analysis-ik/2.18.0`。
  - 补齐 IK 插件需要的默认词典文件。
  - 修复 Docker `COPY` 后词典文件权限，确保 OpenSearch 进程可读取。
- 新增 BM25 环境变量：
  - `BM25_ENABLED`
  - `BM25_PROVIDER`
  - `BM25_BASE_URL`
  - `BM25_INDEX_NAME`
  - `BM25_TOP_K`
  - `BM25_INDEX_ANALYZER`
  - `BM25_SEARCH_ANALYZER`
- 索引链路接入 BM25：
  - `index_parse_job()` 在 Qdrant collection ensure 后调用 `bm25_index_client.ensure_index()`。
  - active chunks 同步构造成 Qdrant points 和 BM25 documents。
  - 写入 Qdrant 后写入 BM25。
  - BM25 upsert 失败会按严格策略标记 parse_job/file failed。
  - PostgreSQL `tsv` 写入保留，作为 fallback 兼容能力。
- Retrieval 链路替换关键词召回来源：
  - `BM25_ENABLED=true` 时使用 OpenSearch BM25 search。
  - `BM25_ENABLED=false` 时回退现有 PostgreSQL/SQLite full-text。
  - API response shape 保持不变，仍返回 `source: vector | full_text | hybrid`。
  - 现有 RRF、reranker、citation/trace 主链路保持不变。
- 文件删除链路接入 BM25 失效：
  - 删除 indexed 文件时同步调用 `bm25_index_client.deactivate_chunks()`。
  - BM25 documents 只置 `is_active=false`，不物理删除。
  - 删除审计日志补充 BM25 失效数量、provider 和 index。
- 测试补齐：
  - BM25 client mapping/upsert/search mock 测试。
  - Retrieval 在 BM25 enabled 时调用 BM25 client 的测试。
  - Files parse/index 成功时写入 BM25 documents 的测试。
  - 删除 indexed 文件时 BM25 documents 失效的测试。
  - Conversations API 默认注入 fake BM25，避免 `.env` 启用 BM25 时单元测试误连真实 OpenSearch。
- 运行态验收补齐：
  - OpenSearch 2.18.0 已启动。
  - `analysis-ik 2.18.0` 插件已加载。
  - `chunks_bm25` index 已创建。
  - `_analyze` 已验证 `ik_max_word` / `ik_smart` 可切出领域词。
  - 当前 `测试` 知识库 74 个 active chunks 已写入 BM25。
  - BM25 直接搜索、Retrieval API、Chat 非流式 API、Chat SSE API 和 message trace 已通过 smoke。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/bm25_index.py` | 新增 | 新增 BM25 client 抽象、OpenSearch 实现、IK mapping、bulk upsert、search、deactivate 和 dependency provider |
| `backend/app/core/config.py` | 修改 | 新增 BM25/OpenSearch 配置项 |
| `backend/app/services/indexing.py` | 修改 | 索引阶段构造并写入 BM25 documents，保留 PostgreSQL tsv fallback |
| `backend/app/services/retrieval.py` | 修改 | 新增 `search_keyword_candidates()`，BM25 enabled 时用 OpenSearch，否则回退 PostgreSQL/SQLite full-text |
| `backend/app/services/files.py` | 修改 | 文件状态索引推进和删除文件失效链路接入 BM25 client |
| `backend/app/services/conversations.py` | 修改 | Chat 检索链路传入 BM25 client |
| `backend/app/api/v1/files.py` | 修改 | Files API 注入 BM25 client |
| `backend/app/api/v1/retrieval.py` | 修改 | Retrieval API 注入 BM25 client |
| `backend/app/api/v1/conversations.py` | 修改 | Conversations message API 注入 BM25 client |
| `backend/tests/test_api_model_clients.py` | 修改 | 新增 OpenSearch BM25 mapping/upsert/search mock 测试 |
| `backend/tests/test_retrieval_api.py` | 修改 | 新增 fake BM25 client 和 BM25 enabled 检索测试 |
| `backend/tests/test_files_api.py` | 修改 | 新增 fake BM25 client 默认注入、索引写入和删除失效断言 |
| `backend/tests/test_conversations_api.py` | 修改 | 新增 fake BM25 client 默认注入，避免测试误连真实 OpenSearch |
| `docker-compose.yml` | 修改 | 新增 `opensearch` 服务、volume 和 backend-api BM25/OpenSearch 依赖配置 |
| `.env.example` | 修改 | 新增 BM25/OpenSearch 占位配置，不包含真实密钥 |
| `.env` | 修改 | 当前本地启用 BM25/OpenSearch 默认配置；真实密钥未写入文档 |
| `opensearch/Dockerfile` | 新增 | 构建安装 IK Analyzer 的 OpenSearch 镜像；使用 `get.infini.cloud` 插件源，补齐词典权限 |
| `opensearch/ik/IKAnalyzer.cfg.xml` | 新增 | 声明 IK 自定义词典和停用词文件 |
| `opensearch/ik/custom.dic` | 新增 | 预置项目领域词 |
| `opensearch/ik/stopword.dic` | 新增 | 预留停用词文件 |
| `opensearch/ik/main.dic` | 新增 | IK 主词典，包含项目领域词 |
| `opensearch/ik/surname.dic` | 新增 | IK 初始化所需姓氏词典 |
| `opensearch/ik/quantifier.dic` | 新增 | IK 初始化所需量词词典 |
| `opensearch/ik/suffix.dic` | 新增 | IK 初始化所需后缀词典 |
| `opensearch/ik/preposition.dic` | 新增 | IK 初始化所需介词词典 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 将 Retrieval 说明从 PostgreSQL full-text 更新为 OpenSearch BM25 + PostgreSQL fallback |
| `docs/tests/TDD.v0.1.md` | 修改 | 补充 BM25/OpenSearch/IK 测试状态和运行态验收结果 |
| `docs/progress/step-047-opensearch-bm25-ik-retrieval.md` | 新增 | 记录本步骤实现、验证和下一步 |
| `docs/progress/README.md` | 修改 | 同步 Step 047 状态、已完成内容、注意事项和下一步建议 |
| `README.md` | 修改 | 同步 Retrieval 当前关键词召回方向 |

## 5. 关键实现说明

- `OpenSearchBM25IndexClient.ensure_index()`：
  - 先 `GET /chunks_bm25`。
  - 不存在时 `PUT /chunks_bm25` 创建 index。
  - mapping 中 `content`、`file_name`、`heading_path` 使用自定义 analyzer：`kb_ik_index` / `kb_ik_search`。
- `OpenSearchBM25IndexClient.upsert_chunks()`：
  - 使用 `_bulk` 写入 document。
  - 文档 `_id` 固定为 `chunk_id`，便于幂等 upsert。
  - bulk 返回 `errors=true` 时抛出 `ApiError`，不静默失败。
- `OpenSearchBM25IndexClient.search()`：
  - 使用 `bool.filter` 限定 `knowledge_base_id` 和 `is_active=true`。
  - 使用 `multi_match` 搜索 `content^3`、`heading_path^2`、`file_name`。
  - 返回统一 `BM25SearchHit(chunk_id, score, raw)`。
- `search_keyword_candidates()`：
  - 统一封装关键词召回来源。
  - BM25 enabled 时返回 `source="full_text"` 的 BM25 candidates。
  - BM25 disabled 时保留旧 PostgreSQL/SQLite full-text candidates。
- 删除策略：
  - Qdrant points 和 BM25 documents 均采用逻辑失效。
  - 删除 API 当前采用严格策略：BM25 deactivation 失败会返回上游错误，不让 UI 误以为文件已彻底删除。
- IK 自定义词典：
  - 第一版预置 `井下落鱼`、`可视化工具`、`光电复合缆`、`防爆计算机`、`地面控制工具`、`井下工具`、`VONETS`、`LED控制`。
  - 已新增 `IKAnalyzer.cfg.xml` 声明 `custom.dic` 和 `stopword.dic`。
- IK 插件来源：
  - 原计划引用的 GitHub release 源在当前网络下超时。
  - 本步骤改用 `get.infini.cloud` 的 `opensearch/analysis-ik/2.18.0` 下载源，版本仍固定为 2.18.0，并已通过 `_cat/plugins` 和 `_analyze` 验证。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| BM25 目标后端测试 | `backend/.venv/bin/python -m pytest backend/tests/test_api_model_clients.py backend/tests/test_retrieval_api.py backend/tests/test_files_api.py backend/tests/test_conversations_api.py -q` | 通过 | 35 passed；仅既有 warning |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 80 passed；仅既有 TestClient/JWT warning |
| Ruff 检查 | `backend/.venv/bin/python -m ruff check backend/app/services/bm25_index.py backend/app/services/indexing.py backend/app/services/retrieval.py backend/app/services/files.py backend/app/api/v1/files.py backend/app/api/v1/retrieval.py backend/app/api/v1/conversations.py backend/tests/test_api_model_clients.py backend/tests/test_retrieval_api.py backend/tests/test_files_api.py backend/tests/test_conversations_api.py` | 通过 | All checks passed |
| Black 检查 | `backend/.venv/bin/python -m black --check backend/app/services/bm25_index.py backend/app/services/indexing.py backend/app/services/retrieval.py backend/app/services/files.py backend/app/api/v1/files.py backend/app/api/v1/retrieval.py backend/app/api/v1/conversations.py backend/tests/test_api_model_clients.py backend/tests/test_retrieval_api.py backend/tests/test_files_api.py backend/tests/test_conversations_api.py` | 通过 | 11 files would be left unchanged |
| Mypy 检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | Success: no issues found in 74 source files |
| Python 语法检查 | `backend/.venv/bin/python -m compileall -q backend/app` | 通过 | 无输出表示通过 |
| Compose 配置检查 | `docker compose config` | 通过 | Compose 可解析，包含 `opensearch-data` volume 和 OpenSearch service |
| OpenSearch 镜像构建 | `docker compose build opensearch` | 通过 | 基础镜像为 OpenSearch 2.18.0；IK 插件使用 `get.infini.cloud/opensearch/analysis-ik/2.18.0` 安装 |
| OpenSearch 本地服务检查 | `curl -fsS http://localhost:9200` | 通过 | OpenSearch 2.18.0 正常返回版本信息 |
| IK 插件验证 | `curl -fsS http://localhost:9200/_cat/plugins?v` | 通过 | 输出包含 `analysis-ik 2.18.0` |
| Analyzer 验证 | `POST /chunks_bm25/_analyze` | 通过 | `ik_smart` 输出 `井下落鱼`、`可视化工具`、`光电复合缆`、`地面控制工具` |
| 真实 PDF BM25 回填 | 后端容器内读取 active chunks 并调用 `bm25_index_client.upsert_chunks()` | 通过 | 当前 `测试` 知识库 74 个 active chunks 已写入 `chunks_bm25` |
| BM25 文档数量验证 | `curl -fsS http://localhost:9200/chunks_bm25/_count?pretty` | 通过 | count = 74 |
| BM25 直接搜索 | OpenSearch `_search` 查询 `VONETS_2.4G_5D98 的密码是什么？` | 通过 | 命中包含密码 `12345678` 的真实 chunk |
| Retrieval API smoke | `POST /api/v1/knowledge-bases/{id}/retrieval/search` | 通过 | 四个关键词问题均返回真实 chunks，source 为 `hybrid` |
| Chat 非流式 API smoke | `POST /api/v1/conversations/{id}/messages`，`stream=false` | 通过 | 回答 `VONETS_2.4G_5D98 的密码是“12345678”`，返回 6 条 citations |
| Chat SSE API smoke | `POST /api/v1/conversations/{id}/messages`，`stream=true` | 通过 | 返回 `message_created`、`retrieval`、`token`、`done` 事件和 citations |
| Trace 验证 | 查询 `message_traces` | 通过 | 保存 retrieved/reranked/final cited chunk ids，并记录 Qwen embedding/reranker/LLM 模型 |
| Compose 服务状态 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio、opensearch 均运行 |
| OpenSearch 拉取后服务复验 | `docker compose ps`、`curl -fsS http://localhost:9200/_cat/plugins?v`、`curl -fsS http://localhost:9200/chunks_bm25/_count?pretty`、`POST /chunks_bm25/_analyze` | 通过 | OpenSearch healthy，`analysis-ik 2.18.0` 可见，`chunks_bm25` count = 74，IK 可识别领域词 |
| OpenSearch 拉取后关键词复验 | OpenSearch `_search` 查询 `VONETS_2.4G_5D98 的密码是什么？` | 通过 | 命中真实 PDF chunk，内容包含 `VONETS_2.4G_5D98` 与密码 `12345678` |
| 后端 BM25 配置复验 | 后端容器内读取 `get_settings()` | 通过 | `BM25_ENABLED=true`，provider 为 `opensearch`，base URL 为 `http://opensearch:9200`，index 为 `chunks_bm25` |
| OpenSearch 拉取后目标回归 | `backend/.venv/bin/python -m pytest backend/tests/test_api_model_clients.py backend/tests/test_retrieval_api.py backend/tests/test_files_api.py backend/tests/test_conversations_api.py -q` | 通过 | 35 passed；仅既有 warning |
| OpenSearch 拉取后 Ruff 复验 | `backend/.venv/bin/python -m ruff check backend/app/services/bm25_index.py backend/app/services/indexing.py backend/app/services/retrieval.py backend/app/services/files.py backend/app/services/conversations.py backend/app/api/v1/files.py backend/app/api/v1/retrieval.py backend/app/api/v1/conversations.py backend/tests/test_api_model_clients.py backend/tests/test_retrieval_api.py backend/tests/test_files_api.py backend/tests/test_conversations_api.py` | 通过 | All checks passed |

## 7. 当前未完成事项

- 未执行浏览器手动点击验收；本步骤已通过 HTTP API 验证 Retrieval、非流式 Chat 和 SSE Chat。
- 未新增 BM25 回填的独立管理接口或后台任务；本次对历史 74 个 chunks 使用一次性脚本回填，后续新解析文件会在 indexing 阶段自动写入 BM25。
- OpenSearch 当前为单节点 dev 配置，cluster health 为 yellow 是因为 replica 未分配；主分片可用，不影响本地开发验证。后续可在 index settings 中把 replicas 设为 0。

## 8. 风险与注意事项

- 当前 `.env` 已设置 `BM25_ENABLED=true`，backend-api 已重启并确认配置生效。
- IK Analyzer 插件版本必须与 OpenSearch 版本兼容。本步骤固定 `OpenSearch 2.18.0` 与 `analysis-ik 2.18.0`。
- 原 GitHub release 插件源在当前环境超时；已改用 `get.infini.cloud` 源，并记录在 Dockerfile。
- 本步骤没有删除 PostgreSQL `tsv` 字段和旧 full-text 逻辑；当 `BM25_ENABLED=false` 时仍可 fallback。
- BM25 enabled 时按严格策略处理上游失败，不做静默降级。这会提高验收可信度，但 OpenSearch 不可用时会影响解析索引和检索。
- `.env` 中包含真实 token/key，未写入进度文档和 `.env.example`。

## 9. 下一步建议

下一步建议进入 Step 048：真实前端问答体验与 BM25 可视化验收。

建议验证：

1. 浏览器登录 Admin。
2. 进入 `测试` 知识库。
3. 在对话页面提问 `VONETS_2.4G_5D98 的密码是什么？`。
4. 确认 SSE 流式回答、引用详情、feedback 回显正常。
5. 如需要更强可观测性，可在 trace/detail 或调试接口中展示关键词召回来源、BM25 命中 chunk ids 和 RRF 合并结果。
