# Step 018：前端用户管理与审计日志页面真实接口联调

## 1. 本步骤目标

本步骤目标是在 Step 017 知识库管理页面真实联调完成后，继续推进第一版 Demo 的后台管理可用性：将用户管理页面和审计日志页面从模拟数据切换到真实后端 API。

完成后，前端可通过页面完成：

- 查询用户列表。
- 按 keyword、role、is_active 筛选用户。
- 新建用户。
- 编辑用户显示名和角色。
- 禁用/启用用户。
- 重置用户密码。
- 查询审计日志。
- 按 actor_id、action、resource_type 筛选审计日志。
- 查看审计日志 details。

本步骤不新增后端核心功能，不处理真实 MinerU 解析、embedding-service、reranker、LLM 或 SSE。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `1. Admin 登录与用户管理`：本步骤前端用户管理页接入真实 Users API。
  - `22. 记录 Admin 高危操作审计日志`：本步骤前端审计日志页接入真实 Audit Logs API。
- `3.1 前端`：继续使用 Vue 3、Vite、TypeScript strict、Vue Router、Element Plus。
- `4.2 users`：
  - 第一版内置默认 Admin。
  - 后续用户只能由 Admin 创建。
  - disabled 用户不能登录。
- `12. 权限与安全`：
  - Admin 可管理用户和知识库。
  - User 不可访问 Admin API。
- `13.8 Phase 8：前端后台管理与问答页面`：本步骤聚焦用户管理与审计日志页面真实接口联调。

## 3. 本步骤完成内容

- 扩展前端 API client：
  - `listUsers(query)`
  - `createUser(payload)`
  - `updateUser(userId, payload)`
  - `disableUser(userId)`
  - `enableUser(userId)`
  - `resetUserPassword(userId, payload)`
  - `listAuditLogs(query)`
- 用户管理页接入真实后端：
  - 未登录时跳转登录页。
  - 页面加载真实用户列表。
  - 支持 keyword、role、active 状态筛选。
  - 支持新建用户。
  - 支持编辑显示名和角色。
  - 支持禁用/启用用户。
  - 支持重置密码。
  - 展示真实创建时间和最近登录时间。
- 审计日志页接入真实后端：
  - 未登录时跳转登录页。
  - 页面加载真实审计日志列表。
  - 支持 actor_id、action、resource_type 筛选。
  - 支持查看 details JSON。
  - 支持复制日志 ID。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 扩展 Users API 与 Audit Logs API 封装 |
| `frontend/src/views/UsersView.vue` | 修改 | 用户管理页从模拟数据切换为真实用户列表、新建、编辑、禁用/启用、重置密码 |
| `frontend/src/views/AuditLogsView.vue` | 修改 | 审计日志页从模拟数据切换为真实审计日志列表、筛选和详情展示 |
| `docs/progress/step-018-frontend-users-audit.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 018 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 用户列表：
  - 调用 `GET /api/v1/users`。
  - 查询参数包括 `keyword`、`role`、`is_active`。
  - 当前页面读取前 50 条。
- 用户创建：
  - 调用 `POST /api/v1/users`。
  - 前端要求邮箱、用户名、显示名和至少 8 位初始密码。
  - 默认角色为 `user`。
- 用户编辑：
  - 调用 `PATCH /api/v1/users/{user_id}`。
  - 当前支持更新显示名和角色。
- 用户状态与密码：
  - 启用/禁用分别调用 `/enable`、`/disable`。
  - 重置密码调用 `/reset-password`。
- 审计日志：
  - 调用 `GET /api/v1/audit-logs`。
  - 当前 action/resource_type 下拉选项来自当前已加载结果集合。
  - details 使用 JSON 格式展示。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过；首次发现 Audit Dialog v-model 类型问题，修复后通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 34 passed，1 个 Starlette/httpx deprecation warning |
| Users/Audit API smoke | 使用 `backend/.venv/bin/python` 调用登录、创建用户、更新用户、禁用、启用、重置密码、用户列表、创建知识库审计、审计日志查询 | 通过 | 登录 200、创建用户 201、更新 200、禁用 200、启用 200、重置密码 200、用户列表 200、审计日志查询 200 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |

## 7. 当前未完成事项

- Users API 当前不会写入审计日志；审计日志页面可展示知识库/文件等已有审计来源。若 SDD 后续要求用户管理操作也进入审计，需要新增后端审计写入。
- Users 页面当前读取前 50 条，尚未实现完整分页 UI。
- AuditLogs 页面当前读取前 50 条，尚未实现完整分页 UI。
- AuditLogs 页面 action/resource_type 下拉选项来自当前已加载数据，尚未提供全局枚举或远程聚合。
- Profile 页面仍主要是模拟数据，尚未接入真实 `/auth/me` 或 user profile API。
- 真实 MinerU 在线解析仍缺少 `MINERU_API_TOKEN`。
- 真实 embedding-service 仍未接入。
- Chat 仍是非流式 JSON Demo，不是 SSE/LLM。

## 8. 风险与注意事项

- 当前前端没有根据当前用户角色隐藏 Admin-only 操作；权限由后端强制控制。
- 重置密码通过对话框输入新密码，不自动生成临时密码；符合当前后端 API，但后续可按安全策略优化。
- 审计日志 response 当前没有 request_id 字段，页面展示并复制的是日志 ID。
- Step 016 的真实解析索引端到端人工确认项仍未解除。

## 9. 下一步建议

建议进入 Step 019：Profile/Auth 状态与导航展示真实化。

原因：

- 当前 AppLayout 仍展示固定的 Admin User / 张经理 文案。
- Profile 页面仍是模拟数据。
- 完成后，前端登录态、当前用户展示、退出登录和用户信息页面会更接近第一版 Demo 的真实体验。

Step 019 建议范围：

- API client 增加 `/auth/me` 和 `/auth/logout` 封装。
- AppLayout 读取当前用户并显示真实 username/display_name/role。
- 退出登录清理 token 并调用 logout。
- Profile 页面展示真实当前用户基础信息。
- 不新增后端核心功能，不处理真实解析索引端到端。
