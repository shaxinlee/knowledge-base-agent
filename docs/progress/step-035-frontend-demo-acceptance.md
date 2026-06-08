# Step 035：第一版 Demo 前端验收固化

## 1. 本步骤目标

将 Step 034 已打通的受限 Demo fixture citation 链路固化到前端验收层面：补充 Chat 页面稳定验收 selector，新增前端验收清单，并通过前端构建、lint、运行服务和真实 API smoke 证明第一版 Demo 的前端验收材料可用。

## 2. 对应 SDD 条目

- SDD v0.1：User 可登录、选择知识库、提问、查看引用、提交反馈。
- SDD v0.1：回答必须带引用编号。
- SDD v0.1：引用必须包含文件名、定位信息和原文片段。
- SDD v0.1：保存会话、消息、引用、trace。
- Step 034 下一步建议：围绕前端页面验收，把 `demo_user` 登录、选择 `Demo Fixture 知识库`、发送推荐问题、查看 citation chips/detail、提交 feedback 的流程固化为文档化验收或自动化基础。

## 3. 本步骤完成内容

- Chat 页面新增稳定 `data-testid` selector，覆盖：
  - 页面根节点
  - 知识库选择
  - 新建对话
  - 历史会话搜索/打开/删除
  - 消息列表和消息气泡
  - 输入框和发送按钮
  - citation chip/list/detail
  - citation 文件名、原文片段、source locator
  - helpful / unhelpful feedback 按钮
- Chat 页面刷新 conversation list 后保留当前 active conversation，提升发送消息后的前端验收稳定性。
- 移除 Chat 页面未使用的 `activeConversation` computed，使前端 lint 可通过。
- 新增 `docs/demo/frontend-acceptance-checklist.md`，记录第一版 Demo 前端验收步骤、账号、推荐问题、预期结果和 selector 清单。
- 更新 Demo 文档、README 和 TDD，增加前端验收清单入口和当前状态说明。
- 复跑真实 API citation + feedback smoke，确认前端验收依赖的数据链路仍可用。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/views/ChatView.vue` | 修改 | 增加稳定 `data-testid` selector，保留 active conversation 刷新状态，并移除未使用 computed |
| `docs/demo/frontend-acceptance-checklist.md` | 新增 | 固化第一版 Demo 前端验收流程、账号、推荐问题、预期结果和 selector 清单 |
| `docs/demo/first-version-demo.md` | 修改 | 增加前端验收清单入口和 Demo fixture citation 前端验收说明 |
| `docs/tests/TDD.v0.1.md` | 修改 | 同步 Step 035 当前状态和前端验收清单入口 |
| `README.md` | 修改 | 在 Primary References 中加入前端验收清单 |
| `docs/progress/step-035-frontend-demo-acceptance.md` | 新增 | 记录 Step 035 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 035 状态、已完成内容、待完成内容、注意事项和下一步建议 |

## 5. 关键实现说明

- 本步骤未新增 Playwright/Cypress 依赖，避免扩大第一版 Demo 的依赖面。
- 新增 selector 只用于验收和后续自动化定位，不改变页面视觉和 API 行为。
- `refreshConversationList()` 现在会在刷新后优先保留原 active conversation；如果该会话不在返回列表中，再回退到第一条或空态。
- `docs/demo/frontend-acceptance-checklist.md` 可直接用于人工验收，也可作为后续浏览器自动化测试脚本的步骤来源。
- 当前前端验收仍基于受限 Demo fixture，不代表真实 MinerU / embedding / reranker / LLM 的完整 MVP 验收。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端 lint | `npm run lint` | 通过 | 初次发现 `activeConversation` 未使用；移除后复跑通过 |
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端 dev server 可访问 |
| Demo citation + feedback API smoke | 使用真实 HTTP API 登录 `demo_user`、创建 conversation、发送推荐问题、提交 helpful、读取 detail | 通过 | assistant answer 包含 `[1]`；citation_count 为 3；feedback_rating 回显 `helpful` |
| selector 与文档扫描 | `rg -n 'data-testid=...|frontend-acceptance-checklist|Demo fixture citation 前端验收' ...` | 通过 | 可定位 selector、验收文档入口和 Demo 文档说明 |

## 7. 当前未完成事项

- 当前仓库仍未引入 Playwright/Cypress，未执行真实浏览器点击/截图自动化。
- 真实 MinerU 在线解析、真实 embedding-service、真实 reranker-service 和真实 LLM Provider 仍未接入。
- 真实上传文件到带引用回答的完整端到端链路仍未通过。
- `cleanup_jobs` 表、异步清理 MinIO/Qdrant 残留对象和知识库删除级联清理仍未实现。

## 8. 风险与注意事项

- 本步骤固化的是第一版 Demo 前端验收，不解除完整 SDD MVP 的真实外部服务验收缺口。
- `data-testid` selector 是后续自动化测试契约的一部分；后续改动 Chat 页面时应同步更新 `docs/demo/frontend-acceptance-checklist.md`。
- 当前 Demo fixture citation 使用本地确定性 demo embedding/reranker，不代表真实检索和重排质量。
- 当前 `.env` 已为本地 Demo 打开 `DEMO_FIXTURE_ENABLED=true`；`.env.example` 默认仍是 `false`。

## 9. 下一步建议

建议进入 Step 036：第一版 Demo 交付审计与收口。

原因：当前第一版 Demo 已具备基础操作、受限 citation 演示、进度文档和前端验收清单。下一步应按 SDD、Demo 文档、TDD 和进度索引进行交付审计，确认第一版 Demo 边界内是否还有必须完成的缺口；如果没有，应整理最终 Demo 验收结论。如果发现缺口，再按缺口拆分后续步骤。
