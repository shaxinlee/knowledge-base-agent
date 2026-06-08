# Step 027：当前用户删除自己 conversation 接口

## 1. 本步骤目标

实现 `DELETE /api/v1/conversations/{conversation_id}`，允许当前登录用户软删除自己的会话，并确保其他用户不能删除不属于自己的会话。

## 2. 对应 SDD 条目

- SDD v0.1：会话 API 包含 `DELETE /api/v1/conversations/{conversation_id}`。
- SDD v0.1：用户只能访问自己的会话。
- SDD v0.1：文件、知识库、会话等对象不做物理即时删除，需要采用 `deleted_at` 软删除。
- TDD v0.1：`TDD-CONV-003`，当前用户删除自己的会话返回 `204`，其他用户不可删除。

## 3. 本步骤完成内容

- 新增 conversation service 层软删除函数。
- 新增 `DELETE /api/v1/conversations/{conversation_id}` 路由。
- 删除会话时将 conversation 状态置为 `deleted`，写入 `deleted_at` 和 `updated_at`。
- 删除后复用已有查询边界，列表和详情默认不返回 deleted conversation。
- 新增后端测试验证：
  - 其他用户删除返回 `404 RESOURCE_NOT_FOUND`。
  - 当前用户删除自己的 conversation 返回 `204 No Content`。
  - 删除后当前用户读取详情返回 `404 RESOURCE_NOT_FOUND`。
  - 删除后当前用户 conversation 列表不再包含该会话。
  - 数据库中 conversation 状态为 `deleted` 且 `deleted_at` 非空。
- 更新 TDD 当前状态，标记删除会话基础测试已实现。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/conversations.py` | 修改 | 新增 `delete_conversation()`，按当前用户权限执行软删除 |
| `backend/app/api/v1/conversations.py` | 修改 | 新增 `DELETE /api/v1/conversations/{conversation_id}` 路由 |
| `backend/tests/test_conversations_api.py` | 修改 | 新增 conversation soft delete 权限和状态测试 |
| `docs/tests/TDD.v0.1.md` | 修改 | 更新 `TDD-CONV-003` 当前实现状态 |
| `docs/progress/step-027-conversation-delete-api.md` | 新增 | 记录 Step 027 的目标、实现、验证结果和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 027 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- 删除接口复用 `require_user_conversation()`，因此：
  - conversation 不存在返回 `RESOURCE_NOT_FOUND`。
  - conversation 不属于当前用户返回 `RESOURCE_NOT_FOUND`。
  - conversation 已删除返回 `RESOURCE_NOT_FOUND`。
- 本步骤只软删除 conversation 本身，不物理删除 messages、citations、traces 或 feedback，符合 SDD 对历史会话数据保留的方向。
- 删除后列表查询和详情查询已经通过 `status == active` 与 `deleted_at IS NULL` 默认过滤，因此无需额外改查询逻辑。
- 本步骤未新增数据库 migration，因为 `conversations.status` 和 `conversations.deleted_at` 字段已经存在。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_conversations_api.py::test_user_can_soft_delete_own_conversation_and_other_user_cannot_delete -q` | 通过 | 1 passed；验证当前用户软删除和其他用户不可删除 |
| 格式检查 | `backend/.venv/bin/black --check backend/app/services/conversations.py backend/app/api/v1/conversations.py backend/tests/test_conversations_api.py` | 通过 | 3 files would be left unchanged |
| Lint 检查 | `backend/.venv/bin/ruff check backend/app backend/tests` | 通过 | All checks passed |
| 类型检查 | `backend/.venv/bin/mypy backend/app` | 通过 | Success: no issues found in 62 source files |
| 后端测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 38 passed, 58 warnings |
| Docker Compose 配置检查 | `docker compose config --quiet` | 通过 | Compose 配置可解析 |
| Docker Compose 运行服务检查 | `docker compose ps --services --filter status=running` | 通过 | 当前运行服务包括 backend-api、frontend、minio、postgres、qdrant、redis |
| 后端健康检查 | `curl -fsS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| 数据库迁移检查 | 未执行 | 未执行 | 本步骤未修改数据库结构 |
| 前端构建测试 | 未执行 | 未执行 | 本步骤未修改前端代码 |

## 7. 当前未完成事项

- 前端 Chat 历史会话列表尚未提供删除按钮；本步骤只完成后端接口。
- 删除会话当前不写 audit_logs；SDD 未明确要求 conversation 删除进入审计，本步骤不扩展。
- 删除会话后 messages/citations/traces/feedback 仍保留，后续如需要后台合规清理，需要另行设计 retention/cleanup 任务。

## 8. 风险与注意事项

- 删除接口返回 `404 RESOURCE_NOT_FOUND` 来隐藏非本人会话存在性，延续当前会话读取权限策略。
- 当前运行中的 backend-api 容器健康检查通过，但容器内代码是否已热加载取决于 Compose 挂载和服务状态；本步骤的可靠验证以本地 venv 测试结果为准。
- 既有测试 warning 仍存在：Starlette/httpx deprecation warning 与开发环境 JWT secret 过短 warning；本步骤未处理这些非阻塞项。

## 9. 下一步建议

建议进入 Step 028：为前端 Chat 历史会话列表接入删除会话交互。

原因：后端删除会话接口已经完成，前端当前仍只能创建和打开历史会话。将删除入口接入前端可以形成用户可操作的会话生命周期闭环，并能通过浏览器页面或接口 smoke 验证 Demo 体验。
