# Step 044：运行配置生效与 Demo 信息清理

## 1. 本步骤目标

本步骤目标是在用户提供真实 MinerU、embedding、reranker、LLM、Qwen 配置后，让运行中的后端服务重新读取当前 `.env`，并移除当前系统中已经显示或可能继续生成的硬编码/演示 Demo 信息。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：完整 RAG 链路需要真实文档解析、Embedding、检索、Reranker、LLM 生成回答和引用溯源。
- SDD v0.1 1.4：MVP 必须使用真实上传文件、真实解析结果、向量检索、Reranker、SSE 和引用回答。
- 用户当前要求：重启服务并重新检查配置，删除之前系统中显示的硬编码、假的 Demo 信息。

## 3. 本步骤完成内容

- 将用户提供的真实运行配置写入当前 `.env`：
  - MinerU API token。
  - DashScope-compatible embedding API base/key/model。
  - DashScope-compatible reranker API base/key/model。
  - DashScope-compatible LLM API base/key/model。
  - Qwen 多模态 embedding provider 配置。
- 将 `.env` 中 `DEMO_FIXTURE_ENABLED` 从 `true` 改为 `false`。
- 重启 `backend-api` 容器，使运行服务重新读取 `.env`。
- 检查容器内配置，确认：
  - MinerU token 已配置。
  - embedding API 已配置，模型为 `qwen3-vl-embedding`。
  - reranker API 已配置，模型为 `qwen3-vl-rerank`。
  - LLM API 已配置，模型为 `qwen3.7-plus`。
  - Qwen 多模态 embedding 配置已读取。
  - Demo fixture 开关已关闭。
- 清理当前数据库和外部存储中的 Demo fixture 数据：
  - 删除 `Demo Fixture 知识库`。
  - 删除 `demo-rag-fixture.txt`。
  - 删除 `demo_user` 和 profile。
  - 删除 Demo 相关 conversations、messages、citations、traces、feedback。
  - 删除 Demo parse_jobs 和 chunks。
  - 将 Demo Qdrant points 标记为 inactive。
  - 删除 Demo MinIO raw file object。
- 清理前端 Chat 页面可见硬编码 Demo 文案：
  - 空知识库状态下创建的默认知识库名称从 `Demo 知识库 ...` 改为 `知识库 ...`。
  - 默认描述从 `用于第一版 Chat Demo 联调的知识库空间。` 改为 `通过 Chat 页面创建的知识库空间。`
  - 函数名从 `createDemoKnowledgeBase` 改为 `createKnowledgeBaseFromChat`。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `.env` | 修改 | 写入真实外部 API 配置，关闭 `DEMO_FIXTURE_ENABLED` |
| `frontend/src/views/ChatView.vue` | 修改 | 移除用户可见的硬编码 Demo 知识库名称/说明，改为普通知识库创建入口 |
| `docs/progress/step-044-runtime-config-demo-cleanup.md` | 新增 | 记录本步骤配置、清理、验证和后续建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 044 状态、已完成内容、注意事项和下一步建议 |

## 5. 关键实现说明

- `.env.example` 未写入用户真实 token/key，避免将真实密钥作为示例配置扩散。
- 后端容器必须重启后才会读取新的 `.env`；本步骤已执行 `docker compose up -d --force-recreate backend-api`。
- Demo fixture 清理按固定标识执行：
  - 知识库名：`Demo Fixture 知识库`
  - 文件名：`demo-rag-fixture.txt`
  - 用户名：`demo_user`
  - 生成型知识库名前缀：`Demo 知识库`
- 清理脚本没有删除普通用户真实上传的文件或知识库。
- 当前只清理运行数据和前端可见 Demo 文案；历史文档中仍保留 Step 034-036 对 Demo fixture 的开发记录，作为项目历史和验收边界说明。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端服务重启 | `docker compose up -d --force-recreate backend-api` | 通过 | backend-api 重新创建并启动 |
| 容器配置检查 | 容器内读取 `get_settings()`，只输出配置是否存在和模型名 | 通过 | MinerU、embedding、reranker、LLM、Qwen 均已配置；Demo fixture 为 `False` |
| Demo 数据清理 | 容器内 SQLAlchemy 清理脚本 | 通过 | 删除 1 个 Demo KB、1 个 Demo file、3 个 parse_jobs、9 个 chunks、6 个 conversations、14 个 messages、21 个 citations、7 个 traces、4 个 feedback、1 个 demo_user/profile；9 个 Qdrant points 已失效，1 个 MinIO object 已删除 |
| Demo 残留检查 | 查询 `Demo Fixture 知识库`、`Demo 知识库%`、`demo-rag-fixture.txt`、`demo_user` 数量 | 通过 | 均为 0 |
| 前端 Demo 文案扫描 | `rg -n "Demo 知识库|Chat Demo 联调|createDemoKnowledgeBase" frontend/src` | 通过 | 无匹配 |
| 前端 lint | `npm run lint` | 通过 | ESLint 通过 |
| 前端 typecheck/build | `npm run typecheck && npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` Rolldown pure annotation warning，不影响产物 |
| 后端健康检查 | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回 `status=ok` |

## 7. 当前未完成事项

- 尚未用真实文件执行 MinerU 在线解析。
- 尚未验证 `qwen3-vl-embedding` 对当前 embedding client 的 OpenAI-compatible `/embeddings` 契约是否完全兼容。
- 尚未验证 `qwen3-vl-rerank` 对当前 reranker client 的 `/rerank` 契约是否完全兼容。
- 尚未验证 `qwen3.7-plus` 的 Chat Completions/SSE 输出与当前 LLM client 完全兼容。
- 尚未将 Step 043 的多模态图片检索骨架接入真实索引和 Chat。

## 8. 风险与注意事项

- `.env` 包含真实 token/key，不应提交到公共仓库或复制到 `.env.example`。
- 当前 Demo fixture 已关闭，后端不再使用 local demo embedding/reranker；后续有 indexed chunks 时会走真实 API 配置。
- 如果 DashScope reranker/embedding 的实际 endpoint 或 payload 与当前 client 假设不同，真实解析/索引/问答时可能返回上游服务错误，需要在对应 provider/client 内适配。
- 前端 dev server 已挂载源码，`ChatView.vue` 修改会由 Vite dev server 热更新；生产构建也已验证通过。

## 9. 下一步建议

下一步建议补跑真实链路验证：

1. 使用 Admin 登录。
2. 创建真实知识库。
3. 上传一个小型真实 `.pdf` 或 `.docx`。
4. 点击重新解析。
5. 观察状态是否从 `parsing -> normalizing -> chunking -> embedding -> indexing -> indexed` 推进。
6. 若失败，记录失败阶段、错误码和 logs，再针对 MinerU、embedding、reranker 或 LLM client 做小步适配。

若真实解析能推进到 indexed，再进入真实带引用问答验收；若要继续多模态图文召回，则进入“真实图片资产与 ImageBlock 生成”步骤。
