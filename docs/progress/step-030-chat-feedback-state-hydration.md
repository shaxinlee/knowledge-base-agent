# Step 030：Chat 历史消息回显 feedback 状态

## 1. 本步骤目标

补齐 Chat 历史会话重新打开后的 helpful/unhelpful 状态回显能力，使当前用户已提交过的 assistant message feedback 能在 conversation detail 中返回，并在前端按钮状态中恢复。

## 2. 对应 SDD 条目

- SDD v0.1：保存会话、消息、引用、trace 和反馈。
- SDD v0.1：前端核心页面需要支持问答、引用展示和反馈。
- TDD v0.1：
  - `TDD-CONV-002`：获取 conversation detail 返回 messages 和 citations。
  - `TDD-FB-001`：helpful 反馈关联 message_trace。
  - `TDD-FB-002`：unhelpful 反馈保存 rating/comment。
  - `TDD-FB-003`：重复反馈更新原反馈，不重复创建。
- Step 020 风险记录：Chat 页面加载历史 conversation 时尚不回显已提交 feedback 状态。

## 3. 本步骤完成内容

- 在后端 `MessageResponse` 中新增可空字段 `feedback_rating`。
- `GET /api/v1/conversations/{conversation_id}` 批量加载当前用户对返回 messages 的 feedback rating。
- conversation detail 中：
  - user message 的 `feedback_rating` 为 `null`。
  - 无反馈 assistant message 的 `feedback_rating` 为 `null`。
  - 已反馈 assistant message 的 `feedback_rating` 为 `helpful` 或 `unhelpful`。
- 更新 conversation API 测试，验证 feedback upsert 后重新读取 conversation detail 能回显最新 rating。
- 更新前端 `Message` 类型，新增 `feedback_rating`。
- Chat 页面打开历史 conversation 后调用 `syncFeedbackState()`，将 assistant message 的 `feedback_rating` 写入本地按钮状态。
- 提交 feedback 成功后同步更新当前 `messages` 中对应 message 的 `feedback_rating`，避免后续局部刷新时状态丢失。
- 同步中文 API contract、OpenAPI 和前端类型。
- 更新 Demo/TDD 当前状态说明。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/schemas/conversations.py` | 修改 | `MessageResponse` 新增 `feedback_rating` |
| `backend/app/services/conversations.py` | 修改 | conversation detail 批量加载当前用户 feedback rating，并写入 message response |
| `backend/tests/test_conversations_api.py` | 修改 | 增加历史 conversation detail 回显 feedback rating 断言 |
| `frontend/src/api/types.ts` | 修改 | `Message` 类型新增 `feedback_rating` |
| `frontend/src/views/ChatView.vue` | 修改 | 打开历史会话时同步 feedback 按钮状态，提交 feedback 后更新 message 状态 |
| `docs/api/frontend-backend-api-contract.md` | 修改 | Message 示例补充 `feedback_rating` |
| `docs/api/openapi.v0.1.yaml` | 修改 | Message schema 补充 nullable `feedback_rating` |
| `docs/demo/first-version-demo.md` | 修改 | Feedback 演示流程补充历史会话回显 |
| `docs/tests/TDD.v0.1.md` | 修改 | 更新会话与反馈当前状态 |
| `docs/progress/step-030-chat-feedback-state-hydration.md` | 新增 | 记录 Step 030 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 030 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- `feedback_rating` 是当前登录用户视角字段，不暴露其他用户的 feedback。
- 后端按 message ids 和 current_user.id 批量查询 `feedback` 表，避免逐条 message 查询。
- 当前字段只回显 rating，不回显 comment；comment 管理和 bad case 查询仍属于后续可选能力。
- 前端回显逻辑只影响按钮激活状态，不改变 message 内容、citations 或 trace。
- SSE 新建消息路径也会返回 `feedback_rating: null`，与非流式 JSON 和历史 detail 响应保持一致。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_conversations_api.py::test_user_can_submit_feedback_for_assistant_message_with_trace_telemetry -q` | 通过 | 1 passed；验证 feedback upsert 后 conversation detail 回显最新 `unhelpful` |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app/schemas/conversations.py backend/app/services/conversations.py backend/tests/test_conversations_api.py` | 通过 | 3 files would be left unchanged |
| 后端 Lint | `backend/.venv/bin/ruff check backend/app backend/tests` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app` | 通过 | Success: no issues found in 62 source files |
| 后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 38 passed, 58 warnings |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| OpenAPI YAML 解析 | `backend/.venv/bin/python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('docs/api/openapi.v0.1.yaml').read_text())"` | 通过 | OpenAPI YAML 可解析 |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端服务可访问 |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 源码关键字扫描 | `rg -n 'feedback_rating|syncFeedbackState|load_feedback_ratings_for_messages|Feedback' ...` | 通过 | 后端 schema/service/test、前端类型/页面、API contract/OpenAPI 均可定位 |

## 7. 当前未完成事项

- Feedback comment 仍不在历史消息中回显。
- Feedback bad case 查询接口尚未实现；SDD 中该项为可选。
- 真实带引用回答仍依赖 MinerU API token、embedding-service、reranker-service 和 LLM Provider。
- 前端尚未配置 Playwright E2E 测试。

## 8. 风险与注意事项

- `feedback_rating` 是新增响应字段，前端类型和契约已同步；老客户端如果忽略该字段不受影响。
- 当前只按当前用户回显 rating，不提供跨用户统计。
- 既有测试 warning 仍存在：Starlette/httpx deprecation warning 与开发环境 JWT secret 过短 warning；本步骤未处理这些非阻塞项。

## 9. 下一步建议

建议进入 Step 031：用户管理操作审计日志写入。

原因：TDD 中 `TDD-AUDIT-003` 仍记录为未完成项，当前 Users API 的禁用、启用、重置密码等高风险管理操作尚未写入 audit_logs。该步骤范围清晰、可测试，并能增强 Demo 的管理操作可追溯性。
