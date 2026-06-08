# Step 025：TDD 文档与当前实现差异核对

## 1. 本步骤目标

将 `docs/tests/TDD.v0.1.md` 与当前 Step 024 之后的第一版基础 Web Demo 状态对齐，明确区分“当前已验证的 Demo 能力”和“完整 SDD v0.1 MVP 仍需满足的内测验收门槛”，并移除测试文档中过期的“项目仍处于文档和类型阶段”描述。

## 2. 对应 SDD 条目

- SDD v0.1 对启动、健康检查、权限、知识库、文件上传、解析、chunking、embedding、索引、检索、Reranker、SSE 问答、引用、trace、feedback、审计和前端核心页面的验收要求。
- SDD v0.1 中明确排除的能力继续作为 TDD 范围外或负向测试处理。
- 用户补充要求：MinerU 解析采用 API 调用方式，不使用本地 MinerU 服务作为当前实现前提。

## 3. 本步骤完成内容

- 在 `TDD.v0.1.md` 顶部新增“当前实现与测试状态”，记录当前基础 Web Demo 已验证能力和完整 MVP 未解除缺口。
- 更新测试环境说明，区分完整 MVP 目标 Compose 栈与当前已验证的基础 Demo Compose 栈。
- 明确 MinerU 当前按 API 调用方式实现，真实验证需要 `MINERU_API_TOKEN`。
- 在知识库、文件、检索重排、Chat、会话反馈、审计等 TDD 用例章节补充当前实现状态与未完成项。
- 将验收门槛拆分为“第一版基础 Web Demo 可操作验收”和“完整 SDD MVP 进入内测前必须满足”。
- 移除过期描述：“当前项目仍处于文档和类型阶段，尚未有后端路由、前端 API client 或测试代码”。
- 更新 `docs/tests/README.md`，增加 Demo 文档和进度总览入口。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `docs/tests/TDD.v0.1.md` | 修改 | 补充当前 Demo 测试状态、环境边界、未完成验收缺口和各关键用例当前状态 |
| `docs/tests/README.md` | 修改 | 增加 Demo 运行说明和开发进度总览入口 |
| `docs/progress/step-025-tdd-current-state-sync.md` | 新增 | 记录 Step 025 的目标、完成内容、验证结果、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 025 总进度、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 本步骤只修改文档，不修改后端、前端或数据库逻辑。
- `TDD.v0.1.md` 继续保留完整 MVP P0/P1 测试门槛，不因为当前 Demo 可操作而降低 SDD 验收标准。
- 当前基础 Web Demo 的可操作验收被单独记录，避免将模板化回答、fake 测试或未配置外部服务误认为真实 RAG 端到端验收通过。
- 当前实现差距被记录到具体 TDD 场景：
  - `TDD-KB-005`：cleanup job 尚未实现。
  - `TDD-FILE-012`：indexed 文件删除后的 Qdrant points 清理/失效尚未完成真实端到端验证。
  - `TDD-INDEX-007`：已记录 `reranker_model`，但尚未写入每个 chunk 的 `reranker_scores`。
  - `TDD-CHAT-009`：用户画像 answer_style/language 尚未接入当前 Demo。
  - `TDD-CONV-003`：删除会话接口尚未实现。
  - `TDD-AUDIT-003`：用户管理操作写入 audit_logs 尚未实现。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 文档存在性检查 | `test -f docs/tests/TDD.v0.1.md && test -f docs/tests/README.md && test -f docs/demo/first-version-demo.md` | 通过 | TDD、测试 README、Demo 文档均存在 |
| 过期描述扫描 | `rg -n "当前项目仍处于文档和类型阶段|尚未有后端路由、前端 API client 或测试代码" docs/tests/TDD.v0.1.md docs/tests/README.md` | 通过 | 无匹配输出；命令返回 1 表示未发现旧描述 |
| 新状态关键字扫描 | `rg -n "当前实现与测试状态|完整 SDD MVP 内测门槛尚未满足|MinerU 解析按用户要求采用 API 调用方式" docs/tests/TDD.v0.1.md` | 通过 | 已找到新增状态说明和 MinerU API 边界说明 |
| Docker Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 后端单元测试 | 未执行 | 未执行 | 本步骤仅修改文档，未改后端代码；沿用 Step 022 已记录的后端 pytest 结果 |
| 前端构建测试 | 未执行 | 未执行 | 本步骤仅修改文档，未改前端代码；沿用 Step 024 已记录的前端 typecheck/build 结果 |

## 7. 当前未完成事项

- 真实 MinerU API 在线解析仍需配置 `MINERU_API_TOKEN` 后验证。
- 真实 embedding-service、reranker-service 和 LLM Provider 仍未接入当前 Compose。
- 真实样本文档 RAG 带引用问答端到端仍未验收。
- Playwright E2E 和 OpenAPI 机器级契约测试尚未落地。
- TDD 中记录的实现差距尚需后续分步补齐：reranker_scores trace、删除会话、用户管理审计、cleanup job、indexed 删除后的 Qdrant 清理/失效验证等。

## 8. 风险与注意事项

- 当前第一版基础 Web Demo 可操作不等于完整 SDD MVP 内测通过。
- 当前 Chat SSE 是真实流式传输，但 token 内容来自模板化 Demo answer，不是真实 LLM。
- 当前 Reranker client 已接入，但真实 reranker-service 未在线验证。
- 当前 MinerU 采用 API 调用方式；真实验证依赖外部 token 和网络可达性。
- 如果后续决定走 Demo fixture 路线，需要用户明确确认，且必须标记为开发/演示用途，不能混淆为真实解析索引能力。

## 9. 下一步建议

建议进入 Step 026：补齐 message trace 中的 `reranker_scores`。

原因：该项对应 `TDD-INDEX-007` 和 `TDD-CHAT-007` 的 P0 trace 要求，范围相对清晰，可以在不依赖真实外部服务的情况下通过 fake reranker 测试验证，并能提升后续 feedback telemetry 和 RAG 调试链路的可验收性。
