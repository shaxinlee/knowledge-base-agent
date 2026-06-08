# Step 020：Helpful/Unhelpful 反馈基础能力

## 1. 本步骤目标

本步骤目标是在 Step 019 Profile/Auth 状态真实化完成后，补齐 SDD MVP 中不依赖外部模型服务的反馈能力：每条 assistant message 可提交 helpful / unhelpful 反馈，并保存用于 bad case 分析的基础 telemetry。

完成后，系统支持：

- 创建 `feedback` 表。
- `POST /api/v1/messages/{message_id}/feedback`。
- 只允许对自己的 assistant message 提交反馈。
- 不允许对 user message 提交反馈。
- 同一用户对同一 assistant message 重复提交时更新同一条反馈。
- 反馈保存 query_text、retrieved_chunk_ids、final_cited_chunk_ids、model/prompt/embedding/reranker 信息。
- Chat 页面展示 helpful / unhelpful 反馈按钮。

本步骤不实现 bad case 查询接口，不处理真实 MinerU 解析、embedding-service、reranker、LLM 或 SSE。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `21. 支持 helpful / unhelpful 反馈`。
- `4.13 feedback`：
  - `message_id`
  - `user_id`
  - `knowledge_base_id`
  - `rating`
  - `comment`
  - `query_text`
  - `retrieved_chunk_ids`
  - `final_cited_chunk_ids`
  - `model_name`
  - `prompt_version`
  - `embedding_model`
  - `reranker_model`
  - `latency_ms`
  - `token_input`
  - `token_output`
  - `created_at`
- `6.10 Feedback API`：
  - `POST /api/v1/messages/{message_id}/feedback`
  - 请求体包含 `rating` 和 `comment`。
- `13.7 Phase 7：反馈与 Bad Case 积累`：
  - 本步骤完成 feedback 表、POST feedback API、前端反馈按钮和 telemetry 保存。
  - 基础 bad case 查询接口在 SDD 中为可选，本步骤暂不实现。

## 3. 本步骤完成内容

- 新增后端模型：
  - `Feedback`
  - `FeedbackRating`
- 新增 migration：
  - `0009_create_feedback`
  - 创建 `feedback` 表。
  - 增加 rating check constraint。
  - 增加 `message_id + user_id` 唯一约束。
  - 增加 message 和 knowledge_base/rating 索引。
- 新增后端 schema：
  - `FeedbackCreateRequest`
  - `FeedbackResponse`
- 新增后端 service：
  - `create_or_update_feedback()`
  - 校验 message 存在且属于当前用户。
  - 校验 message role 必须为 assistant。
  - 从 conversation 读取 knowledge_base_id。
  - 从 message_trace 读取 query/retrieval/citation/model telemetry。
  - 重复提交时更新同一条反馈。
- 新增后端 API：
  - `POST /api/v1/messages/{message_id}/feedback`
- 新增测试：
  - assistant message 可提交 feedback。
  - feedback 保存 trace telemetry。
  - 同一 message 重复反馈会更新，不会新增重复记录。
  - user message 提交反馈返回 `422 VALIDATION_ERROR`。
- 前端接入：
  - API client 新增 `submitMessageFeedback()`。
  - Chat 页面每条 assistant message 展示“有帮助 / 没帮助”按钮。
  - 提交成功后高亮当前 rating。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/models/feedback.py` | 新增 | 新增 `Feedback` 模型和 `FeedbackRating` 枚举 |
| `backend/app/models/__init__.py` | 修改 | 导出 Feedback 相关模型 |
| `backend/migrations/versions/0009_create_feedback.py` | 新增 | 创建 feedback 表、约束和索引 |
| `backend/app/schemas/feedback.py` | 新增 | 新增 feedback request/response schema |
| `backend/app/services/feedback.py` | 新增 | 新增反馈校验、upsert 和 telemetry 保存逻辑 |
| `backend/app/api/v1/feedback.py` | 新增 | 新增 message feedback API endpoint |
| `backend/app/api/v1/router.py` | 修改 | 注册 Feedback router |
| `backend/tests/test_conversations_api.py` | 修改 | 增加 feedback API 测试 |
| `frontend/src/api/client.ts` | 修改 | 新增 `submitMessageFeedback()` API 封装 |
| `frontend/src/views/ChatView.vue` | 修改 | assistant message 增加 helpful/unhelpful 反馈按钮 |
| `docs/progress/step-020-feedback-basics.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 020 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 反馈对象边界：
  - 只能对 `role=assistant` 的 message 提交反馈。
  - message 必须属于当前用户。
  - conversation 也必须属于当前用户。
- upsert 语义：
  - `feedback` 表对 `(message_id, user_id)` 建唯一约束。
  - 如果同一用户重复提交同一条 assistant message 的反馈，则更新已有记录。
  - 这样页面上“有帮助 / 没帮助”代表当前最终反馈状态。
- telemetry：
  - `query_text`、`retrieved_chunk_ids`、`final_cited_chunk_ids`、`embedding_model`、`reranker_model` 来自 `message_traces`。
  - `model_name` 和 `prompt_version` 优先来自 `messages`，缺失时回退到 trace。
  - `latency_ms`、`token_input`、`token_output` 来自 `messages`。
- 前端展示：
  - Chat 页面不要求 comment 输入，当前仅提交 rating。
  - 后端 API 仍支持 comment，真实 smoke 已覆盖 comment 写入。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式化 | `backend/.venv/bin/black backend/app backend/tests backend/migrations` | 通过 | 80 files left unchanged |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 70 个 source files 无类型错误 |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| 容器内 migration | `docker compose run --rm --no-deps -e JWT_SECRET_KEY=dev-only-change-me-please-32-bytes-min backend-api alembic upgrade head` | 通过 | 成功从 `0008_conversations_messages` 升级到 `0009_create_feedback` |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 35 passed，1 个 Starlette/httpx deprecation warning |
| Feedback API smoke | 使用 `backend/.venv/bin/python` 调用登录、创建知识库、创建 conversation、发送 message、提交 helpful、更新 unhelpful | 通过 | 登录 200、创建知识库 201、创建会话 201、发送消息 200、feedback helpful 201、feedback unhelpful 201 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |

## 7. 当前未完成事项

- 未实现 feedback 列表或 bad case 查询接口；SDD 中该项为可选。
- Chat 页面当前只提交 rating，不提供 comment 输入框。
- feedback telemetry 中 reranker/token/latency 仍受当前非流式模板 Demo 限制，真实值需要后续 LLM/reranker 接入。
- 真实 MinerU 在线解析仍缺少 `MINERU_API_TOKEN`。
- 真实 embedding-service 仍未接入。
- Chat 仍是非流式 JSON Demo，不是 SSE/LLM。

## 8. 风险与注意事项

- 当前 feedback API 与 message ownership 绑定，Admin 不默认给他人 conversation/message 提交反馈，符合前序会话隔离策略。
- 当前 Chat 页面没有在加载 conversation 详情时回显历史 feedback 状态，因为后端 message response 尚未包含 feedback_summary；后续可补。
- Step 016 的真实解析索引端到端人工确认项仍未解除。

## 9. 下一步建议

建议回到 Step 016 的人工确认项，选择真实端到端或开发 Demo fixture 路线：

- 路线 A：提供 `MINERU_API_TOKEN`，并提供或允许新增真实 embedding-service，继续真实上传 -> MinerU API -> 标准化 -> chunking -> embedding -> Qdrant -> Chat citation 验证。
- 路线 B：确认允许实现明确标记为开发 Demo 的 seed/fixture 路径，用于生成可检索 chunks 并验证 Chat citation 展示；该路径不得伪装成真实 MinerU 解析结果。

原因：

- 到本步骤为止，不依赖外部模型服务的 MVP 前后端能力已经基本补齐。
- 剩余最影响第一版 Demo 质量的是“带引用回答”的真实或明确 Demo 化索引数据来源。
