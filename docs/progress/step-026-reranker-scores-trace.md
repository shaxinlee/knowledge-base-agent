# Step 026：补齐 message trace 中的 reranker_scores

## 1. 本步骤目标

补齐 Chat 消息 trace 中的 reranker 分数字段，将 Retrieval/Chat 重排后的每个 chunk score 保存到 `message_traces.reranker_scores`，提升 RAG trace、feedback telemetry 和后续端到端验收的可追溯性。

## 2. 对应 SDD 条目

- SDD v0.1：问答链路需要保存 trace，用于追踪 query、retrieved chunks、final context、citations、模型和检索链路信息。
- TDD v0.1：
  - `TDD-INDEX-007`：Reranker 重排后，`reranked_chunk_ids` 和 `reranker_scores` 写入 trace。
  - `TDD-CHAT-007`：完成一次问答后保存 query_text、retrieved_chunk_ids、reranked_chunk_ids、final_context_chunk_ids、final_cited_chunk_ids 等。

## 3. 本步骤完成内容

- 将 assistant message trace 的 `reranked_chunk_ids` 从 `None` 改为当前 Retrieval 返回的重排后 chunk id 列表。
- 新增 `build_reranker_scores()`，将 Retrieval 返回的重排后结果转换为 `{chunk_id: score}` 结构并保存到 `message_traces.reranker_scores`。
- 扩展 conversation API fake reranker 测试，使 fake reranker 可注入固定分数。
- 更新 conversation API 测试断言，验证 trace 中写入 `reranked_chunk_ids` 和 `reranker_scores`。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/conversations.py` | 修改 | 在创建 assistant message trace 时保存 reranked_chunk_ids 和 reranker_scores |
| `backend/tests/test_conversations_api.py` | 修改 | 扩展 FakeRerankerClient，增加 trace reranker_scores 断言 |
| `docs/progress/step-026-reranker-scores-trace.md` | 新增 | 记录 Step 026 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 026 状态、已完成内容、风险和下一步建议 |

## 5. 关键实现说明

- 当前 Retrieval API 在 vector/full-text merge 后调用 reranker，并将重排分数作为 `RetrievalResultItem.score` 返回。
- Chat 创建 assistant message 时复用该结果：
  - `reranked_chunk_ids` 保存重排后的 chunk id 顺序。
  - `reranker_scores` 保存 `{chunk_id: score}`，便于后续 trace 调试和 telemetry 扩展。
- 空知识库或无可检索 chunks 时，Retrieval 返回空列表，`reranked_chunk_ids` 保存为空列表，`reranker_scores` 保存为空对象，不触发 embedding/Qdrant/reranker 外部调用。
- 本步骤不改变前端响应结构，不新增数据库 migration，因为 `message_traces.reranker_scores` 字段已经存在。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_conversations_api.py::test_user_can_create_conversation_and_send_non_stream_message_with_citation -q` | 通过 | 1 passed；验证 trace 写入 reranked_chunk_ids 和 reranker_scores |
| 格式检查 | `backend/.venv/bin/black --check backend/app/services/conversations.py backend/tests/test_conversations_api.py` | 通过 | 2 files would be left unchanged |
| Lint 检查 | `backend/.venv/bin/ruff check backend/app backend/tests` | 通过 | All checks passed |
| 类型检查 | `backend/.venv/bin/mypy backend/app` | 通过 | Success: no issues found in 62 source files |
| 后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 37 passed, 56 warnings |
| Docker Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 数据库迁移检查 | 未执行 | 未执行 | 本步骤未修改数据库结构，`reranker_scores` 字段已存在 |
| 前端构建测试 | 未执行 | 未执行 | 本步骤未修改前端代码 |

## 7. 当前未完成事项

- 真实 reranker-service 在线重排仍未验证。
- 当前 `retrieved_chunk_ids` 与 `reranked_chunk_ids` 都来自 Retrieval 返回的最终可展示结果；若后续需要严格区分“重排前候选集”和“重排后候选集”，需要扩展 Retrieval service 的内部 trace 输出。
- Feedback response 当前仍只返回模型信息，不返回 reranker_scores；如后续需要 bad case 分析页面展示分数，可在 feedback telemetry schema 中扩展。

## 8. 风险与注意事项

- 本步骤不改变回答质量，不接入真实 LLM，也不解除 Step 016 的真实端到端人工确认项。
- `reranker_scores` 当前是 JSON 对象，key 为 chunk id，value 为 score；后续如接入不同 reranker 返回更多 metadata，需要保持向后兼容。
- 当前运行中的 backend-api 容器健康检查通过，但容器内代码是否已热加载取决于 Compose 挂载和服务状态；本步骤的可靠验证以本地 venv 测试结果为准。

## 9. 下一步建议

建议进入 Step 027：实现当前用户删除自己 conversation 的后端接口。

原因：`TDD-CONV-003` 是当前 TDD 已记录的未完成项，范围独立、可测试、可回滚；完成后可以补齐会话生命周期闭环，并为前端历史会话管理留下清晰接口基础。
