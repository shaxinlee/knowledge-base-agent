# Step 024：API Contract / OpenAPI / 前端类型一致性核对

## 1. 本步骤目标

核对当前后端实现、文字 API contract、OpenAPI 和前端 TypeScript 类型之间的差异，并同步已经实现的接口契约，减少第一版 Demo 交接时的文档/类型偏差。

本步骤不新增业务功能，不修改后端业务逻辑，不接入真实 MinerU、embedding-service、reranker-service 或 LLM。

## 2. 对应 SDD 条目

- SDD v0.1 API 边界：前后端应基于统一接口契约联调。
- SDD v0.1 MVP：Chat SSE、feedback、retrieval/reranker、auth、profile 展示等 Demo 能力需要清晰契约。
- README 当前规则：任何 API change 必须同步 readable API contract、OpenAPI、frontend types 和相关 TDD。

## 3. 本步骤完成内容

- 核对后端当前路由和 schema：
  - `/auth/logout`
  - `/auth/me`
  - `/conversations/{conversation_id}/messages`
  - `/messages/{message_id}/feedback`
  - `/knowledge-bases/{knowledge_base_id}/retrieval/search`
- 更新文字 API contract：
  - Retrieval API 从“未接 reranker”改为“merge 后调用 reranker-service 重排”。
  - Chat API 从“stream=true 后续目标”改为“当前已支持 `stream=true` SSE”。
  - SSE `message_created` event 改为当前实现的 `user_message` + `assistant_message` 对象结构。
  - Feedback response 补充 telemetry 字段：`user_id`、`knowledge_base_id`、`query_text`、`retrieved_chunk_ids`、`final_cited_chunk_ids`、`model_name`、`prompt_version`、`embedding_model`、`reranker_model`、`latency_ms`、`token_input`、`token_output`、`updated_at`。
  - 将未实现的 `/users/me/profile` 标记为当前未实现，并说明 Profile 页面当前使用 `/auth/me`。
  - 修正 Audit Logs 章节编号。
- 更新 OpenAPI：
  - 移除当前未实现的 `/users/me/profile` path。
  - 移除当前未使用的 `UserProfile` / `UserProfileUpdateRequest` schema。
  - 为 `POST /conversations/{conversation_id}/messages` 增加 `text/event-stream` 响应描述和 SSE 示例。
  - 为 `MessageCreateRequest.content` 补充 `minLength=1`、`maxLength=8000`。
  - 扩展 `Feedback` schema，与后端 `FeedbackResponse` 对齐。
- 更新前端类型：
  - 删除当前未实现且未使用的 `UserProfile` / `UserProfileUpdateRequest`。
  - 扩展 `Feedback` interface，与后端 response 对齐。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| docs/api/frontend-backend-api-contract.md | 修改 | 同步 Retrieval reranker、Chat SSE、Feedback telemetry、Profile 当前边界和章节编号 |
| docs/api/openapi.v0.1.yaml | 修改 | 同步 SSE response、Feedback schema，移除未实现 profile path/schema |
| frontend/src/api/types.ts | 修改 | 同步 Feedback response 类型，移除未实现 profile 类型 |
| docs/progress/step-024-api-contract-sync.md | 新增 | 记录本步骤目标、内容、验证结果和后续建议 |
| docs/progress/README.md | 修改 | 更新总进度索引、已完成内容和下一步建议 |

## 5. 关键实现说明

- 当前 Profile 页面只读展示来自 `GET /api/v1/auth/me`，不是 `/users/me/profile`。
- 当前 `stream=true` 返回 `text/event-stream`，事件包括：
  - `message_created`
  - `retrieval`
  - `token`
  - `done`
- 当前 SSE `message_created` event payload 是完整 `user_message` 和一个 content 为空的 `assistant_message`。
- 当前 `retrieval` event 中 `reranked_count` 仍为 `0`，因为 message trace 还没有保存每个 chunk 的 reranker scores；这反映当前实现，不代表最终 SDD 完整形态。
- 当前 Feedback response 已包含 trace telemetry 字段，前端类型已同步。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 旧契约关键字扫描 | `rg -n "users/me/profile|UserProfile|UserProfileUpdateRequest|SSE stream will be added|不执行 reranker|后续 Phase 6-B" docs/api/openapi.v0.1.yaml docs/api/frontend-backend-api-contract.md frontend/src/api/types.ts` | 通过 | OpenAPI 和前端类型已移除 active profile 契约；文字契约只保留“当前未实现”的说明 |
| OpenAPI YAML 解析 | `backend/.venv/bin/python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('docs/api/openapi.v0.1.yaml').read_text())"` | 通过 | OpenAPI YAML 可解析 |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `cd frontend && npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` pure annotation warning，不影响构建 |
| 后端测试 | 未执行 | 未执行 | 本步骤未修改后端业务代码；后端全量测试已在 Step 022 通过 |

## 7. 当前未完成事项

- TDD 文档是否需要同步到 Step 021-024 的最新实现仍未专项核对。
- OpenAPI 还没有定义结构化 SSE event schema，只以 `text/event-stream` 字符串示例描述。
- `message_traces.reranker_scores` 仍未保存，SSE `retrieval.reranked_count` 当前仍为 `0`。
- Step 016 真实端到端人工确认项仍未解除。

## 8. 风险与注意事项

- OpenAPI 与后端 FastAPI 自动生成 schema 未做机器级 diff，只做了人工核对与 YAML 解析验证。
- 移除 `/users/me/profile` active contract 是基于当前实现；如果后续恢复用户偏好编辑功能，需要重新新增后端接口、前端 API、OpenAPI 和测试。
- 当前契约描述 SSE 已可用，但仍明确标注回答为模板化 Demo answer，不是真实 LLM token streaming。

## 9. 下一步建议

建议进入 Step 025：TDD 文档与当前实现差异核对。

原因：API contract、OpenAPI 和前端类型已经同步到当前主要实现；下一步应检查 `docs/tests/TDD.v0.1.md` 中的测试范围、阻塞项和验收 gate 是否仍停留在旧阶段，并补充当前 Demo 的真实验证命令和仍未解除的外部依赖项。
