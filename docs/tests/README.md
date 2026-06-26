# Tests

本目录保存知识库 Agent 助手的测试设计与验收文档。

## 主测试文档

- `TDD.v0.1.md`：v0.1 测试设计文档，是测试范围、测试数据、测试用例、验收门槛和缺陷分级的事实来源。

## 补充测试文档

- `TDD.v0.1.consumer-frontend.md`：to C 用户端前端分层、路由权限、只读知识库和问答 UI 回归测试补充设计。主 TDD 仍是 v0.1 总测试基线，本补充文档只覆盖本次前端分层变更。

## 当前状态入口

- `../demo/first-version-demo.md`：当前第一版基础 Web Demo 的可运行流程、验收边界和外部依赖缺口。
- `../progress/README.md`：分步骤开发进度、已完成验证、未完成事项和下一步建议。

## 上游规范

- `../specs/SDD.v0.1.md`：v0.1 主 SDD。
- `../specs/SDD.v0.1.consumer-frontend.md`：to C 用户端前端分层补充 SDD。
- `../api/frontend-backend-api-contract.md`：中文 API 契约。
- `../api/openapi.v0.1.yaml`：OpenAPI 机器可读接口契约。

## 命名约定

- 主测试设计文档使用 `TDD.v{major}.{minor}.md`。
- 测试用例编号使用 `TDD-{AREA}-{NUMBER}`，例如 `TDD-FILE-001`。
- 自动化测试代码应按后端、前端、接口契约和端到端场景分层组织。

## 使用约定

- 开发功能前先阅读 SDD，编写或更新对应 TDD 用例，再实现代码。
- 接口变更必须同步更新 API 契约、OpenAPI、前端类型和 TDD。
- 修复缺陷时必须补充或更新能复现该缺陷的测试用例。
- v0.1 内测前必须执行 `TDD.v0.1.md` 中定义的 P0/P1 用例。
