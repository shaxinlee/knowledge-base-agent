# Step 031：用户管理操作审计日志写入

## 1. 本步骤目标

为 Admin 用户管理操作写入 `audit_logs`，补齐用户创建、更新、禁用、启用、重置密码等操作的可追溯记录，完成 `TDD-AUDIT-003` 的后端基础验收。

## 2. 对应 SDD 条目

- SDD v0.1：Admin/User 权限边界。
- SDD v0.1：高风险管理操作需要进入审计日志。
- TDD v0.1：
  - `TDD-AUDIT-003`：Admin 禁用/启用/重置密码写入 audit_logs。
  - `TDD-AUDIT-005`：审计列表筛选可按 action/resource_type 查询。

## 3. 本步骤完成内容

- Users API 路由将当前 Admin、IP、User-Agent 传入 users service。
- `create_user` 写入 `create_user` 审计日志。
- `update_user` 写入 `update_user` 审计日志。
- `disable_user` 写入 `disable_user` 审计日志。
- `enable_user` 写入 `enable_user` 审计日志。
- `reset_password` 写入 `reset_user_password` 审计日志。
- 审计 details 记录用户管理前后快照。
- 重置密码审计只记录 `password_changed=true`，不记录明文密码或 password hash。
- 更新 Users API 测试，验证五类用户管理操作均写入 audit_logs。
- 更新 TDD 和 Demo 文档，说明用户管理审计已实现。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/api/v1/users.py` | 修改 | Users API 接收 Request，并传入 actor、ip_address、user_agent |
| `backend/app/services/users.py` | 修改 | 用户创建/更新/禁用/启用/重置密码写入 audit_logs |
| `backend/tests/test_users_api.py` | 修改 | 增加用户管理操作审计日志断言，并验证重置密码不泄露密码 |
| `docs/tests/TDD.v0.1.md` | 修改 | 更新 `TDD-AUDIT-003` 当前状态 |
| `docs/demo/first-version-demo.md` | 修改 | 补充用户管理操作写入审计日志说明 |
| `docs/progress/step-031-users-audit-logs.md` | 新增 | 记录 Step 031 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 031 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 本步骤复用既有 `create_audit_log()`，不新增数据库表或字段。
- 用户审计 `resource_type` 统一为 `user`，`resource_id` 为目标用户 ID。
- action 命名：
  - `create_user`
  - `update_user`
  - `disable_user`
  - `enable_user`
  - `reset_user_password`
- 用户快照包含 id、email、username、display_name、role、status、failed_login_count。
- 审计日志不记录 password hash，也不记录重置后的明文密码。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_users_api.py::test_admin_can_create_list_update_disable_enable_and_reset_user -q` | 通过 | 1 passed；验证 create/update/disable/enable/reset-password 五类审计日志 |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app/services/users.py backend/app/api/v1/users.py backend/tests/test_users_api.py` | 通过 | 3 files would be left unchanged |
| 后端 Lint | `backend/.venv/bin/ruff check backend/app backend/tests` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app` | 通过 | Success: no issues found in 62 source files |
| 后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 38 passed, 58 warnings |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 前端构建测试 | 未执行 | 未执行 | 本步骤未修改前端代码 |
| 数据库迁移检查 | 未执行 | 未执行 | 本步骤未修改数据库结构 |

## 7. 当前未完成事项

- 审计日志仍未包含 request_id 字段，前端当前展示并复制日志 ID。
- 审计日志导出、保留策略和高级筛选不在当前步骤范围。
- cleanup job 与 indexed 文件删除后的 Qdrant 清理/失效验证仍未完成。
- 真实带引用回答仍依赖 MinerU API token、embedding-service、reranker-service 和 LLM Provider。

## 8. 风险与注意事项

- 用户管理审计 details 包含 email/username/display_name/role/status 等管理信息；不包含密码或 password hash。
- 本步骤不会改变用户管理 API response 结构。
- 既有测试 warning 仍存在：Starlette/httpx deprecation warning 与开发环境 JWT secret 过短 warning；本步骤未处理这些非阻塞项。

## 9. 下一步建议

建议进入 Step 032：审计日志前端展示用户管理操作可读文案。

原因：后端已写入用户管理审计日志，前端审计页可以读取真实数据，但 action 当前仍以原始英文枚举展示。补齐用户管理 action 的可读展示能提升 Demo 可验收性，且不依赖外部模型服务。
