# Step 045：Queued 解析自动提交与真实文件索引修复

## 1. 本步骤目标

本步骤目标是处理用户反馈的两个运行态问题：

- 用户创建的 `测试` 知识库中，上传文件长期停留在 `queued`。
- 知识库列表中残留多个历史 smoke/readiness 测试知识库，影响当前真实使用。

在排查过程中还发现真实 MinerU 解析已经能完成，但 Qwen 多模态 embedding 和 Qdrant 运行态索引存在适配问题，因此本步骤一并完成最小修复，使当前上传的真实 PDF 能推进到 `indexed`。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：系统应完成上传文件、解析、chunk、embedding、向量索引、检索、问答与引用链路。
- SDD v0.1 1.4：MVP 必须基于真实上传文件和真实解析/索引结果验收，不应依赖 Demo fixture。
- SDD v0.1 2.1.5：文件上传后应创建 `parse_job`，调用 MinerU，保存解析结果，标准化 document blocks，生成 chunks，并写入向量索引。
- 用户当前要求：上传文件一直在 queue，并且知识库中有很多垃圾内容，需要修复运行态问题并清理历史测试数据。
- 用户已确认方向：MinerU、embedding、reranker、LLM 均采用 API 化接入；本步骤继续沿用 Qwen 多模态 embedding provider 抽象，不把模型调用硬编码到业务逻辑中。

## 3. 本步骤完成内容

- 修复文件状态轮询不推进 `queued` parse_job 的问题：
  - `GET /api/v1/files/{file_id}/status` 检测到 latest parse_job 为 `queued` 时，会读取 MinIO raw file 并自动提交 MinerU。
  - 提交成功后推进为 `parsing`，`progress=10`，并写入 MinerU `batch_id/data_id/submit_response`。
  - 提交失败时写入 `MINERU_SUBMIT_FAILED`，文件和 parse_job 进入 `failed`，状态接口不抛出额外 HTTP 错误，便于前端直接展示失败状态。
- 清理运行数据库中的历史测试知识库：
  - 保留用户真实知识库 `测试`。
  - 删除 16 个 `Step... Smoke/Readiness` 历史测试知识库。
  - 按外键依赖顺序删除 conversations、messages、traces、feedback、document_blocks、parse_jobs、files、knowledge_bases。
  - 删除相关 MinIO raw/parsed objects。
- 删除 Qdrant 中旧 Demo fixture collection：
  - 原 `chunks` collection 是早期 fake/demo embedding 创建的 2 维向量结构。
  - 当前真实 Qwen embedding 返回 2560 维，旧 collection 会导致 Qdrant upsert 失败。
  - 确认旧 collection 中 9 个 points 均为已失效 `demo-rag-fixture.txt` 后，删除并由真实索引流程重建为 2560 维。
- 修复 Qwen 多模态 embedding 接入真实索引链路：
  - 新增 `QwenMultimodalTextEmbeddingClient`，让 text chunks 通过既有 `QwenMultimodalEmbeddingProvider` 生成向量。
  - 当 `EMBEDDING_MODEL` 为 Qwen VL 多模态 embedding 模型时，索引链路自动选择该 provider。
  - 显式空 `api_key` 不再被环境变量覆盖，便于测试和错误处理。
- 修复 embedding 批量大小问题：
  - DashScope 返回真实错误：text batch 不能大于 20。
  - 索引阶段改为按 `EMBEDDING_BATCH_SIZE` 分批调用 embedding，当前默认 16。
  - 保持返回向量顺序与 chunk 顺序一致。
- 修复重试索引成功后的旧错误残留：
  - 成功 indexed 后清空 `parse_job.error_code`、`error_message`。
  - 移除旧 `logs.indexing_error`，避免页面显示已 indexed 但仍残留旧错误。
- 对用户当前真实 PDF 完成运行态修复：
  - MinerU 真实解析完成，`mineru_latest_state=done`。
  - 保存 parsed zip 到 MinIO `parsed-results`。
  - 生成 222 个 `document_blocks`。
  - 生成 74 个 active chunks。
  - 通过 Qwen `qwen3-vl-embedding` 生成 2560 维向量。
  - 写入 Qdrant 74 个 points。
  - 文件最终状态为 `indexed`，parse_job 为 `indexed / progress=100`，无错误码。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/files.py` | 修改 | 文件状态轮询遇到 `queued` parse_job 时自动提交 MinerU，并记录提交成功/失败状态 |
| `backend/tests/test_files_api.py` | 修改 | 覆盖上传后状态轮询自动提交 queued parse_job，验证进入 `parsing/progress=10` |
| `backend/app/services/embedding.py` | 修改 | 新增 Qwen 多模态文本 embedding client，并在 Qwen VL 模型配置下接入真实索引链路 |
| `backend/app/rag/embeddings/qwen_multimodal.py` | 修改 | 修正 `api_key` 读取语义：仅 `None` 使用环境配置，显式空字符串按缺 key 处理 |
| `backend/app/services/indexing.py` | 修改 | embedding 按 `EMBEDDING_BATCH_SIZE` 分批请求；成功索引后清理旧错误状态和 `indexing_error` |
| `backend/tests/test_api_model_clients.py` | 修改 | 新增 Qwen text embedding adapter、embedding 分批、成功索引错误清理测试 |
| `docs/progress/step-045-auto-submit-queued-parse-and-runtime-indexing.md` | 新增 | 记录本步骤目标、实现、清理、真实运行验证和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 045 状态、已完成内容、待完成事项和下一步建议 |

## 5. 关键实现说明

- `submit_queued_parse_job()`：
  - 从 MinIO `raw-files` 读取原始上传文件。
  - 复用现有 MinerU API client，完成 batch create、signed PUT 上传和 batch id 记录。
  - 只负责把 `queued` 推进到 `parsing` 或失败，不处理后续 normalizing/chunking/indexing。
- `get_file_status_with_polling()`：
  - 当前状态推进顺序为 `queued -> parsing -> normalizing -> chunking -> embedding -> indexing/indexed`。
  - 每次状态请求只基于当前 latest parse_job 推进可执行阶段，保持现有轮询式后台处理模型。
- `QwenMultimodalTextEmbeddingClient`：
  - 业务层仍依赖 `EmbeddingClientProtocol`。
  - Qwen HTTP 调用仍封装在 `QwenMultimodalEmbeddingProvider` 内。
  - text chunks 会转成 `EmbeddingRequest(input_type="text", content=...)`。
- `embed_texts_in_batches()`：
  - 按 `EMBEDDING_BATCH_SIZE` 将 chunk 文本拆批。
  - 当前配置为 16，满足 DashScope 返回的 “batch size should not be larger than 20” 限制。
  - 多批向量按原顺序拼回，保证后续 chunk 与 vector 一一对应。
- Qdrant 运行态清理：
  - 本步骤删除的是只包含已失效 Demo fixture points 的旧 `chunks` collection。
  - 删除后由索引流程按真实 Qwen 向量维度自动重建 collection。
  - 未删除用户 `测试` 知识库、文件、document blocks 或 chunks。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_api_model_clients.py backend/tests/test_multimodal_embeddings.py backend/tests/test_files_api.py -q` | 通过 | 26 passed；覆盖 queued 自动提交、Qwen provider、embedding 分批和索引错误清理 |
| 后端全量测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 76 passed；仅有既有 JWT key 长度和 TestClient deprecation warning |
| Ruff 检查 | `backend/.venv/bin/python -m ruff check backend/app/services/embedding.py backend/app/services/indexing.py backend/app/rag/embeddings/qwen_multimodal.py backend/tests/test_api_model_clients.py` | 通过 | All checks passed |
| Black 检查 | `backend/.venv/bin/python -m black --check backend/app/services/embedding.py backend/app/services/indexing.py backend/app/rag/embeddings/qwen_multimodal.py backend/tests/test_api_model_clients.py` | 通过 | 4 files would be left unchanged |
| Mypy 检查 | `backend/.venv/bin/python -m mypy backend/app` | 通过 | Success: no issues found in 72 source files |
| 后端重启 | `docker compose up -d --force-recreate backend-api` | 通过 | backend-api 已重新创建并启动 |
| 历史测试知识库清理 | 容器内 SQLAlchemy 清理脚本 | 通过 | 删除 16 个历史 Step/Smoke/Readiness 知识库，当前仅剩 `测试` |
| 旧 Qdrant collection 检查 | Qdrant scroll/count | 通过 | 旧 collection 中 9 个 points 均为 inactive Demo fixture points |
| 旧 Qdrant collection 清理 | Qdrant `DELETE /collections/chunks` | 通过 | 删除旧 2 维 collection，后续索引自动重建 |
| 真实 MinerU 解析状态 | 文件状态轮询 API | 通过 | 当前 PDF 从 `queued` 推进到 MinerU `done`，parsed zip 已保存 |
| 真实 blocks/chunks 生成 | 数据库检查 | 通过 | `document_blocks=222`，`active_chunks=74` |
| 真实 Qwen embedding | 运行态索引脚本 | 通过 | Qwen `qwen3-vl-embedding` 返回 2560 维向量 |
| 真实 Qdrant 写入 | Qdrant collection/count 检查 | 通过 | `chunks` collection 维度 2560，points_count=74 |
| 文件状态 API | Admin 登录后 `GET /api/v1/files/{file_id}/status` | 通过 | 返回 `file_status=indexed`、`parse_status=indexed`、`progress=100`、无错误码 |

## 7. 当前未完成事项

- 当前仅确认真实 PDF 上传到 indexed；尚未完成基于该 indexed 文件的真实 Chat SSE 问答验收。
- 尚未验证 `qwen3-vl-rerank` 的真实 reranker API 契约是否与当前 reranker client 完全兼容。
- 尚未验证 `qwen3.7-plus` 的真实 LLM Chat Completions/SSE 契约是否与当前 LLM client 完全兼容。
- 尚未将 Step 043 的图片 Evidence/ImageBlock 多模态召回骨架接入真实 MinerU assets 和 Chat 主链路。
- 当前状态推进仍依赖前端或接口轮询触发，不是独立后台 worker；这是现有架构边界，后续可单独拆 Step 做任务队列。

## 8. 风险与注意事项

- `.env` 中含真实 API token/key，进度文件和最终回复均不记录密钥值。
- 删除 Qdrant collection 前已确认其中只有 inactive Demo fixture points；如果未来切换 embedding 模型导致维度变化，不能直接删除含真实 active points 的 collection，应先迁移或使用新 collection。
- Qwen 多模态 embedding 真实 batch 限制为最多 20 条 text，本步骤按 16 条分批；如果后续模型限制变化，应调整 `EMBEDDING_BATCH_SIZE`。
- 当前 status endpoint 会在请求时推进任务状态；如果用户长时间不打开页面或不刷新状态，任务不会自动继续到下一阶段。
- 当前只清理历史 Step smoke/readiness 知识库；审计日志中的历史操作记录未清理，因为它们不影响知识库列表，且可作为开发审计轨迹保留。

## 9. 下一步建议

下一步建议进入真实问答验收：

1. 使用当前 `测试` 知识库和已 indexed 的 PDF 发起一个与文档内容相关的问题。
2. 验证 retrieval 能从 74 个真实 chunks 中召回候选。
3. 验证 `qwen3-vl-rerank` 是否能完成候选重排。
4. 验证 `qwen3.7-plus` 是否能通过 Chat SSE 返回带引用编号的回答。
5. 若 reranker 或 LLM API 契约不兼容，按 Step 046 单独适配对应 client，不把问题混到解析/索引阶段。
