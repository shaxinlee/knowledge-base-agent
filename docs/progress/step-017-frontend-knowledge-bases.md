# Step 017：前端知识库管理页面真实接口联调

## 1. 本步骤目标

本步骤目标是在 Step 016 确认真实解析索引端到端仍缺少外部条件后，继续推进不依赖模型服务的第一版 Demo 能力：将知识库管理页面从模拟数据切换到真实 KnowledgeBase API。

完成后，前端可通过页面完成：

- 查询 active 知识库。
- 按 keyword 查询知识库。
- 按 deleted 状态查询软删除知识库。
- 创建知识库。
- 编辑知识库名称和描述。
- 删除知识库。
- 查看真实 file_count 和 chunk_count 字段。

本步骤不新增后端核心功能，不处理 MinerU token、embedding-service、reranker、LLM、SSE 或真实解析索引端到端。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `2. Admin 创建、编辑、删除知识库空间`：本步骤前端页面接入真实创建、编辑和删除接口。
  - `22. 记录 Admin 高危操作审计日志`：本步骤调用已有后端 API，审计写入由 Step 006 后端逻辑完成。
- `3.1 前端`：继续使用 Vue 3、Vite、TypeScript strict、Vue Router、Element Plus。
- `4.4 knowledge_bases`：
  - 状态为 `active/deleting/deleted`。
  - 只有 Admin 可创建、编辑、删除知识库。
  - 删除知识库采用软删除。
- `13.8 Phase 8：前端后台管理与问答页面`：本步骤聚焦知识库管理页面真实接口联调。

## 3. 本步骤完成内容

- 扩展前端 API client：
  - `listKnowledgeBases(query)` 支持 `page`、`page_size`、`keyword`、`status`。
  - `updateKnowledgeBase()` 调用 `PATCH /knowledge-bases/{id}`。
  - `deleteKnowledgeBase()` 调用 `DELETE /knowledge-bases/{id}`。
- 知识库管理页接入真实后端：
  - 未登录时跳转登录页。
  - 页面加载时读取真实 active 知识库列表。
  - 支持 keyword 查询。
  - 支持切换到 `deleted` 查询软删除知识库。
  - 支持新建知识库。
  - 支持编辑名称和描述。
  - 支持删除知识库并触发后端软删除。
  - 展示真实 `file_count` 和 `chunk_count`。
  - 保留跳转到 Chat 和 Files 页的入口。
- 移除不符合 SDD v0.1 范围的前端展示：
  - 删除原页面中“外部数据源实时同步 / 自动化向量更新”的营销型卡片。
  - 页面文案收敛为知识库创建、维护、软删除等 SDD 已规定能力。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 扩展知识库列表查询、编辑和删除 API 封装 |
| `frontend/src/views/KnowledgeBasesView.vue` | 修改 | 知识库管理页从模拟数据切换为真实后端 API，支持创建/编辑/删除/查询 |
| `docs/progress/step-017-frontend-knowledge-bases.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 017 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 列表查询：
  - `statusFilter='all'` 时不向后端传 `status`，后端默认返回 active 且未软删除知识库。
  - 切换 `deleted` 时传 `status=deleted`，Admin 可查看软删除知识库。
- 创建/编辑：
  - 使用 Element Plus dialog。
  - 创建时调用 `POST /knowledge-bases`。
  - 编辑时调用 `PATCH /knowledge-bases/{id}`。
  - 名称为空时前端阻止提交。
- 删除：
  - 使用确认框防止误删。
  - 调用 `DELETE /knowledge-bases/{id}`，由后端执行软删除并写入审计日志。
- 页面边界：
  - 仅展示 SDD 已规定的知识库管理能力。
  - 不展示外部数据源同步、自动化向量更新等 SDD 未规定核心功能。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 34 passed，1 个 Starlette/httpx deprecation warning |
| KnowledgeBase API smoke | 使用 `backend/.venv/bin/python` 调用登录、创建、更新、active 列表、删除、deleted 列表 | 通过 | 登录 200、创建 201、更新 200、active 列表 200 且命中、删除 204、deleted 列表 200 且命中 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |

## 7. 当前未完成事项

- Users 页面仍主要是模拟数据，尚未接入真实 Users API。
- AuditLogs 页面仍主要是模拟数据，尚未接入真实 Audit Logs API。
- Profile 页面仍主要是模拟数据，尚未接入真实 `/auth/me` 或 user profile API。
- 知识库列表当前读取前 50 条，尚未实现完整分页 UI。
- 真实 MinerU 在线解析仍缺少 `MINERU_API_TOKEN`。
- 真实 embedding-service 仍未接入。
- Chat 仍是非流式 JSON Demo，不是 SSE/LLM。

## 8. 风险与注意事项

- 当前 KnowledgeBase API 的 `file_count` 和 `chunk_count` 仍由后端返回基础值；如后端后续实现真实聚合统计，页面无需改变字段即可展示。
- 删除知识库后，相关 cleanup job 尚未实现；该限制已在前序进度文件中记录。
- 当前前端无法区分 Admin/User 权限展示按钮；普通 User 如果访问创建/编辑/删除操作，后端会返回 403。后续可在 Profile/Auth 状态真实接入后细化按钮可见性。
- Step 016 的真实解析索引端到端人工确认项仍未解除。

## 9. 下一步建议

建议进入 Step 018：前端 Users 与 AuditLogs 页面真实接口联调。

原因：

- 这两个页面的后端 API 已存在，且不依赖 MinerU token 或 embedding-service。
- 完成后，第一版 Demo 的后台管理部分将从“部分真实、部分模拟”进一步收敛为真实数据。
- 同时可让 Admin 高危操作审计在页面上可见，补强 SDD MVP 的审计要求。

Step 018 建议范围：

- `UsersView.vue` 接入真实 Users API：列表、新建、启用/禁用、重置密码。
- `AuditLogsView.vue` 接入真实 Audit Logs API：列表、筛选、详情展示。
- 不新增后端核心功能，不处理真实解析索引端到端。
