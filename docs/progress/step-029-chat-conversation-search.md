# Step 029：Chat 历史会话搜索过滤

## 1. 本步骤目标

将 Chat 页面左侧“搜索历史会话”输入框从静态 UI 补齐为可用的本地过滤能力，支持按会话标题过滤当前知识库下已加载的历史会话。

## 2. 对应 SDD 条目

- SDD v0.1：前端核心页面需要支持登录、管理、上传、状态轮询、问答、引用展示和反馈等主流程。
- SDD v0.1：conversation 绑定单个 knowledge_base_id，用户只能访问自己的会话。
- Step 028 下一步建议：Chat 页面已有搜索输入框但此前只是静态 UI，需要补齐本地标题过滤。

## 3. 本步骤完成内容

- 新增 `conversationSearchQuery` 前端状态。
- 新增 `filteredConversations` 计算属性，按会话标题执行本地过滤。
- 搜索输入框接入 `v-model` 和清空按钮。
- 历史会话列表切换为渲染 `filteredConversations`。
- 新增空态：
  - 当前知识库无历史会话时显示“暂无历史会话”。
  - 搜索无匹配结果时显示“没有匹配会话”。
- 切换知识库、创建 Demo 知识库、新建会话时清空搜索词，避免新状态被旧搜索词隐藏。
- 删除当前会话时优先切换到当前搜索结果中的下一条可见会话；没有可见会话时清空消息区和引用详情。
- 更新 Demo 运行说明，补充历史会话搜索可演示流程。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/views/ChatView.vue` | 修改 | 接入历史会话搜索状态、过滤列表、无结果空态和相关边界处理 |
| `docs/demo/first-version-demo.md` | 修改 | 补充 Chat 历史会话搜索可演示流程 |
| `docs/progress/step-029-chat-conversation-search.md` | 新增 | 记录 Step 029 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 029 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 搜索仅在前端本地执行，不新增后端 API 参数。
- 搜索范围是当前 knowledge base 下已加载的 conversation 列表，符合 MVP 单知识库会话边界。
- 匹配逻辑使用 `trim()` 和 `toLocaleLowerCase()` 做大小写不敏感标题匹配。
- 新建会话时会清空搜索词，确保新建会话立即可见。
- 删除当前会话后，页面优先打开搜索结果中的下一条可见会话，保持用户当前筛选上下文。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端服务可访问 |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 源码关键字扫描 | `rg -n 'conversationSearchQuery|filteredConversations|没有匹配会话|暂无历史会话|normalizeSearchKeyword|v-for="conversation in filteredConversations"' frontend/src/views/ChatView.vue` | 通过 | 搜索状态、过滤计算属性、空态和列表渲染均可定位 |
| 后端单元测试 | 未执行 | 未执行 | 本步骤未修改后端代码 |
| Playwright 页面测试 | 未执行 | 未执行 | 当前仓库尚未配置 Playwright 测试体系；本步骤使用 typecheck/build 和运行服务检查作为最小验证 |

## 7. 当前未完成事项

- Chat 页面加载历史 conversation 时尚不回显已提交 feedback 状态。
- Chat 搜索仅过滤已加载的前 50 条 conversation，完整分页/后端搜索未实现。
- 真实带引用回答仍依赖 MinerU API token、embedding-service、reranker-service 和 LLM Provider。
- 前端尚未配置 Playwright E2E 测试。

## 8. 风险与注意事项

- 本地过滤不会向后端请求更多 conversation；当历史会话超过当前加载页时，搜索结果可能不完整。
- 本步骤不改变 conversation API，不影响权限边界。
- 当前运行中的 frontend 容器是否热更新取决于 Compose 挂载和服务状态；源码已通过本地 typecheck/build 验证。

## 9. 下一步建议

建议进入 Step 030：为 Chat 历史消息回显已提交 feedback 状态做后端/前端最小闭环评估。

原因：当前 Chat 页面可以提交 helpful/unhelpful，但重新打开历史会话时不会回显已提交状态，Step 020 已记录该体验缺口。该能力与现有 feedback 表和 conversation detail 响应相关，适合作为下一步独立评估和实现。
