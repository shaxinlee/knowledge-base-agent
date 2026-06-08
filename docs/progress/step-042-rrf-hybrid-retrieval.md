# Step 042：混合检索 RRF 策略补齐

## 1. 本步骤目标

本步骤目标是补齐 Step 040 进度文件中记录的混合检索算法缺口：将 Vector + Full-text 的候选合并从简单 score 相加升级为 RRF（Reciprocal Rank Fusion）策略，并将默认召回规模对齐到用户确认计划中的 vector topK 50、full-text topK 50、rerank top 20。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：完整 RAG 链路中的向量检索、PostgreSQL 全文检索、Reranker 重排。
- SDD v0.1 1.4：实现 Vector + Full-text 混合召回，使用 Reranker 重排。
- 用户确认的 Step 040 算法策略：Qdrant vector topK 建议 50，PostgreSQL full-text topK 建议 50，合并算法使用 RRF，默认 `k=60`，对 hybrid merged top 20 执行 reranker。

## 3. 本步骤完成内容

- 将 `merge_candidates` 改为接收 vector/full-text 两组候选并按 RRF 计算合并分数。
- RRF 默认参数设置为 `k=60`。
- 同一 chunk 同时被 vector 与 full-text 命中时，结果来源标记为 `hybrid`。
- 将进入 reranker 的候选上限固定为 merged top 20。
- 将 Retrieval API 默认 `vector_top_k` 从 30 调整为 50。
- 将 Retrieval API 默认 `full_text_top_k` 从 30 调整为 50。
- 新增 RRF 合并行为测试，验证排序、分数和 `hybrid` source 标记。
- 更新既有检索测试，验证默认 vector search limit 已变为 50。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/retrieval.py` | 修改 | 新增 RRF 常量、rerank 候选上限，并将混合召回合并逻辑升级为 RRF |
| `backend/app/schemas/retrieval.py` | 修改 | 将 `vector_top_k` 与 `full_text_top_k` 默认值调整为 50 |
| `backend/tests/test_retrieval_api.py` | 修改 | 新增 RRF 合并单元测试，并同步默认 vector search limit 断言 |
| `docs/progress/step-042-rrf-hybrid-retrieval.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 042 状态和当前总体进度 |

## 5. 关键实现说明

核心逻辑位于 `backend/app/services/retrieval.py`：

- `RRF_K = 60`：按用户确认计划设定 RRF 默认平滑参数。
- `RERANK_CANDIDATE_LIMIT = 20`：只将 hybrid merged top 20 送入 reranker，避免对过多候选执行昂贵重排。
- `merge_candidates(vector_candidates, full_text_candidates)`：
  - 分别遍历 vector 与 full-text 候选列表。
  - 使用候选在各自列表中的名次计算 `1 / (k + rank)`。
  - 同一 `chunk_id` 多路命中时累加 RRF 分数。
  - 多路命中 source 标记为 `hybrid`。
  - 最终按 RRF 分数降序进入 reranker。

注意：Retrieval API 最终返回给前端的 `score` 仍来自 reranker 分数；RRF 分数主要用于决定送入 reranker 前的候选顺序。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 检索专项测试 | `backend/.venv/bin/python -m pytest backend/tests/test_retrieval_api.py -q` | 通过 | 4 passed，覆盖 RRF、hybrid source、知识库过滤和 reranker 排序 |
| 后端 lint | `backend/.venv/bin/python -m ruff check backend/app/services/retrieval.py backend/app/schemas/retrieval.py backend/tests/test_retrieval_api.py` | 通过 | All checks passed |
| 后端格式检查 | `backend/.venv/bin/python -m black --check backend/app/services/retrieval.py backend/app/schemas/retrieval.py backend/tests/test_retrieval_api.py` | 通过 | 3 files would be left unchanged |
| 后端类型检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | Success: no issues found in 65 source files |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 52 passed；仅有既有 TestClient/JWT secret 开发环境 warning |
| 前端类型与构建 | `npm run typecheck && npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` Rolldown pure annotation warning，不影响产物 |
| 真实 API 在线验收 | 配置 MinerU/embedding/reranker/LLM API 后执行 | 未执行 | 本步骤为本地算法补齐，不解除 Step 041 外部配置缺口 |

## 7. 当前未完成事项

- 未执行真实 MinerU 在线解析。
- 未执行真实 embedding/reranker/LLM API 在线调用。
- 未执行真实上传文件到带引用回答的端到端验收。
- 未将 Chat SSE 改造成真正边接收 LLM token 边落库；当前 SSE 事件格式保持原有行为。

## 8. 风险与注意事项

- RRF 改变的是 reranker 前的候选排序，不直接代表最终回答质量；最终质量仍依赖真实 embedding、full-text、reranker 和 LLM。
- 当前 SQLite 测试环境的 full-text 逻辑是兼容性实现，生产 PostgreSQL 路径使用 `websearch_to_tsquery` 与 `ts_rank`。
- 默认召回从 30/30 提升到 50/50 会增加一次检索和 reranker 前处理的候选规模，但最终 reranker 上限为 20，风险可控。
- Step 041 仍处于“需要人工确认”，因为真实外部 API 配置仍缺失。

## 9. 下一步建议

下一步仍建议回到 Step 041：配置真实 `MINERU_API_TOKEN`、embedding API、reranker API 和 LLM API 后，重新执行真实 `.pdf/.docx/.txt` 上传解析、parsed-results 保存、blocks/chunks 生成、embedding API 索引、Qdrant 写入、User 提问、reranker API、LLM SSE、citation、feedback 和 trace 回显。
