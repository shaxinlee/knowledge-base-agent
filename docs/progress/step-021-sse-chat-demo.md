# Step 021：Chat SSE 流式 Demo

## 1. 本步骤目标

本步骤目标是在 Step 020 feedback 基础能力完成后，补齐 SDD MVP 中的 Chat SSE 流式返回能力，让 `POST /api/v1/conversations/{conversation_id}/messages` 在 `stream=true` 时返回 `text/event-stream`，并让前端 Chat 页面使用流式事件逐步展示回答。

本步骤实现的是模板化 Demo SSE：

- SSE 协议、事件流和前端流式渲染是真实的。
- 检索、message/citation/trace 保存仍复用当前后端逻辑。
- answer 内容仍来自当前模板化 demo，不是真实 LLM token streaming。

本步骤不处理真实 LLM、reranker、真实 MinerU 在线解析、真实 embedding-service 或真实带引用索引数据来源。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `16. SSE 流式返回回答`。
  - `17. 回答必须带引用编号`。
  - `18. 引用必须包含文件名、定位信息和原文片段`。
  - `19. 证据不足时必须拒答`。
  - `20. 保存会话、消息、引用、trace`。
- `2.3 问答生成流`：
  - `SSE streaming answer`
  - `create assistant message`
  - `create citations`
  - `create message_trace`
- `6.9 Messages / Chat API`：
  - `POST /api/v1/conversations/{conversation_id}/messages`
  - 请求 `stream=true`
  - 响应为 SSE stream。
  - 最终完成事件包含 `message_id`、`answer`、`citations`。
- `13.6 Phase 6：RAG 问答与引用溯源`：
  - 本步骤完成 SSE streaming demo；真实 LLM 和 reranker 仍待后续服务接入。

## 3. 本步骤完成内容

- 后端 Chat endpoint 支持双模式：
  - `stream=false`：继续返回原 `MessageCreateResponse` JSON。
  - `stream=true`：返回 `text/event-stream`。
- 后端新增 SSE 事件：
  - `message_created`：返回 `user_message` 和空内容的 `assistant_message`。
  - `retrieval`：返回 retrieved/final context 数量。
  - `token`：按固定 chunk size 流式返回 answer 片段。
  - `done`：返回最终 `message_id`、完整 `answer` 和 `citations`。
- 后端保持原有数据保存行为：
  - user message 保存。
  - assistant message 保存。
  - citations 保存。
  - message_trace 保存。
- 前端 API client 新增 POST SSE 解析：
  - 使用 `fetch` + `ReadableStream`，因为 EventSource 不支持 POST。
  - 解析 `event:` 和 `data:`。
  - 分发到 `onMessageCreated`、`onRetrieval`、`onToken`、`onDone`。
- 前端 Chat 页面改为使用 `stream=true`：
  - 收到 `message_created` 后追加 user message 和空 assistant message。
  - 收到 `token` 后逐步拼接 assistant content。
  - 收到 `done` 后设置最终 answer 和 citations。
  - helpful/unhelpful feedback 按钮继续可用。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/api/v1/conversations.py` | 修改 | `stream=true` 时返回 SSE；新增 SSE event 构造和 token chunking |
| `backend/tests/test_conversations_api.py` | 修改 | 新增 SSE message 测试，验证 message_created/retrieval/token/done 事件与数据保存 |
| `frontend/src/api/types.ts` | 修改 | 更新 `SseMessageCreatedEvent` 类型，包含 user/assistant message |
| `frontend/src/api/client.ts` | 修改 | 新增 `streamConversationMessage()` 和 SSE parser |
| `frontend/src/views/ChatView.vue` | 修改 | Chat 发送消息切换为 SSE 流式展示 |
| `docs/progress/step-021-sse-chat-demo.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 021 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- SSE endpoint：
  - 仍使用同一个 `POST /conversations/{conversation_id}/messages`。
  - endpoint 根据 `payload.stream` 决定返回 JSON 或 `StreamingResponse`。
  - `StreamingResponse` 使用 `text/event-stream`。
- 数据保存时机：
  - 当前 demo 在开始发送 SSE 事件前完成检索、answer 构造和 DB commit。
  - 因此 SSE 传输失败不会导致半写入的 message/citation/trace。
  - 后续真实 LLM token streaming 可改为边生成边写最终 assistant message。
- token 分片：
  - 当前按固定长度拆分模板 answer，模拟 token 流式展示。
  - 这不是 LLM token streaming，不代表最终模型响应行为。
- 前端解析：
  - POST SSE 使用 `fetch` 读取 `response.body.getReader()`。
  - 按 `\n\n` 分隔 SSE event。
  - `done` 事件负责最终覆盖完整 answer 和 citations，避免 token 拼接误差。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式化 | `backend/.venv/bin/black backend/app backend/tests backend/migrations` | 通过 | `conversations.py` 被格式化，其余文件保持不变 |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 70 个 source files 无类型错误 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 36 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| SSE API smoke | 使用 `backend/.venv/bin/python` 调用登录、创建知识库、创建 conversation、`stream=true` 发送消息 | 通过 | 返回 `text/event-stream`；包含 `message_created`、`token`、`done`；空知识库拒答文本存在 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |

## 7. 当前未完成事项

- SSE 当前流式传输的是模板化 demo answer，不是真实 LLM token。
- `retrieval` event 当前只返回数量，不返回详细 trace。
- 当前仍未接入 reranker-service。
- 当前仍未接入真实 LLM Provider。
- 当前仍未配置 `MINERU_API_TOKEN`。
- 当前仍未接入真实 embedding-service。
- 当前仍缺少真实带引用 indexed chunks 的端到端演示数据。

## 8. 风险与注意事项

- 当前 SSE 实现为了 Demo 稳定性，在开始 stream 前已经完成 DB commit；真实 LLM streaming 可能需要不同的事务策略。
- 前端使用 POST + fetch stream，自定义解析 SSE；若后续服务端增加 error event，需要补前端 error 分支。
- 当前空知识库路径仍会拒答，这是正确的 SDD 行为。
- Step 016 的真实解析索引端到端人工确认项仍未解除。

## 9. 下一步建议

建议回到 Step 016 的人工确认项，选择真实端到端或开发 Demo fixture 路线：

- 路线 A：提供 `MINERU_API_TOKEN`，并提供或允许新增真实 embedding-service，继续真实上传 -> MinerU API -> 标准化 -> chunking -> embedding -> Qdrant -> Chat citation 验证。
- 路线 B：确认允许实现明确标记为开发 Demo 的 seed/fixture 路径，用于生成可检索 chunks 并验证 Chat citation 展示；该路径不得伪装成真实 MinerU 解析结果。

原因：

- 到本步骤为止，Chat 页面已具备 SSE 流式协议、拒答、feedback、conversation/message/trace 保存。
- 剩余最影响第一版 Demo 质量的是“真实或明确 Demo 化的带引用数据来源”。
