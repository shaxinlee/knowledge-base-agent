# Specs

本目录保存知识库 Agent 助手的规范驱动开发文档。

## 主规范

- `SDD.v0.1.md`：v0.1 主 SDD，是产品范围、架构边界、数据库设计、接口边界、开发里程碑和验收标准的事实来源。

## 命名约定

- 主 SDD 使用 `SDD.v{major}.{minor}.md`。
- 主 TDD 放在 `../tests/`，使用 `TDD.v{major}.{minor}.md`。
- API 子规范放在 `../api/`，并通过 `frontend-backend-api-contract.md` 和 `openapi.v0.1.yaml` 同步表达。
- 前端接口类型放在 `../../frontend/src/api/types.ts`，必须与 API 子规范保持一致。

## 使用约定

- 开始实现前先阅读 `SDD.v0.1.md`。
- 编写或验收测试前阅读 `../tests/TDD.v0.1.md`。
- 产品、架构、数据库、后端、前端、检索链路和部署变更必须能回溯到主 SDD。
- 若接口发生变化，必须同步更新中文 API 契约、OpenAPI 文件和前端类型定义。
- v0.1 不得自行加入主 SDD 明确排除的能力。
