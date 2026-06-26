# Step 019：Profile/Auth 状态与导航展示真实化

## 1. 本步骤目标

本步骤目标是在 Step 018 用户管理与审计日志页面真实联调完成后，将前端布局和个人资料页面中固定的用户文案切换为真实当前登录用户数据，并接入真实退出登录流程。

完成后，前端可实现：

- AppLayout 侧边栏显示真实 display_name / role。
- AppLayout 顶部显示真实当前用户。
- 退出登录时调用后端 `/auth/logout`，并清理本地 token。
- Profile 页面展示真实 `/auth/me` 返回的当前用户信息。
- access token 失效或读取当前用户失败时清理 token 并跳转登录页。

本步骤不新增后端核心功能，不实现用户资料编辑，不处理真实 MinerU 解析、embedding-service、reranker、LLM 或 SSE。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `1. Admin 登录与用户管理`：本步骤让前端登录态展示与退出登录接入真实 Auth API。
- `3.1 前端`：继续使用 Vue 3、Vite、TypeScript strict、Vue Router、Element Plus。
- `4.2 users`：展示 username、role、status、created_at、last_login_at 等当前用户基础信息。
- `4.3 user_profiles`：当前仅展示后端 `AuthUserResponse` 中的 display_name；不新增 profile 编辑功能。
- `12. 权限与安全`：退出登录后 refresh token 不可复用，由后端 Step 005 已实现。

## 3. 本步骤完成内容

- 扩展前端 API client：
  - `getRefreshToken()`
  - `getCurrentUser()`
  - `logout(payload)`
- AppLayout 接入真实当前用户：
  - mounted 后调用 `/auth/me`。
  - 侧边栏头像、display_name、role 使用真实数据。
  - 顶部当前用户使用真实数据。
  - 退出登录按钮调用 `/auth/logout`，然后清理 token 并跳转登录页。
  - 如果 `/auth/me` 失败，清理 token 并跳转登录页。
- Profile 页面接入真实当前用户：
  - mounted 后调用 `/auth/me`。
  - 展示 username、display_name、role、is_active、created_at、last_login_at。
  - 支持刷新当前用户信息。
  - 移除原先未接后端的“保存”假操作。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 增加 refresh token 读取、当前用户查询和 logout API 封装 |
| `frontend/src/components/AppLayout.vue` | 修改 | 布局展示真实当前用户，退出登录调用后端并清理 token |
| `frontend/src/views/ProfileView.vue` | 修改 | Profile 页面展示真实 `/auth/me` 用户信息，移除未接后端的保存假操作 |
| `docs/progress/step-019-profile-auth-state.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 019 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 当前用户：
  - `getCurrentUser()` 调用 `GET /api/v1/auth/me`。
  - AppLayout 与 Profile 各自读取当前用户，保持实现简单。
- 退出登录：
  - 读取 localStorage 中的 refresh token。
  - 调用 `POST /api/v1/auth/logout`。
  - 无论后端 logout 是否因 token 过期失败，前端都会清理本地 token 并跳转登录页。
  - 后端已验证 logout 后 refresh token 不可复用。
- Profile 页面：
  - 当前只读展示真实用户基础信息。
  - 不提供编辑 display_name，因为当前后端没有面向当前用户的 profile update endpoint。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 34 passed，1 个 Starlette/httpx deprecation warning |
| Auth API smoke | 使用 `backend/.venv/bin/python` 调用登录、`/auth/me`、logout、logout 后 refresh | 通过 | 登录 200、me 200 且返回 admin/admin、logout 204、logout 后 refresh 401 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |

## 7. 当前未完成事项

- Profile 页面当前只读，尚未实现用户自助编辑 display_name 或 profile 偏好。
- 前端仍没有集中式 auth store；当前采用页面/布局按需读取 `/auth/me` 的简单实现。
- 前端 token refresh 自动续期尚未实现。
- 真实 MinerU 在线解析仍缺少 `MINERU_API_TOKEN`。
- 真实 embedding-service 仍未接入。
- Chat 仍是非流式 JSON Demo，不是 SSE/LLM。

## 8. 风险与注意事项

- AppLayout 与 Profile 各自调用 `/auth/me`，简单直接但不是最终最优状态；后续可用 Pinia auth store 统一。
- access token 过期时当前会跳转登录页，不会自动 refresh。
- logout 调用失败时前端仍会清理 token，这是为了避免用户卡在本地登录态。
- Step 016 的真实解析索引端到端人工确认项仍未解除。

## 9. 下一步建议

建议下一步回到 Step 016 的人工确认项：

- 如果可以提供 `MINERU_API_TOKEN`，并提供或允许新增真实 embedding-service，则继续真实端到端解析索引验证。
- 如果短期无法提供外部服务，则需要人工确认是否允许实现明确标记为开发 Demo 的 seed/fixture 路径，用于生成可检索 chunks 并验证 Chat citation 展示。

原因：

- 到本步骤为止，第一版 Web Demo 的主要前端页面已经基本接入真实后端 API。
- 继续做更多页面 polish 的收益低于补齐“带引用回答”的核心演示链路。
- SDD MVP 的关键差距仍是真实解析、embedding/Qdrant 索引、reranker、SSE/LLM 和反馈。
