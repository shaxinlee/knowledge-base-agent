# Step 023：第一版 Demo 运行说明与验收边界整理

## 1. 本步骤目标

将当前第一版 Web Demo 的启动方式、可演示流程、验收边界、SDD MVP 差距和外部依赖条件整理为项目内文档，避免后续开发或演示时把“基础 Web Demo 可操作”误判为“SDD v0.1 完整 MVP 已完成”。

本步骤不新增业务功能，不接入真实外部服务，不修改数据库结构。

## 2. 对应 SDD 条目

- SDD v0.1 1.3 核心目标：上传、解析、切片、索引、混合检索、reranker、LLM、引用溯源、会话与反馈保存。
- SDD v0.1 1.4 MVP 必须做什么：Admin 登录、知识库、文件上传、MinerU、embedding、Qdrant、全文检索、reranker、SSE、引用、拒答、trace、feedback、审计、Docker Compose。
- SDD v0.1 1.5 MVP 明确不做什么：不得擅自扩展 SDD 未规定的核心能力。
- 本步骤对应的是 Demo 运行和验收文档，不替代真实端到端功能验收。

## 3. 本步骤完成内容

- 新增第一版 Demo 运行说明文档。
- 明确当前 Demo 定位为“第一版基础 Web Demo 可操作版本”。
- 记录当前已可演示流程：
  - 登录与当前用户展示。
  - 知识库管理。
  - 文件上传、状态查看、chunks 空态/调试页。
  - Chat SSE 与证据不足拒答。
  - feedback。
  - 用户管理与审计。
- 记录当前不能验收为完整 SDD MVP 的原因：
  - `MINERU_API_TOKEN` 未配置。
  - Compose 尚未提供真实 embedding-service。
  - Compose 尚未提供真实 reranker-service。
  - Chat 仍是模板化回答，不是真实 LLM。
  - 真实带引用问答端到端链路未验证。
- 新增 SDD MVP 验收矩阵，逐项标注当前状态。
- 更新根 README，将项目描述从过期 Phase 0 状态调整为第一版 Web Demo 阶段，并指向 Demo 文档。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| README.md | 修改 | 更新项目当前状态、Demo 启动入口、默认 Admin、当前 Demo 边界和未完成外部依赖 |
| docs/demo/first-version-demo.md | 新增 | 新增第一版 Demo 启动、操作流程、验收矩阵、外部依赖和下一步路线说明 |
| docs/progress/step-023-demo-runbook-boundary.md | 新增 | 记录本步骤目标、实现内容、验证结果和后续建议 |
| docs/progress/README.md | 修改 | 更新总进度索引、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- `docs/demo/first-version-demo.md` 将当前 Demo 分为：
  - Demo 当前定位。
  - 启动前准备。
  - 启动方式。
  - 当前可演示流程。
  - SDD MVP 验收矩阵。
  - 当前验收命令。
  - 当前 Demo 验收结论。
  - 下一步选择。
- README 仅作为入口说明，详细边界放入 Demo 文档，避免 README 过长。
- 文档明确标注 MinerU 按 API 方式实现，并列出当前代码采用的 batch upload/result API 路径。
- 文档明确区分：
  - 已验证基础能力。
  - fake-client 测试覆盖能力。
  - 未在线验证的真实外部服务能力。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 文档文件存在性 | `test -f docs/demo/first-version-demo.md && test -f docs/progress/step-023-demo-runbook-boundary.md` | 通过 | 新增 Demo 文档和 Step 023 进度文件均存在 |
| README 入口检查 | `rg -n "first-version-demo|first-version Web Demo|Current Demo Boundary" README.md` | 通过 | README 已指向 Demo 文档并更新当前状态 |
| 进度索引检查 | `rg -n "Step 023|第一版 Demo 运行说明" docs/progress/README.md docs/progress/step-023-demo-runbook-boundary.md` | 通过 | 总进度索引包含 Step 023 |
| SDD 边界关键词检查 | `rg -n "MINERU_API_TOKEN|embedding-service|reranker-service|模板化|完整 MVP" docs/demo/first-version-demo.md` | 通过 | Demo 文档包含关键未完成项说明 |
| Docker Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| Compose 服务状态 | `docker compose ps` | 通过 | backend-api、frontend、postgres、redis、qdrant、minio 均为 Up |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 backend-api ok |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端服务可访问 |
| 后端测试 | 未执行 | 未执行 | 本步骤只修改文档与 README，未修改后端代码；Step 022 已完成后端全量测试 |
| 前端构建 | 未执行 | 未执行 | 本步骤只修改文档与 README，未修改前端代码；本步通过运行服务访问检查验证 Demo 入口可访问 |

## 7. 当前未完成事项

- Step 016 真实端到端人工确认项仍未解除。
- 真实 MinerU 在线解析仍需 `MINERU_API_TOKEN`。
- 真实 embedding-service 仍未接入 Compose。
- 真实 reranker-service 仍未接入 Compose。
- 真实 LLM answer generation 仍未实现。
- 第一版 Demo 如需展示带引用回答，需要继续选择真实外部服务路线或经人工确认后开发 Demo fixture 路线。

## 8. 风险与注意事项

- README 现在描述的是当前 Demo 阶段，但 API contract、OpenAPI 和 TDD 是否完全同步到 Step 022/023 仍需后续专项检查。
- 当前 Demo 文档中列出的真实外部服务缺口不是阻塞本步骤的问题，但会阻塞 SDD 完整 MVP 验收。
- 如果选择 Demo fixture 路线，必须明确标记为开发/演示用途，不得污染生产逻辑或替代真实解析索引验收。
- 当前系统环境中 `git` 命令不可用，无法通过 git 状态确认工作区；本步骤以文件内容和验证命令为准。

## 9. 下一步建议

建议进入 Step 024：API Contract / OpenAPI / 前端类型与当前实现差异核对。

原因：README 与 Demo 文档已经把当前可运行边界写清楚。继续推进第一版 Demo 前，需要确认对外契约是否仍停留在旧阶段，特别是 SSE、feedback、reranker、文件状态、知识库状态、Auth/logout、Profile 等接口是否和当前实现一致。该步骤可以只做核对和必要的契约文档同步，不需要新增核心业务功能。
