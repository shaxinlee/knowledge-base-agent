# Step 014：前端 Chat Demo 真实接口联调

## 1. 本步骤目标

本步骤目标是在 Step 013 后端非流式 Chat Demo 的基础上，将前端登录页和 Chat 页面从静态/模拟数据切换到真实后端 API，形成第一版可操作的 Web Demo：

- 前端可使用默认 Admin 登录。
- Chat 页面可读取 active 知识库。
- Chat 页面可创建 Demo 知识库。
- Chat 页面可创建、选择和打开 conversation。
- Chat 页面可发送 `stream=false` 消息。
- Chat 页面可展示 assistant answer 和 citations。
- 空知识库场景下可展示证据不足拒答。

本步骤不新增真实 LLM、SSE、reranker、文件上传页面联调或真实 embedding-service。

## 2. 对应 SDD 条目

- `1.3 核心目标`：系统应支持用户提问并返回带引用溯源的知识问答结果。本步骤完成第一版页面到后端非流式问答接口的联调。
- `1.4 MVP 必须做什么`：
  - `1. Admin 登录与用户管理`：本步骤让前端登录页接入真实 Admin 登录接口。
  - `15. User 基于单个知识库空间提问`：本步骤让 Chat 页面在选定单个知识库后创建会话并发送问题。
  - `17. 回答必须带引用编号`、`18. 引用必须包含文件名、定位信息和原文片段`：本步骤前端展示后端返回的 citation 信息；空知识库时 citation 为空并展示拒答。
  - `19. 证据不足时必须拒答`：本步骤通过真实接口 smoke 验证空知识库拒答路径。
  - `20. 保存会话、消息、引用、trace`：本步骤复用 Step 013 后端保存逻辑，并通过前端调用路径触发。
- `3.1 前端`：Vue 3、Vite、TypeScript strict、Vue Router、Element Plus。本步骤沿用现有前端技术栈。
- `13.8 Phase 8：前端后台管理与问答页面`：本步骤聚焦 Chat 页面真实接口联调。

## 3. 本步骤完成内容

- 新增前端 API client：
  - 登录。
  - token 本地保存和清理。
  - 知识库列表/创建。
  - conversation 列表/创建/详情。
  - conversation message 发送。
- 登录页接入真实后端：
  - 使用 `POST /api/v1/auth/login`。
  - 登录成功保存 access/refresh token。
  - 登录成功跳转到 Chat 页面。
  - 默认填充开发 Demo 账号 `admin` / `AdminPassword123`。
- Chat 页面接入真实后端：
  - 未登录时跳转登录页。
  - 加载 active 知识库并支持切换。
  - 无知识库时可创建 Demo 知识库。
  - 按知识库加载 conversation 列表。
  - 支持新建 conversation。
  - 支持打开 conversation 并展示历史消息。
  - 发送消息时调用 `POST /api/v1/conversations/{conversation_id}/messages`，请求体显式设置 `stream:false`。
  - 展示 assistant answer。
  - 展示 citations chip 和 citation detail。
- 后端检索服务补充 Demo 保护：
  - 当知识库中没有 active indexed chunks 时，retrieval 直接返回空结果。
  - 该保护避免空知识库 Demo 因未配置真实 embedding-service 而失败。
  - 若后续知识库已有 indexed chunks，则仍会进入 embedding/Qdrant 检索链路。
- 新增/补充测试：
  - 覆盖空知识库消息发送时返回拒答。
  - 验证该路径不会调用 embedding-service。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 新增 | 新增前端真实 API client，封装登录、知识库、conversation 和消息发送 |
| `frontend/src/api/types.ts` | 修改 | 补充/调整 Chat Demo、retrieval 和 message response 相关类型 |
| `frontend/src/views/LoginView.vue` | 修改 | 登录页切换为真实登录接口，保存 token 并跳转 Chat 页面 |
| `frontend/src/views/ChatView.vue` | 修改 | Chat 页面切换为真实知识库/conversation/message 接口，展示 assistant answer 和 citations |
| `backend/app/services/retrieval.py` | 修改 | 增加无 active indexed chunks 时的空检索结果保护，保障空知识库拒答 Demo 可运行 |
| `backend/tests/test_conversations_api.py` | 修改 | 补充空知识库非流式 Chat Demo 拒答与不调用 embedding-service 的测试 |
| `docs/progress/step-014-frontend-chat-demo.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 014 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- API client：
  - 默认 API base URL 为 `http://localhost:8000/api/v1`。
  - 可通过 `VITE_API_BASE_URL` 覆盖。
  - 非登录请求自动附带 `Authorization: Bearer <access_token>`。
  - 当前仅做 Demo 级 token 保存，不实现 refresh 自动续期。
- 登录页：
  - 保持原页面风格和 Element Plus 控件。
  - 登录成功后保存 token，进入 `/chat`。
  - 登录失败时展示后端 error envelope 中的错误信息。
- Chat 页面：
  - 页面基于单个 `activeKnowledgeBaseId` 工作，符合 SDD 禁止跨知识库查询的边界。
  - 新建会话后可立即发送消息。
  - 发送消息使用后端当前已支持的 `stream:false` JSON demo。
  - citation 展示使用后端返回的 `file_name`、`source_locator`、`excerpt` 和 `chunk_id`。
- 空知识库拒答：
  - 当前 Compose 尚未定义真实 embedding-service。
  - 为保证第一版 Demo 在空知识库下可运行，retrieval 在无 active indexed chunks 时直接返回空结果，由 Chat service 使用证据不足模板拒答。
  - 该逻辑不改变已有 indexed chunks 的真实检索路径。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 75 files would be left unchanged |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 66 个 source files 无类型错误 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 34 passed，1 个 Starlette/httpx deprecation warning |
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| Docker Compose 服务状态 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| Qdrant 检查 | `curl -sS http://localhost:6333/collections` | 通过 | 返回 `status:"ok"` |
| 真实接口 smoke | 使用 `backend/.venv/bin/python` 调用登录、创建知识库、创建 conversation、发送 message | 通过 | 登录 200、创建知识库 201、创建会话 201、发送消息 200；assistant role 为 `assistant`，citation_count 为 `0`，回答为证据不足拒答 |
| 系统 Python smoke 尝试 | 使用系统 `python3.11` 执行同一路径 | 失败 | 系统环境缺少 `httpx`，改用项目后端虚拟环境后通过；应用本身无失败 |
| 真实 MinerU 在线解析 | 配置 `MINERU_API_TOKEN` 后上传真实文件解析 | 未执行 | 本步骤不涉及 MinerU 在线验证，Step 008 已实现 API client，真实 token 仍需用户提供 |
| 真实 LLM/SSE 验证 | 真实模型服务 + SSE 流式回答 | 未执行 | 本步骤明确不实现真实 LLM/SSE |

## 7. 当前未完成事项

- 前端文件上传、文件列表、解析状态轮询和 chunks 页面仍主要是静态/模拟页面，尚未接入真实 Files API。
- 当前 Chat Demo 使用非流式 JSON 响应，尚未实现 SSE。
- 当前 assistant answer 为后端模板化 Demo，不是真实 LLM 生成。
- 当前尚未实现 reranker-service。
- 当前 Compose 尚未定义真实 embedding-service 容器。
- 当前未完成真实上传文件到 MinerU API、标准化、chunking、embedding、Qdrant、Chat 的完整端到端在线验证。
- 当前未实现 helpful/unhelpful feedback。
- 登录 token 当前没有自动 refresh。
- Chat 页面搜索历史会话输入框当前仅保留 UI，尚未实现过滤逻辑。

## 8. 风险与注意事项

- 由于真实 embedding-service、reranker-service 和 LLM Provider 尚未接入，本步骤只能证明前端 Chat Demo 到后端非流式接口可用，不能代表最终 RAG 质量。
- 空知识库拒答路径可稳定演示；带 indexed chunks 的真实问答仍依赖后续 embedding-service、reranker 和 LLM 服务补齐。
- `VITE_API_BASE_URL` 默认指向本地 `http://localhost:8000/api/v1`，部署到其他环境时需要显式配置。
- 默认 Demo 账号只适用于开发环境，生产环境必须修改默认密码和 JWT secret。
- 本步骤没有改变 MinerU API 方式；文档解析仍沿用 Step 008 已实现的 MinerU API client。

## 9. 下一步建议

建议进入 Step 015：前端文件上传与解析状态联调。

原因：

- 第一版 Demo 目前可以登录、创建知识库、创建会话并看到拒答，但还不能通过页面上传资料并看到文件解析/索引状态。
- SDD MVP 的核心演示链路是“上传资料 -> 解析/切片/索引 -> 提问 -> 引用回答”。
- 在接入 SSE/LLM 之前，先让文件上传和状态页面接入真实后端，可以让 Demo 从“空知识库拒答”推进到“用户能把资料放进系统”的更完整状态。

Step 015 建议范围：

- `FilesView.vue` 接入真实知识库列表、文件列表、上传和状态查询。
- `ChunksView.vue` 或文件详情入口展示真实 active chunks。
- 暂不引入新后端核心功能，只复用 Step 007-011 已有 API。
- 若没有 `MINERU_API_TOKEN` 或真实 embedding-service，则在页面上明确展示当前状态/错误，不伪造解析成功。
