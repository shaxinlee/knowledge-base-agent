# Step 013：Phase 6-A 非流式 Chat Demo 基础

## 1. 本步骤目标

本步骤目标是在 Step 012 检索基础 API 之上，完成第一版后端 Chat Demo 闭环：

- 创建 conversation。
- 保存 user message。
- 复用 retrieval service 检索 chunks。
- 生成模板化 assistant answer。
- 保存 assistant message。
- 保存 message citations。
- 保存 message trace。
- 证据不足时返回拒答模板。

本步骤暂不实现真实 LLM、SSE streaming、reranker 和 feedback。

## 2. 对应 SDD 条目

- `4.9 conversations`：会话固定绑定 `knowledge_base_id`，用户只能查看自己的会话。
- `4.10 messages`：保存 user/assistant/system 消息。
- `4.11 message_citations`：assistant message 可有多个 citation，citation 必须关联真实 chunk。
- `4.12 message_traces`：保存 query_text、retrieved_chunk_ids、final_context_chunk_ids、final_cited_chunk_ids、embedding_model、chat_model、prompt_version 等。
- `13.6 Phase 6：RAG 问答与引用溯源`：本步骤完成 conversation/message/citation/trace 基础和证据不足拒答模板；SSE、真实 LLM、Prompt 和最终 grounded answer 留待后续。
- `docs/tests/TDD.v0.1.md`：
  - `TDD-CHAT-004`：引用结构包含 file_name、source_locator、excerpt、chunk_id。本步骤已覆盖基础 citation 结构。
  - `TDD-CHAT-006`：证据不足拒答。本步骤实现无检索结果时的拒答模板。
  - `TDD-CHAT-007`：保存 trace。本步骤保存 retrieved/final chunk ids 与模型信息。

## 3. 本步骤完成内容

- 新增数据库模型：
  - `Conversation`
  - `Message`
  - `MessageCitation`
  - `MessageTrace`
- 新增 migration `0008_conversations_messages`：
  - `conversations`
  - `messages`
  - `message_citations`
  - `message_traces`
- 新增 Conversations API：
  - `GET /api/v1/conversations?knowledge_base_id=<kb_id>`
  - `POST /api/v1/conversations`
  - `GET /api/v1/conversations/{conversation_id}`
  - `POST /api/v1/conversations/{conversation_id}/messages`
- 新增非流式 Chat Demo：
  - 当前 `POST /conversations/{conversation_id}/messages` 返回 JSON。
  - 请求 `stream=false` 或不传 `stream` 时，返回 `user_message` 与 `assistant_message`。
  - 复用 Step 012 retrieval service 检索当前 conversation 绑定的 knowledge base。
  - 有检索结果时生成模板化回答，并在正文中使用 `[1]`、`[2]` 等引用编号。
  - 无检索结果时生成拒答模板。
  - 保存 assistant message citations。
  - 保存 message trace。
- 会话访问控制：
  - 用户只能读取自己的 conversation。
  - 其他用户访问返回 `404 RESOURCE_NOT_FOUND`。
- 同步契约：
  - 更新 `frontend/src/api/types.ts`，新增 `MessageCreateResponse`，并将 `MessageCreateRequest.stream` 调整为可选 boolean。
  - 更新 `docs/api/frontend-backend-api-contract.md`，说明当前 Phase 6-A demo 的非流式 JSON 响应。
  - 更新 `docs/api/openapi.v0.1.yaml`，将消息接口当前响应补充为 `MessageCreateResponse`。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/conversation.py` | 新增 | 新增 `Conversation` 与 `ConversationStatus` |
| `backend/app/models/message.py` | 新增 | 新增 `Message`、`MessageCitation`、`MessageTrace` 和 `MessageRole` |
| `backend/app/models/__init__.py` | 修改 | 导出 conversation/message 相关模型 |
| `backend/migrations/versions/0008_create_conversations_messages.py` | 新增 | 新增 conversations/messages/citations/traces 表 |
| `backend/app/schemas/conversations.py` | 新增 | 新增 conversation/message/citation Pydantic schemas |
| `backend/app/services/conversations.py` | 新增 | 新增会话列表/创建/详情/消息发送、模板回答、citation/trace 保存逻辑 |
| `backend/app/api/v1/conversations.py` | 新增 | 新增 Conversations API endpoints |
| `backend/app/api/v1/router.py` | 修改 | 注册 Conversations router |
| `backend/tests/test_conversations_api.py` | 新增 | 覆盖创建会话、发送消息、citation/trace 保存、用户隔离 |
| `frontend/src/api/types.ts` | 修改 | 同步非流式 message response 类型 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | 补充 Phase 6-A 非流式 demo 响应说明 |
| `docs/api/openapi.v0.1.yaml` | 修改 | 补充 `MessageCreateResponse` 和消息接口 JSON 响应 |
| `docs/progress/step-013-non-stream-chat-demo.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 013 状态和下一步建议 |

## 5. 关键实现说明

- 非流式 demo：
  - SDD 最终要求 SSE streaming 与真实 LLM。
  - 本步骤为了形成第一版可演示闭环，先实现 `stream=false` JSON 响应。
  - 后续 Step 014 可在保留当前数据结构的基础上增加 SSE。
- 模板化回答：
  - 有检索结果时，assistant content 使用检索 excerpt 构造回答，每条 excerpt 带 `[n]` 编号。
  - citation rows 与正文编号一致。
  - 无检索结果时，使用证据不足拒答模板。
- trace：
  - `retrieved_chunk_ids` 保存本次 retrieval 返回的 chunk ids。
  - `final_context_chunk_ids` 与 `final_cited_chunk_ids` 当前使用前 6 个 retrieval results。
  - `embedding_model` 来自 embedding client。
  - `chat_model` 当前记录为 `template-demo`。
- 会话隔离：
  - `require_user_conversation()` 强制 `conversation.user_id == current_user.id`。
  - Admin 当前也不默认读取他人会话，符合 SDD “Admin 不默认读取用户私人会话”的约束。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式化 | `backend/.venv/bin/black backend/app backend/tests backend/migrations` | 通过 | migration 和 conversations service 被格式化 |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | 无 lint 问题 |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 66 个 source files 无类型错误 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 33 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| OpenAPI YAML 解析 | 使用 PyYAML 读取 `docs/api/openapi.v0.1.yaml` | 通过 | YAML 可解析 |
| 后端 Docker 构建 | `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple backend-api` | 通过 | 后端镜像构建成功 |
| 容器内 migration | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 成功从 `0007_chunks_metadata` 升级到 `0008_conversations_messages` |
| 容器内后端测试 | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api pytest` | 通过 | 33 passed，1 个 Starlette/httpx deprecation warning |
| PostgreSQL migration 版本检查 | `select version_num from alembic_version;` | 通过 | 当前版本为 `0008_conversations_messages` |
| PostgreSQL 表检查 | `\dt conversations/messages/message_citations/message_traces` | 通过 | 四张新表均存在 |
| 完整 Compose 启动 | `docker compose up -d` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均启动 |
| 后端健康检查 | `curl http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端启动检查 | `curl -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| Qdrant 健康检查 | `curl http://localhost:6333/collections` | 通过 | Qdrant 服务正常 |
| 真实 LLM/SSE 验证 | 真实模型服务 + SSE 流式回答 | 未执行 | 本步骤明确不接真实 LLM/SSE |

## 7. 当前未完成事项

- 未实现 SSE streaming。
- 未实现真实 LLM Provider 调用。
- 未实现 reranker-service。
- 未实现 helpful/unhelpful feedback。
- 未实现前端 Chat 页面接真实接口。
- 未实现真实 embedding-service 容器，因此真实上传文件后的完整 MinerU/embedding/Qdrant/chat 端到端仍需后续环境补齐。

## 8. 风险与注意事项

- 当前回答是模板化 demo，不是 LLM 生成回答，不能代表最终回答质量。
- 当前 citations 来自 retrieval top results，尚未经过 reranker 和 final context selection。
- 当前 `stream=true` 目标仍未实现；API contract 已注明 Phase 6-A 当前是非流式 JSON demo。
- 当前 trace 已保存基础字段，但 latency/token/prompt snapshot 仍是占位或空值。

## 9. 下一步建议

建议进入 Step 014：前端 Chat Demo 联调或 SSE/LLM 二选一。

如果目标是尽快看到第一版 demo 页面，建议 Step 014 优先前端联调：

- Chat 页面调用 Conversations API。
- 创建/选择 conversation。
- 发送 `stream=false` 消息。
- 展示 assistant answer 与 citations。
- 在引用中显示 file_name、source_locator、excerpt。

如果目标是更贴近 SDD 完整后端，则 Step 014 优先 SSE：

- 将 `POST /conversations/{id}/messages` 增加 `stream=true` SSE 分支。
- 事件包含 `message_created`、`retrieval`、`token`、`done`、`error`。
- 复用当前 message/citation/trace 保存逻辑。
