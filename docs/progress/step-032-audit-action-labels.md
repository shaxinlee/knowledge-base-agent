# Step 032：审计日志前端可读操作文案

## 1. 本步骤目标

优化审计日志页面的操作类型展示，将用户管理、知识库和文件相关 action 从原始英文枚举展示为可读中文文案，同时保留原始 action code 便于排查。

## 2. 对应 SDD 条目

- SDD v0.1：前端核心页面需要支持管理和审计日志查询。
- TDD v0.1：
  - `TDD-AUDIT-003`：用户管理操作写入 audit_logs。
  - `TDD-AUDIT-005`：审计列表筛选可按 action/resource_type 查询。
- Step 031 下一步建议：用户管理审计日志已写入，前端需要展示可读文案。

## 3. 本步骤完成内容

- 审计日志页面新增 `formatAction()`。
- 审计日志页面新增 `formatResourceType()`。
- 操作类型下拉框显示中文文案，但提交给后端的筛选值仍保留原始 action。
- 资源类型下拉框显示中文文案，但提交给后端的筛选值仍保留原始 resource_type。
- 审计日志表格显示中文操作文案，同时在已映射时保留原始 action code。
- 审计详情弹窗显示中文操作文案，同时保留原始 action code。
- 审计详情弹窗资源字段显示中文资源类型，同时保留原始 resource_type code。
- 更新 Demo 文档，说明审计日志页面以可读中文文案展示常见操作类型。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/views/AuditLogsView.vue` | 修改 | 增加 action/resource_type 中文文案映射，并优化列表和详情展示 |
| `docs/demo/first-version-demo.md` | 修改 | 补充审计日志页面可读中文文案说明 |
| `docs/progress/step-032-audit-action-labels.md` | 新增 | 记录 Step 032 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 032 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- `formatAction()` 当前覆盖：
  - `create_knowledge_base` -> `创建知识库`
  - `update_knowledge_base` -> `更新知识库`
  - `delete_knowledge_base` -> `删除知识库`
  - `upload_file` -> `上传文件`
  - `delete_file` -> `删除文件`
  - `create_user` -> `创建用户`
  - `update_user` -> `更新用户`
  - `disable_user` -> `禁用用户`
  - `enable_user` -> `启用用户`
  - `reset_user_password` -> `重置密码`
- `formatResourceType()` 当前覆盖 `knowledge_base`、`file`、`user`。
- 筛选值仍使用后端原始枚举，避免改变 API contract。
- 未映射 action/resource_type 会按原值展示，保证向后兼容。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建测试 | `npm run build` | 通过 | Vite build 成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞构建 |
| 前端访问检查 | `curl -fsS http://localhost:5173 >/dev/null` | 通过 | 前端服务可访问 |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 源码关键字扫描 | `rg -n 'formatAction|formatResourceType|创建用户|更新用户|禁用用户|启用用户|重置密码|reset_user_password' frontend/src/views/AuditLogsView.vue` | 通过 | 可定位 action/resource_type 文案映射和展示引用 |
| 后端测试 | 未执行 | 未执行 | 本步骤未修改后端代码；Step 031 已完成后端审计写入验证 |
| Playwright 页面测试 | 未执行 | 未执行 | 当前仓库尚未配置 Playwright 测试体系；本步骤使用 typecheck/build 和源码扫描作为最小验证 |

## 7. 当前未完成事项

- 审计日志高级筛选、导出和保留策略尚未实现。
- 审计日志 response 当前仍无 request_id 字段，页面展示并复制日志 ID。
- cleanup job 与 indexed 文件删除后的 Qdrant 清理/失效验证仍未完成。
- 真实带引用回答仍依赖 MinerU API token、embedding-service、reranker-service 和 LLM Provider。

## 8. 风险与注意事项

- 本步骤仅优化前端显示，不改变后端 action 值和筛选 API。
- 新增 action 后如果没有映射，会显示原始 action 字符串；后续可按需扩展映射表。
- 当前未执行浏览器自动化点击/筛选验证。

## 9. 下一步建议

建议进入 Step 033：文件删除后 indexed chunks/Qdrant 清理或失效验证方案。

原因：`TDD-FILE-012` 仍要求删除 indexed 文件后 chunks inactive，Qdrant points 失效或清理，并写 audit log。当前文件软删除和审计已实现，但 indexed 删除后的 Qdrant 失效/清理真实验证仍是缺口。该步骤应先核对当前删除逻辑和 Qdrant client 能力，再决定是补实现还是形成需要人工确认的验证边界。
