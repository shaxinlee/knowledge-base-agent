# Step 028：前端 Chat 历史会话删除交互

## 1. 本步骤目标

在前端 Chat 历史会话列表中接入删除会话交互，调用 Step 027 已实现的 `DELETE /api/v1/conversations/{conversation_id}` 后端接口，形成用户可操作的会话生命周期基础闭环。

## 2. 对应 SDD 条目

- SDD v0.1：conversation CRUD，包含 `DELETE /api/v1/conversations/{conversation_id}`。
- SDD v0.1：用户只能访问自己的会话。
- SDD v0.1：会话等对象采用软删除，不做物理即时删除。
- TDD v0.1：`TDD-CONV-003` 当前用户删除自己的会话，其他用户不可删除。
- Demo 文档：Chat 页面可演示会话创建、历史会话打开、历史会话删除和 SSE 流式消息发送。

## 3. 本步骤完成内容

- 在前端 API client 中新增 `deleteConversation(conversationId)`。
- 在 Chat 历史会话列表中为每条会话增加删除图标按钮。
- 删除前使用 Element Plus 确认框，取消时不报错。
- 删除成功后显示成功提示，并从当前历史会话列表移除该会话。
- 如果删除的是当前会话：
  - 存在其他会话时自动打开列表中的下一条会话。
  - 没有其他会话时清空消息区和引用详情。
- 防止删除按钮点击冒泡触发打开会话。
- 删除中禁用对应会话的打开和删除操作。
- 更新 Demo 运行说明，补充 Chat 历史会话删除流程和软删除边界。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 新增 `deleteConversation()` 前端 API 方法 |
| `frontend/src/views/ChatView.vue` | 修改 | 在历史会话列表接入删除按钮、确认框、删除状态和删除后列表/消息区更新 |
| `docs/demo/first-version-demo.md` | 修改 | 补充 Chat 历史会话删除可演示流程和软删除说明 |
| `docs/progress/step-028-frontend-conversation-delete.md` | 新增 | 记录 Step 028 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 028 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 前端删除会话复用 Step 027 的真实后端接口，不新增 mock 或 fixture 路线。
- 历史会话条目从“整条 button”调整为两列布局：
  - 左侧 `conversation-main` 负责打开会话。
  - 右侧 `conversation-delete` 负责删除会话。
- 删除按钮使用 `@click.stop`，避免删除动作同时触发打开会话。
- `deletingConversationById` 用于记录单条会话删除状态，保证删除期间该条会话不可重复点击。
- 本步骤不改变后端软删除策略，不删除 messages、citations、traces 或 feedback 历史数据。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端服务可访问 |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 删除会话接口 smoke | Python urllib 调用登录、创建知识库、创建会话、删除会话、详情 404、列表为空 | 通过 | 输出 `conversation_delete_smoke=passed` |
| 后端单元测试 | 未执行 | 未执行 | 本步骤未修改后端代码；后端删除接口已在 Step 027 通过 `38 passed` 回归验证 |
| Playwright 页面测试 | 未执行 | 未执行 | 当前仓库尚未配置 Playwright 测试体系；本步骤使用 typecheck/build 与真实接口 smoke 作为最小验证 |

## 7. 当前未完成事项

- Chat 历史会话搜索输入框仍未实现过滤逻辑。
- Chat 页面加载历史 conversation 时尚不回显已提交 feedback 状态。
- 真实带引用回答仍依赖 MinerU API token、embedding-service、reranker-service 和 LLM Provider。
- 前端尚未配置 Playwright E2E 测试。

## 8. 风险与注意事项

- 删除会话只是软删除 conversation；messages、citations、traces 和 feedback 仍保留在数据库中。
- 本步骤只验证前端构建和真实接口 smoke，未做浏览器自动化点击验证。
- 如果当前运行中的 frontend 容器不是热更新模式，需要重新构建/重启前端容器才能看到最新页面；本地源码 typecheck/build 已通过。

## 9. 下一步建议

建议进入 Step 029：实现 Chat 历史会话搜索过滤。

原因：Chat 页面已有搜索输入框但目前只是静态 UI。补齐本地标题过滤不依赖外部服务，范围小、可前端验证，并能减少 Demo 中“看得见但不能用”的界面空壳。
