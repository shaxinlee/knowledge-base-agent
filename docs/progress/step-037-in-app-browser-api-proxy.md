# Step 037：内置浏览器 API 代理与 Failed to fetch 修复

## 1. 本步骤目标

修复 Codex 内置浏览器通过临时端口访问 Demo 页面时，登录后出现 `Failed to fetch` 的问题，确保第一版 Demo 在 `http://localhost:63166/login` 这类转发地址下也能正常访问后端 API。

## 2. 对应 SDD 条目

- SDD v0.1 1.4：Admin 登录与用户管理。
- SDD v0.1 1.4：User 基于单个知识库空间提问。
- SDD v0.1 1.4：Docker Compose 一键启动完整系统。
- 第一版 Demo 验收边界：本地 Web Demo 应可打开、登录并加载知识库/用户/审计/Chat 页面数据。

## 3. 本步骤完成内容

- 将前端 API 默认地址从绝对地址 `http://localhost:8000/api/v1` 改为同源相对地址 `/api/v1`。
- 将 Vite dev server 的 `/api` 代理目标改为 Docker Compose 服务名 `http://backend-api:8000`，避免前端容器内访问 `localhost:8000` 指向自身。
- 保留 `VITE_API_BASE_URL` 覆盖能力，后续部署或本机非 Docker 开发仍可显式指定 API 地址。
- 将 Codex 内置浏览器当前临时端口 `http://localhost:63166` / `http://127.0.0.1:63166` 加入后端 CORS 允许来源。
- 重启前端容器，使新的 Vite 代理配置生效。
- 验证从前端同源 `/api/v1` 代理访问后端 health 和 admin 登录均成功。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 默认 API base URL 改为 `/api/v1`，让内置浏览器端口通过同源代理访问 API |
| `frontend/vite.config.ts` | 修改 | `/api` 代理默认目标改为 `http://backend-api:8000`，并保留 `VITE_DEV_PROXY_TARGET` 覆盖 |
| `.env` | 修改 | 将 `http://localhost:63166` 和 `http://127.0.0.1:63166` 加入本地 CORS 来源 |
| `.env.example` | 修改 | 同步本地/内置浏览器 CORS 来源示例 |
| `docs/progress/step-037-in-app-browser-api-proxy.md` | 新增 | 记录本步骤目标、实现、验证和后续建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 037 状态和当前修复说明 |

## 5. 关键实现说明

- `Failed to fetch` 的根因不是 admin 账号或密码错误；后端 `POST /api/v1/auth/login` 已验证可返回 admin token。
- 内置浏览器使用 `http://localhost:63166/login` 访问页面时，如果前端直接请求 `http://localhost:8000/api/v1`，会绕开 Vite 代理，并可能被内置浏览器网络环境或跨来源策略拦截。
- 改为 `/api/v1` 后，浏览器请求会落到当前页面同源地址，再由 Vite dev server 的 `/api` proxy 转发到 `backend-api:8000`。
- 本步骤不改变后端业务接口、数据库结构、认证逻辑或 Demo fixture 数据。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端容器重启 | `docker compose up -d --force-recreate frontend` | 通过 | 前端容器已重新创建并启动 |
| 前端代理 health | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回后端 health：`status=ok` |
| 前端代理 admin 登录 | `curl -fsS -X POST http://localhost:5173/api/v1/auth/login ...` | 通过 | 返回 `admin` / `admin` role |
| 登录页访问 | `curl -fsS http://localhost:5173/login >/dev/null` | 通过 | 登录页可访问 |
| 前端 lint | `cd frontend && npm run lint` | 通过 | ESLint 通过 |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `cd frontend && npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 内置浏览器端口 shell 可见性 | `curl -fsS http://localhost:63166/login` | 未执行成功 | 该端口是 Codex 内置浏览器转发端口，当前 shell 侧不可直接连接；已通过同源代理设计规避前端直接请求后端端口的问题 |

## 7. 当前未完成事项

- 如果 Codex 内置浏览器后续更换新的临时端口，后端 CORS 可能还需要加入新的来源；但当前前端默认同源代理后，普通 API 请求不再直接依赖跨端口 CORS。
- 当前生产构建仍使用前端静态资源；如后续用静态服务器部署，需要配置同样的 `/api` 反向代理或显式设置 `VITE_API_BASE_URL`。

## 8. 风险与注意事项

- `VITE_DEV_PROXY_TARGET` 默认值现在面向 Docker Compose 开发环境；如果在宿主机直接 `npm run dev`，且后端跑在宿主机 `localhost:8000`，可以设置 `VITE_DEV_PROXY_TARGET=http://localhost:8000`。
- `.env.example` 中记录了当前 Codex 内置浏览器端口 `63166`，该端口可能因会话变化而变化。
- 本步骤只修复页面访问与 API 代理问题，不改变完整 SDD MVP 的真实外部服务缺口。

## 9. 下一步建议

请在内置浏览器中强刷新 `http://localhost:63166/login`，重新输入 `admin` / `AdminPassword123` 登录。如果仍显示旧错误，优先清除该页面的 Local Storage 或打开新的内置浏览器会话，避免旧前端 bundle/token 缓存影响。
