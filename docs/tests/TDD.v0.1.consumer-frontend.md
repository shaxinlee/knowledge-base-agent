# 知识库 Agent 助手 v0.1 to C 用户端前端分层 TDD

| 字段 | 内容 |
| --- | --- |
| 版本 | v0.1 consumer-frontend |
| 定位 | to C 用户端前端分层补充测试设计 |
| 上游规范 | `docs/specs/SDD.v0.1.consumer-frontend.md` |
| 主测试基线 | `docs/tests/TDD.v0.1.md` |
| 测试重点 | 路由权限、角色导航、只读知识库、当前 SaaS 问答链路回归、管理端不回退 |

## 0. 文档定位

本文档是 `docs/tests/TDD.v0.1.md` 的补充测试设计，覆盖 `docs/specs/SDD.v0.1.consumer-frontend.md` 中定义的 to C 用户端前端分层、to B 管理后台保留、用户端只读知识库和问答 UI 回归测试。

主测试基线仍是 `docs/tests/TDD.v0.1.md`。本文不替代主 TDD 中关于认证、RBAC、知识库、文件上传、解析、检索、rerank、SSE、引用、trace、feedback、审计和 Docker Compose 的 P0/P1 测试要求。

本文只补充以下测试范围：

- 前端路由权限。
- 入口选择页。
- 登录后角色跳转。
- 用户端导航。
- 管理端导航。
- 用户端只读知识库页面。
- 用户端问答页面继续复用当前 SaaS 问答接口。
- 管理端原有入口不回退。
- 用户端中文文案和范围外功能排除。

## 1. 测试目标

本补充 TDD 需要证明：

1. 前端根路径提供用户页面和管理员页面两个入口。
2. 用户页面必须先选择一个 Admin 用户管理中已注册且启用的普通用户，无需输入密码即可进入，并只获得该普通 `user` 权限。
3. 管理员页面必须使用账号密码登录。
4. `user` 和 `admin` 的页面入口已分层。
5. 普通用户只能只读查看 active 知识库和文件。
6. to C 问答页继续使用当前 SaaS conversation SSE 问答接口。
7. to C 问答页未新增前端本地问答算法或模拟回答。
8. 管理员原有管理功能不回退。
9. 正式文案为中文。
10. 用户端不出现原型中的社区、公开知识库、Premium、Billing、Trash、Help、语音输入等范围外功能入口。

## 2. 测试范围

### 2.1 范围内

- 登录后角色跳转。
- 入口选择页点击进入。
- 路由守卫。
- 用户端导航。
- 管理端导航。
- `/chat` 问答主流程。
- `/chat` citation 展示。
- `/chat` helpful / unhelpful 反馈。
- `/chat` 历史会话打开和删除。
- `/knowledge` 只读知识库卡片展示。
- `/knowledge` 只读文件列表展示。
- `/profile` 按角色展示。
- 前端类型检查。
- 前端生产构建。
- 管理后台入口回归。

### 2.2 范围外

- 后端 RAG 算法正确性重新评测。
- embedding 服务替换。
- reranker 服务替换。
- LLM 服务替换。
- OpenSearch / BM25 排名质量评测。
- 公开注册。
- 移动端 App。
- 计费。
- 社区。
- 公开知识库。
- 文档级权限。

## 3. 测试数据

测试环境应准备：

- 现有 admin 账号。
- 已有普通 user 账号，或由 admin 创建一个普通用户。
- 至少一个 active 知识库。
- 至少一个 active 知识库中包含 indexed 文件，用于问答引用验证。
- 可复用当前真实 `测试` 知识库，或测试环境中的 fixture 知识库。

不要求为本补充 TDD 新增测试数据格式。若使用 fixture，应继续遵守主 TDD 对 Demo fixture 的标记和边界要求，不得将 fixture 伪装为真实解析结果。

## 4. P0 测试用例

| 用例编号 | 用例名称 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| TDD-CONSUMER-ENTRY-001 | 首页显示双入口 | 打开前端根路径 | 访问 `/` | 显示“用户页面”和“管理员页面”两个选项 |
| TDD-CONSUMER-ENTRY-002 | 用户页面选择用户后免密进入 | 浏览器无有效 token，存在已注册启用普通用户 | 在 `/` 选择一个用户并点击进入用户页面 | 自动创建所选普通用户会话并进入 `/chat` |
| TDD-CONSUMER-ENTRY-003 | 用户页面 token 无管理权限 | 已通过用户页面进入 | 访问 `/users` | 跳转 `/forbidden` 或后端返回 `403 FORBIDDEN` |
| TDD-CONSUMER-ENTRY-005 | 用户页面下拉来自用户管理 | Admin 已创建多个启用普通用户，并禁用一个普通用户 | 访问 `/` 查看用户页面下拉 | 下拉显示启用普通用户的名称，不显示 admin 或已禁用用户 |
| TDD-CONSUMER-ENTRY-004 | 管理员页面进入登录 | 浏览器可能已有普通用户 token | 在 `/` 点击管理员页面 | 清理当前 token 并进入 `/login` |
| TDD-CONSUMER-AUTH-001 | 未登录访问 `/chat` 跳转登录 | 浏览器无有效 token | 访问 `/chat` | 跳转 `/login` |
| TDD-CONSUMER-AUTH-002 | 未登录访问 `/knowledge` 跳转登录 | 浏览器无有效 token | 访问 `/knowledge` | 跳转 `/login` |
| TDD-CONSUMER-AUTH-003 | 普通用户登录后进入问答页 | 存在 active 普通用户 | 使用普通用户登录 | 登录成功后进入 `/chat` |
| TDD-CONSUMER-AUTH-004 | 管理员登录后进入管理页 | 存在 admin 用户 | 使用 admin 登录 | 登录成功后进入 `/knowledge-bases` 或登录前目标页 |
| TDD-CONSUMER-RBAC-001 | 普通用户不能访问知识库管理 | 普通用户已登录 | 访问 `/knowledge-bases` | 跳转 `/forbidden` |
| TDD-CONSUMER-RBAC-002 | 普通用户不能访问文件管理 | 普通用户已登录 | 访问 `/files` | 跳转 `/forbidden` |
| TDD-CONSUMER-RBAC-003 | 普通用户不能访问用户管理 | 普通用户已登录 | 访问 `/users` | 跳转 `/forbidden` |
| TDD-CONSUMER-RBAC-004 | 普通用户不能访问审计日志 | 普通用户已登录 | 访问 `/audit-logs` | 跳转 `/forbidden` |
| TDD-CONSUMER-CHAT-001 | 普通用户可进入问答页 | 普通用户已登录 | 访问 `/chat` | 页面显示知识库选择器 |
| TDD-CONSUMER-CHAT-002 | 问答页继续调用当前 SSE 接口 | 普通用户已登录且有 active 知识库 | 选择知识库并发送问题 | 请求当前 conversation message SSE 接口，返回 `text/event-stream` |
| TDD-CONSUMER-CHAT-003 | 回答显示 citation 信息 | active 知识库有可召回 indexed 文件 | 发送与知识库内容相关的问题 | 回答完成后显示引用编号、文件名、source_locator 和原文片段 |
| TDD-CONSUMER-CHAT-004 | 普通用户可提交反馈 | 已产生 assistant message | 点击 helpful 或 unhelpful | 反馈提交成功并回显当前选择 |
| TDD-CONSUMER-KB-001 | 普通用户可查看知识库卡片 | 普通用户已登录且有 active 知识库 | 访问 `/knowledge` | 页面显示 active 知识库卡片 |
| TDD-CONSUMER-KB-002 | 普通用户可查看知识库文件 | `/knowledge` 已加载知识库卡片 | 点击知识库卡片 | 页面显示该知识库文件列表 |
| TDD-CONSUMER-KB-003 | 用户端知识库页无管理入口 | 普通用户已登录 | 访问 `/knowledge` 并检查页面 | 不出现创建、上传、编辑、删除、重试解析入口 |
| TDD-CONSUMER-ADMIN-001 | 管理员可访问管理页面 | admin 已登录 | 访问 `/knowledge-bases`、`/files`、`/users`、`/audit-logs` | 各页面可访问且不跳转 forbidden |
| TDD-CONSUMER-ADMIN-002 | 管理员原有管理入口可见 | admin 已登录 | 查看管理端导航和页面操作区 | 创建知识库、上传文件、用户管理入口仍可见 |

## 5. P1 测试用例

| 用例编号 | 用例名称 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| TDD-CONSUMER-NAV-001 | 普通用户导航最小化 | 普通用户已登录 | 查看左侧导航 | 只显示对话问答、知识库、个人资料、退出 |
| TDD-CONSUMER-NAV-002 | 管理员导航保留管理菜单 | admin 已登录 | 查看左侧导航 | 显示管理后台菜单 |
| TDD-CONSUMER-CHAT-005 | 无 active 知识库时不允许创建 | 普通用户已登录且无 active 知识库 | 访问 `/chat` | 显示“暂无可用知识库，请联系管理员维护知识库”，无创建按钮 |
| TDD-CONSUMER-CHAT-006 | 历史会话能力保持可用 | 普通用户有历史会话 | 访问 `/chat`，搜索、打开、删除自己的会话 | 历史会话列表、打开和删除功能正常 |
| TDD-CONSUMER-CHAT-007 | 图片引用仍可预览 | 回答包含图片 citation | 点击图片引用或预览入口 | 图片可加载并可预览 |
| TDD-CONSUMER-KB-004 | 知识库无文件空状态 | active 知识库无文件 | 在 `/knowledge` 选择该知识库 | 显示“当前知识库暂无文件。” |
| TDD-CONSUMER-KB-005 | 文件信息格式可读 | active 知识库有文件 | 查看 `/knowledge` 文件列表 | 文件状态、大小、更新时间格式可读 |
| TDD-CONSUMER-PROFILE-001 | 普通用户 profile 只显示个人资料 | 普通用户已登录 | 访问 `/profile` | 只显示个人资料，不显示助手配置 |
| TDD-CONSUMER-PROFILE-002 | 管理员 profile 显示助手配置 | admin 已登录 | 访问 `/profile` | 显示个人资料和助手配置 |
| TDD-CONSUMER-COPY-001 | 用户端无原型英文占位 | 普通用户已登录 | 检查 `/chat`、`/knowledge`、`/login` 主要可见文案 | 不出现原型英文占位、Premium、Billing、Trash、Help、社区、公开知识库入口 |

## 6. 自动化与人工验收

### 6.1 必跑检查

前端实现完成后必须运行：

```bash
npm run typecheck
npm run build
```

### 6.2 建议检查

如当前 lint 配置可用，建议运行：

```bash
npm run lint
```

### 6.3 E2E 建议

如果已有 Playwright、Cypress 或等价前端 E2E 基础，应优先覆盖：

- 登录跳转。
- 普通用户路由拦截。
- 管理员路由访问。
- `/chat` SSE smoke。
- `/chat` citation 展示。
- `/chat` feedback 提交。
- `/knowledge` 只读知识库展示。
- `/knowledge` 文件列表展示。

如果尚未落地 E2E 自动化，先按本文 P0/P1 用例进行人工验收，并在验收记录中写明环境、账号、知识库、文件和结果。

## 7. 通过门槛

本补充 TDD 的通过门槛如下：

1. 所有 P0 用例必须通过。
2. P1 中路由、导航、只读知识库、问答引用相关用例必须通过。
3. 前端 `npm run typecheck` 必须通过。
4. 前端 `npm run build` 必须通过。
5. 管理端原有核心能力不得回退。
6. 不允许出现新的前端模拟问答算法。
7. 普通用户不得看到知识库或文件增删改入口。
8. 用户端主要页面不得出现原型英文占位或范围外商业化入口。
