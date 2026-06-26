# API Contract

本目录保存知识库 Agent 助手 v0.1 的前后端接口契约。

文件说明：

- `frontend-backend-api-contract.md`：中文接口说明，供产品、前端、后端、测试联调时阅读。
- `openapi.v0.1.yaml`：OpenAPI 3.1 契约，供后端实现、接口测试、自动化工具参考。
- `../../frontend/src/api/types.ts`：前端 TypeScript 类型定义，页面和 API client 开发时直接引用。

上游规范：

- `../specs/SDD.v0.1.md`：v0.1 主 SDD，定义产品范围、架构边界、验收标准和禁止扩展项。

开发约定：

- 后端实现接口时必须以本目录契约为准。
- 前端调用接口时必须优先使用 `frontend/src/api/types.ts` 中的类型。
- 如接口发生变化，应同时更新中文契约、OpenAPI 文件和前端类型。
- v0.1 不新增主 SDD 禁止的接口，例如跨知识库查询、GraphRAG 查询、Text2SQL、文档级权限、用户组和 Editor 角色。
