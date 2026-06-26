# 第一版 Demo 前端验收清单

本文档固化第一版 Web Demo 的前端验收流程，重点覆盖 Step 034 已打通的受限 Demo fixture citation 链路。该清单用于人工验收，也可作为后续 Playwright/Cypress 自动化用例的步骤来源。

## 1. 验收定位

本清单验证的是当前第一版 Web Demo 的前端可演示闭环：

- 登录。
- 选择 Demo fixture 知识库。
- 创建/打开会话。
- 发送推荐问题。
- 查看 assistant answer 中的引用编号。
- 查看 citation 详情。
- 提交 helpful / unhelpful feedback。

本清单不验证真实 MinerU 解析、真实 embedding-service、真实 reranker-service 或真实 LLM 输出质量。

## 2. 前置条件

1. Docker Compose 基础栈正在运行。
2. 后端 migration 已升级到 head。
3. `.env` 中已设置：

```bash
DEMO_FIXTURE_ENABLED=true
```

4. 后端容器已重新创建，使 `.env` 生效：

```bash
docker compose up -d --force-recreate backend-api
```

5. 已执行 Demo fixture seed：

```bash
docker compose exec backend-api python -m app.dev.seed_demo_fixture
```

6. 前端可访问：

```bash
curl -fsS http://localhost:5173 >/dev/null
```

7. 后端健康检查通过：

```bash
curl -fsS http://localhost:8000/api/v1/health
```

## 3. Demo 账号与数据

| 项目 | 值 |
|---|---|
| 前端地址 | `http://localhost:5173` |
| Demo User | `demo_user` |
| Demo User 密码 | `DemoUserPassword123` |
| 知识库 | `Demo Fixture 知识库` |
| 文件 | `demo-rag-fixture.txt` |
| 推荐问题 | `井下落鱼可视化工具 使用步骤是什么？` |

## 4. 页面验收步骤

| 步骤 | 操作 | 预期结果 |
|---|---|---|
| 1 | 打开 `http://localhost:5173` | 显示登录页 |
| 2 | 使用 `demo_user` / `DemoUserPassword123` 登录 | 进入 Chat 页面 |
| 3 | 在知识库下拉框选择 `Demo Fixture 知识库` | Chat 页面切换到该知识库 |
| 4 | 点击“新建对话” | 消息区清空，准备提问 |
| 5 | 输入推荐问题并点击“发送” | 消息区出现用户问题和 assistant 回答 |
| 6 | 检查 assistant 回答 | 回答正文包含 `[1]` 引用编号 |
| 7 | 点击 citation chip | 右侧“引用详情”展示 `demo-rag-fixture.txt`、`demo:section-1` 和原文片段 |
| 8 | 点击“有帮助” | helpful 按钮变为 active 状态 |
| 9 | 重新打开该历史会话 | assistant message 的 helpful 状态保持回显 |
| 10 | 点击“没帮助” | feedback 更新为 unhelpful，按钮 active 状态切换 |

## 5. 建议自动化选择器

Step 035 已在 Chat 页面增加以下稳定选择器，后续自动化测试应优先使用这些 selector，而不是依赖中文文案或 CSS class：

| Selector | 用途 |
|---|---|
| `[data-testid="chat-demo-page"]` | Chat Demo 页面根节点 |
| `[data-testid="knowledge-base-select"]` | 知识库选择 |
| `[data-testid="new-conversation-button"]` | 新建对话 |
| `[data-testid="conversation-search-input"]` | 搜索历史会话 |
| `[data-testid="conversation-row"]` | 历史会话行 |
| `[data-testid="conversation-open-button"]` | 打开历史会话 |
| `[data-testid="message-list"]` | 消息列表 |
| `[data-testid="message-bubble-user"]` | 用户消息气泡 |
| `[data-testid="message-bubble-assistant"]` | Assistant 消息气泡 |
| `[data-testid="message-composer"]` | 消息输入框 |
| `[data-testid="send-message-button"]` | 发送按钮 |
| `[data-testid="citation-chip-list"]` | 引用 chip 列表 |
| `[data-testid="citation-chip"]` | 单个引用 chip |
| `[data-testid="citation-panel"]` | 右侧引用面板 |
| `[data-testid="citation-detail"]` | 引用详情卡片 |
| `[data-testid="citation-detail-file-name"]` | 引用文件名 |
| `[data-testid="citation-detail-excerpt"]` | 引用原文片段 |
| `[data-testid="citation-detail-source-locator"]` | 引用定位 |
| `[data-testid="feedback-helpful-button"]` | helpful 反馈按钮 |
| `[data-testid="feedback-unhelpful-button"]` | unhelpful 反馈按钮 |

## 6. 当前自动化状态

- 当前仓库尚未引入 Playwright/Cypress。
- Step 035 未新增浏览器自动化依赖，避免扩大第一版 Demo 的依赖面。
- 当前已通过前端 `typecheck`、`build`、源码 selector 扫描和真实后端 API citation/feedback smoke 间接验证前端验收链路所需数据可用。

## 7. 验收结论记录模板

执行人工验收时，可复制以下模板到进度文件或验收记录中：

```text
验收时间：
验收人：
浏览器：
前端地址：http://localhost:5173
后端地址：http://localhost:8000/api/v1/health
Demo fixture seed：已执行 / 未执行
登录 demo_user：通过 / 失败
选择 Demo Fixture 知识库：通过 / 失败
发送推荐问题：通过 / 失败
回答包含 [1]：通过 / 失败
citation 文件名/locator/片段展示：通过 / 失败
helpful/unhelpful feedback：通过 / 失败
历史会话 feedback 回显：通过 / 失败
备注：
```
