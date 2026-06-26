# Step 043：多模态检索路由与图文召回基础骨架

## 1. 本步骤目标

本步骤目标是在不改变现有 Chat/Retrieval 主链路、不新增数据库表、不执行真实 Qwen 在线调用的前提下，完成多模态检索路由与图文召回的基础骨架：

- QueryRouter 输出结构化多标签路由决策。
- Embedding provider 抽象支持 text/image/video。
- Qwen 多模态 embedding 调用被封装在可替换 provider 内。
- ImageBlock/Evidence 以 Pydantic 数据结构预留图片 evidence 与引用字段。
- MultimodalRetriever 支持按 route 调用可注入检索通道。
- Weighted RRF 支持按模态权重融合 evidence。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：文档解析、Chunking、Embedding、检索、Reranker、LLM、引用溯源。
- SDD v0.1 1.4：Vector + Full-text 混合召回、引用必须包含文件名、定位信息和原文片段、证据不足拒答。
- SDD v0.1 2.1.6：每个 chunk 必须生成 `source_locator`，用于引用溯源。
- 用户确认新增方向：多模态检索路由、图片 image/figure evidence、图片 OCR/caption/surrounding text 检索，以及 Qwen 系列多模态 embedding provider 抽象。

说明：本步骤是对 SDD v0.1 文本 RAG 的增强骨架，不替代既有 text chunk 检索、Qdrant、reranker、citation/trace 链路。

## 3. 本步骤完成内容

- 新增 `backend/app/rag/` 包。
- 实现 `RuleBasedQueryRouter`：
  - 默认启用 text + table。
  - 日期、金额、负责人、状态等字段型问题启用 text + table。
  - 架构图、流程图、截图等视觉型问题启用 text + image，并设置 `must_return_visual=true`。
  - 图文混合问题输出 `multimodal_lookup`。
  - 文档级定位问题启用 text + table + image + metadata。
  - 路由结果始终包含 text/table/image/metadata 四个 modality。
- 实现 `LLMQueryRouter` 预留接口和严格 JSON prompt；当前未接真实 LLM router。
- 实现 `BaseEmbeddingProvider`、`EmbeddingRequest`、`EmbeddingResult`。
- 实现 `QwenMultimodalEmbeddingProvider`：
  - 支持 text/image/video request。
  - 默认 endpoint 为 DashScope 多模态 embedding path。
  - 支持 `QWEN_EMBEDDING_MODEL`、`QWEN_API_KEY`、`QWEN_BASE_URL` 配置。
  - 上游失败、响应结构不支持、空向量、向量数量/维度不一致时抛出明确 `ApiError`。
- 实现 `ImageBlock` 和 `Evidence` Pydantic 数据结构。
- 实现 `image_block_to_evidence()`，确保 image evidence source 包含 doc_id、file_name、page、image_path、caption、ocr_text。
- 实现 `MultimodalRetriever`，可注入 text/table/image/metadata 四路 retriever，并根据 route enabled/top_k 调用对应通道。
- 实现 `weighted_rrf_fusion()`，支持按模态权重 RRF 融合、按 evidence_id 去重、重复 evidence 分数累加。
- 新增 20 个单元测试覆盖 QueryRouter、Weighted RRF、Qwen provider 和 MultimodalRetriever。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/core/config.py` | 修改 | 新增 Qwen 多模态 embedding 配置项 |
| `.env` | 修改 | 增加 Qwen embedding 本地环境变量占位 |
| `.env.example` | 修改 | 增加 Qwen embedding 环境变量说明 |
| `backend/app/rag/__init__.py` | 新增 | 新增 RAG 包入口 |
| `backend/app/rag/query_router.py` | 新增 | 新增 RouteDecision schema、规则路由器和 LLM router 预留接口 |
| `backend/app/rag/embeddings/__init__.py` | 新增 | 新增 embedding provider 包入口 |
| `backend/app/rag/embeddings/base.py` | 新增 | 新增 text/image/video embedding provider 抽象 |
| `backend/app/rag/embeddings/qwen_multimodal.py` | 新增 | 新增 Qwen 多模态 embedding provider |
| `backend/app/rag/retriever.py` | 新增 | 新增 ImageBlock、Evidence、MultimodalRetriever 和 image evidence 转换 |
| `backend/app/rag/fusion.py` | 新增 | 新增 Weighted RRF evidence 融合 |
| `backend/tests/test_query_router.py` | 新增 | 覆盖规则路由与 LLM router prompt |
| `backend/tests/test_fusion.py` | 新增 | 覆盖 Weighted RRF 权重、去重和 source 保留 |
| `backend/tests/test_multimodal_embeddings.py` | 新增 | 覆盖 Qwen provider mock 请求、响应解析和错误处理 |
| `backend/tests/test_multimodal_retriever.py` | 新增 | 覆盖按 route 调用通道、融合结果和 image evidence source |
| `docs/progress/step-043-multimodal-query-router-foundation.md` | 新增 | 记录本步骤实现、验证和后续边界 |
| `docs/progress/README.md` | 修改 | 同步 Step 043 总进度 |
| `docs/tests/TDD.v0.1.md` | 修改 | 同步多模态路由与融合测试状态 |

## 5. 关键实现说明

- `RouteDecision` 使用 Pydantic schema，包含 `query`、`intent`、`routes`、`answer_policy` 和 `confidence`。
- `RuleBasedQueryRouter.route()` 采用关键词规则，输出稳定可测试的多标签路由；不会只返回单一 modality。
- `QwenMultimodalEmbeddingProvider` 是唯一包含 Qwen/DashScope HTTP 调用细节的模块，业务层只依赖 `BaseEmbeddingProvider`。
- `ImageBlock` 当前不落数据库；它保留图片资源路径、caption、OCR、surrounding text 和 metadata，供后续真实图片索引使用。
- `MultimodalRetriever` 当前是可注入骨架，不主动读取现有 `ChunkMetadata` 或 Qdrant；后续 Step 045 可把它接入现有 Retrieval/Chat。
- `weighted_rrf_fusion()` 使用公式 `score += route_weight[modality] * 1 / (k + rank)`，默认 `k=60`。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 多模态目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_query_router.py backend/tests/test_fusion.py backend/tests/test_multimodal_embeddings.py backend/tests/test_multimodal_retriever.py -q` | 通过 | 20 passed |
| 后端 lint | `backend/.venv/bin/python -m ruff check backend/app/rag backend/tests/test_query_router.py backend/tests/test_fusion.py backend/tests/test_multimodal_embeddings.py backend/tests/test_multimodal_retriever.py` | 通过 | All checks passed |
| 后端格式检查 | `backend/.venv/bin/python -m black --check backend/app/rag backend/tests/test_query_router.py backend/tests/test_fusion.py backend/tests/test_multimodal_embeddings.py backend/tests/test_multimodal_retriever.py` | 通过 | 11 files would be left unchanged |
| 后端类型检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | Success: no issues found in 72 source files |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 72 passed；仅有既有 TestClient/JWT secret 开发环境 warning |
| 真实 Qwen 在线调用 | 配置 `QWEN_API_KEY` 后执行 | 未执行 | 本步骤使用 MockTransport 测试 provider，不消耗真实 API |
| Chat/Retrieval 端到端 | 接入现有主链路后执行 | 未执行 | 本步骤按确认范围不改变现有 Chat/Retrieval 行为 |

## 7. 当前未完成事项

- 未将 MinerU assets 图片文件真实保存到 MinIO `assets` bucket。
- 未从 MinerU 图片 metadata 生成真实 `ImageBlock`。
- 未将图片向量写入 Qdrant 或独立 image collection。
- 未实现 caption/OCR/surrounding text 的真实 BM25/全文检索索引。
- 未将 `MultimodalRetriever` 接入现有 Retrieval API 或 Chat SSE。
- 未让 answer_policy 控制真实回答行为。
- 未做真实 Qwen API 在线验收。
- 未在前端 citation 中展示图片预览。

## 8. 风险与注意事项

- 本步骤是多模态基础骨架，不代表图文召回端到端已完成。
- Qwen provider 当前采用可配置 HTTP endpoint 和兼容型响应解析；真实供应商 payload/response 如有差异，需要在 provider 内适配，不应污染业务逻辑。
- `ImageBlock` 当前仅为 Pydantic 数据结构，不具备持久化和索引能力。
- 现有 Chat/Retrieval 主链路保持不变，因此当前页面问答体验不会因为本步骤自动具备图片召回能力。
- 多模态方向是用户确认后的新增增强，后续进度文件需继续注明其与 SDD 原文文本 RAG 要求的边界。

## 9. 下一步建议

建议进入 Step 044：真实图片资产与 ImageBlock 生成。

原因：Step 043 已具备 QueryRouter、Evidence、Embedding provider 和融合骨架；下一步应从 MinerU zip/assets/metadata 中提取图片资源，保存到 MinIO `assets` bucket，并生成可持久化或可索引的真实 ImageBlock，为后续图片向量索引和 Chat 接入做准备。
