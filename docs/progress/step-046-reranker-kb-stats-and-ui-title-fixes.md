# Step 046：真实问答 Reranker、知识库统计与顶部标题修复

## 1. 本步骤目标

本步骤目标是修复用户反馈的三个当前运行态 bug：

- 新建问答后向模型提问，后端返回 `UPSTREAM_SERVICE_ERROR: Reranker API request failed.`。
- 除文件库和对话问答页面外，其他页面左上角仍显示硬编码的 `2024 年度财务报告知识库`。
- 当前知识库已有真实 chunks，但知识库管理页面仍显示文件数和 Chunk 总数为 0。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：完整 RAG 链路需要 embedding、Qdrant 检索、Reranker 重排、LLM 生成回答和引用溯源。
- SDD v0.1 1.4：MVP 需要完成真实上传文件到带引用回答的端到端链路。
- SDD v0.1 13.5：检索结果需要经过 Reranker 重排，并保存 reranked chunk ids / reranker scores。
- SDD v0.1 前端验收要求：知识库、文件、对话等页面应展示真实后端数据，不能保留无关 Demo/硬编码业务内容。
- 用户当前要求：修复真实问答 reranker 报错、修改顶部标题、修复知识库 chunks 统计展示。

## 3. 本步骤完成内容

- 修复 DashScope / Qwen reranker API 契约：
  - 当前旧 client 请求 `{RERANKER_API_BASE_URL}/rerank`，在 `https://dashscope.aliyuncs.com/compatible-mode/v1` 下返回 404。
  - 本步骤新增 `DashScopeTextRerankerClient`，请求 DashScope text rerank endpoint：`/api/v1/services/rerank/text-rerank/text-rerank`。
  - 请求体使用 `model + input.query + input.documents + parameters.return_documents=false`。
  - 解析 DashScope 返回的 `output.results[].relevance_score`。
  - 当 base URL 指向 DashScope 或 model 为 Qwen 系列时，自动选择 DashScope reranker client。
- 修复知识库统计：
  - `KnowledgeBaseResponse.file_count` 不再固定为 0，改为统计当前知识库中未删除文件数量。
  - `KnowledgeBaseResponse.chunk_count` 不再固定为 0，改为统计当前知识库中 active chunks 数量。
  - 列表接口和详情接口均返回真实统计。
- 修复前端顶部标题：
  - `AppLayout` 默认左上角从 `2024 年度财务报告知识库` 改为 `Agent-Assistant`。
  - 文件管理和对话问答页面已有自定义 top-left slot，不受影响。
- 完成真实运行态 smoke：
  - 知识库列表接口返回 `测试`：`file_count=1`、`chunk_count=74`。
  - Retrieval API 成功召回真实 PDF chunks。
  - 新建 conversation 后提问成功，不再出现 reranker 上游错误。
  - LLM 返回带引用编号的回答，citation 包含真实文件名、source locator、excerpt 和 chunk id。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/reranker.py` | 修改 | 新增 DashScope text reranker client、DashScope endpoint/payload 适配、`relevance_score` 解析和自动 provider 选择 |
| `backend/app/services/knowledge_bases.py` | 修改 | 知识库 response 返回真实 file_count 和 active chunk_count |
| `backend/tests/test_api_model_clients.py` | 修改 | 新增 DashScope reranker endpoint、payload 和 `relevance_score` 解析测试 |
| `backend/tests/test_knowledge_bases_api.py` | 修改 | 新增知识库列表/详情真实文件数和 active chunk 数统计测试 |
| `frontend/src/components/AppLayout.vue` | 修改 | 默认顶部标题从硬编码财务报告知识库改为 `Agent-Assistant` |
| `docs/progress/step-046-reranker-kb-stats-and-ui-title-fixes.md` | 新增 | 记录本步骤目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 046 状态、已完成内容、注意事项和下一步建议 |

## 5. 关键实现说明

- `DashScopeTextRerankerClient`：
  - 从 `RERANKER_API_BASE_URL` 只提取 scheme + host，例如 `https://dashscope.aliyuncs.com/compatible-mode/v1` 会归一化为 `https://dashscope.aliyuncs.com`。
  - 固定调用 DashScope text rerank endpoint，避免继续请求不存在的 compatible `/rerank`。
  - 仍实现 `RerankerClientProtocol`，Retrieval/Chat 主链路无需改造。
- `parse_reranker_scores()`：
  - 保留原有 `scores` 和 `results[].score` 兼容。
  - 新增 `output.results[].relevance_score` 兼容，用于 DashScope/Qwen reranker。
- 知识库统计：
  - `file_count` 统计 `files.deleted_at is null`。
  - `chunk_count` 统计 `chunks_metadata.is_active=true`，并 join `files` 排除已删除文件。
  - 当前未限制 chunk 只统计 indexed 文件，因为 active chunks 本身就是索引/解析链路写入的可见数据；后续如需更严格口径，可增加 `File.status=indexed`。
- 前端标题：
  - 只改默认 top-left slot，不影响 Chat/Files 页面现有上下文标题。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| DashScope reranker 真实 endpoint 探测 | 容器内最小 HTTP 请求 | 通过 | `/compatible-mode/v1/rerank` 返回 404；DashScope text rerank endpoint 返回 200 和 `relevance_score` |
| 后端目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_api_model_clients.py backend/tests/test_knowledge_bases_api.py backend/tests/test_retrieval_api.py backend/tests/test_conversations_api.py -q` | 通过 | 25 passed |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 78 passed；仅有既有 JWT key 长度和 TestClient deprecation warning |
| Ruff 检查 | `backend/.venv/bin/python -m ruff check backend/app/services/reranker.py backend/app/services/knowledge_bases.py backend/tests/test_api_model_clients.py backend/tests/test_knowledge_bases_api.py` | 通过 | All checks passed |
| Black 检查 | `backend/.venv/bin/python -m black --check backend/app/services/reranker.py backend/app/services/knowledge_bases.py backend/tests/test_api_model_clients.py backend/tests/test_knowledge_bases_api.py` | 通过 | 4 files would be left unchanged |
| Mypy 检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | Success: no issues found |
| Python 语法检查 | `backend/.venv/bin/python -m compileall -q backend/app` | 通过 | 无输出表示通过 |
| 前端 lint | `npm run lint` | 通过 | ESLint 通过 |
| 前端 typecheck/build | `npm run typecheck && npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` Rolldown pure annotation warning，不影响产物 |
| 后端重启 | `docker compose up -d --force-recreate backend-api` | 通过 | backend-api 已重新创建并启动 |
| 服务状态检查 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均运行 |
| 知识库统计 API smoke | Admin 登录后 `GET /api/v1/knowledge-bases` | 通过 | `测试` 返回 `file_count=1`、`chunk_count=74` |
| Retrieval API smoke | `POST /api/v1/knowledge-bases/{id}/retrieval/search` | 通过 | 成功返回真实 PDF chunk 结果，无 reranker 错误 |
| Chat API smoke | 创建 conversation 后 `POST /messages stream=false` | 通过 | 成功返回带 `[1]` 引用的回答和 citations，无 reranker 错误 |

## 7. 当前未完成事项

- 本步骤修复了非流式 Chat API smoke；仍建议后续补跑前端页面中的 SSE 交互路径，确认 UI 流式渲染、citation 展示和 feedback 提交都正常。
- `docs/demo/first-version-demo.md` 等旧 Demo 文档仍有历史 fixture 边界说明，未在本步骤全面重写。
- 多模态图片召回仍未接入真实 Chat 主链路。
- 知识库统计当前通过列表响应实时计算；后续数据量较大时可考虑缓存或聚合表，但当前不提前扩展架构。

## 8. 风险与注意事项

- DashScope Qwen reranker 当前使用 text rerank endpoint，已通过真实最小请求验证；如果后续切换到图片/多模态 rerank，需要新增 multimodal rerank provider，而不是复用 text endpoint。
- 本步骤没有改动用户上传文件、chunks 或 Qdrant points。
- `.env` 中真实 API key/token 未写入文档。
- `file_count/chunk_count` 已改为真实统计，页面可能需要刷新一次才能看到最新数字。

## 9. 下一步建议

下一步建议进入 Step 047：真实前端问答体验验收与引用展示收口。

原因：后端真实 Retrieval + Reranker + LLM 非流式 smoke 已经通过，下一步应从用户浏览器路径验证：

1. 在 Chat 页面选择 `测试` 知识库。
2. 发起与 PDF 相关的问题。
3. 确认 SSE 流式回答不报错。
4. 确认回答显示引用编号。
5. 确认 citation detail 能展示文件名、source locator 和 excerpt。
6. 提交 helpful/unhelpful feedback 并回显。
