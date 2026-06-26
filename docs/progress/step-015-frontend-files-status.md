# Step 015：前端文件上传与解析状态联调

## 1. 本步骤目标

本步骤目标是在 Step 014 前端 Chat Demo 联调完成后，将文件管理与 Chunk 调试页面从模拟数据切换到真实后端 Files API，让第一版 Demo 具备“通过页面上传资料并观察状态”的基础能力：

- 文件管理页可选择 active 知识库。
- 文件管理页可读取真实文件列表。
- 文件管理页可上传文件到真实后端。
- 文件管理页可处理 Hash 重复提示，并允许 Admin 强制上传。
- 文件管理页可刷新文件/parse_job 状态。
- 文件管理页可触发重新解析。
- 文件管理页可删除文件。
- Chunk 调试页可根据文件读取真实 active chunks。

本步骤不新增后端核心功能，不实现真实 MinerU 在线解析 token 配置、不实现真实 embedding-service 容器、不实现 SSE/LLM/reranker。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `3. Admin 上传多格式文件`：本步骤让前端文件页调用真实上传 API。
  - `4. 文件格式、大小、同名、Hash 校验`：本步骤前端展示后端校验结果，Hash 重复时支持强制上传。
  - `5. 原始文件保存到 MinIO`：本步骤通过真实接口 smoke 验证上传成功后文件进入后端保存链路。
  - `8. 文档标准化为 blocks`、`9. 文档切片生成 chunks`：本步骤不新增生成逻辑，但 Chunk 页面可查看后端已有 active chunks。
  - `18. 引用必须包含文件名、定位信息和原文片段`：本步骤在 Chunk 调试页展示 `source_locator` 与 chunk 原文，服务于后续引用检查。
- `2.1 文档上传与解析流`：
  - 上传入口仅 Admin。
  - 上传限制、扩展名、Hash 和同名校验由后端执行。
  - 上传成功后创建 parse_job。
  - Admin 可触发重新解析。
- `2.1.6 source_locator 规则`：Chunk 调试页展示真实 `source_locator`。
- `3.1 前端`：继续使用 Vue 3、Vite、TypeScript strict、Vue Router、Element Plus。
- `13.8 Phase 8：前端后台管理与问答页面`：本步骤聚焦文件管理与 Chunk 调试页面真实接口联调。

## 3. 本步骤完成内容

- 扩展前端 API client：
  - `listFiles()`
  - `uploadFiles()`
  - `getFile()`
  - `getFileStatus()`
  - `retryParseFile()`
  - `deleteFile()`
  - `listFileChunks()`
  - `ApiClientError`
- 调整 API client 请求处理：
  - JSON 请求继续自动设置 `Content-Type: application/json`。
  - multipart/form-data 上传时不再强制设置 JSON header，由浏览器生成 boundary。
  - 后端 error envelope 的 `code` 和 `details` 被保留，供页面识别 `DUPLICATE_FILE_HASH`。
- 文件管理页接入真实后端：
  - 未登录时跳转登录页。
  - 加载 active 知识库并支持切换。
  - 按知识库读取真实文件列表。
  - 支持 keyword 和 status 查询。
  - 支持选择文件并立即上传。
  - 支持 Hash 重复时展示后端 details，并可强制上传。
  - 支持刷新文件状态和 parse_job 状态。
  - 支持触发 `retry-parse`。
  - 支持软删除文件。
  - 支持跳转 Chunk 调试页查看指定文件 chunks。
- Chunk 调试页接入真实后端：
  - 从 query 参数 `file_id` 读取目标文件。
  - 读取真实文件详情、文件状态和 chunks。
  - 展示文件状态、parse_job 状态、chunk 总数。
  - 展示 chunk id、source_locator、token_count、active 状态和原文内容。
  - 支持按 chunk id/内容和 source_locator 在页面内过滤。
  - 支持复制 chunk id 和 source locator。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 扩展 Files/Chunks API 封装，支持 multipart 上传和保留后端 error details |
| `frontend/src/views/FilesView.vue` | 修改 | 文件管理页从模拟数据切换为真实知识库、文件列表、上传、状态、重试、删除和 Chunk 跳转 |
| `frontend/src/views/ChunksView.vue` | 修改 | Chunk 调试页从模拟数据切换为真实文件详情、状态和 chunks |
| `docs/progress/step-015-frontend-files-status.md` | 新增 | 记录本步骤目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 015 状态、已完成内容、待完成内容和下一步建议 |

## 5. 关键实现说明

- multipart 上传：
  - `uploadFiles()` 使用 `FormData`，字段名为后端要求的 `files`。
  - 同步传入 `force` 字段，用于 Hash 重复后的强制上传。
  - API client 检测到 body 是 `FormData` 时，不设置 `Content-Type`，避免 boundary 丢失。
- Hash 重复处理：
  - 后端返回 `DUPLICATE_FILE_HASH` 时，`ApiClientError` 保留 `details.duplicates`。
  - 文件页读取 `incoming_file_name` 和 `existing_file_name` 生成提示。
  - 用户点击“强制上传”后，以同一批 `selectedFiles` 重新提交 `force=true`。
- 状态展示：
  - 文件列表来自 `GET /knowledge-bases/{knowledge_base_id}/files`。
  - parse_job 状态来自 `GET /files/{file_id}/status`。
  - 页面加载文件列表后会尝试刷新可见文件的状态；单个文件也可以手动刷新。
- 重新解析：
  - 文件页调用 `POST /files/{file_id}/retry-parse`。
  - 当前环境未配置 `MINERU_API_TOKEN` 时，后端会返回明确失败；页面展示真实错误，不伪造成功。
- Chunk 调试：
  - 文件列表通过 query 参数跳转：`/chunks?file_id=<file_id>`。
  - Chunk 页面读取 `GET /files/{file_id}`、`GET /files/{file_id}/status` 和 `GET /files/{file_id}/chunks`。
  - 当前未索引文件通常返回空 chunks，页面展示真实空态。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 前端类型检查 | `npm run typecheck --prefix frontend` | 通过 | `vue-tsc --noEmit` 通过 |
| 前端构建 | `npm run build --prefix frontend` | 通过 | Vite build 成功；存在第三方 `@vueuse/core` pure annotation warning，不影响构建 |
| 后端单元/接口测试 | `.venv/bin/pytest`（在 `backend` 目录执行） | 通过 | 34 passed，1 个 Starlette/httpx deprecation warning |
| 真实上传 smoke | 使用 `backend/.venv/bin/python` 调用登录、创建知识库、上传 txt、查询文件列表、查询状态、查询 chunks | 通过 | 登录 200、创建知识库 201、上传 202、文件列表 200 且 total=1、状态 200 且 file/job 均为 `queued`、chunks 200 且 total=0 |
| 前端入口检查 | `curl -sS -I http://localhost:5173` | 通过 | 返回 HTTP 200 |
| 后端健康检查 | `curl -sS http://localhost:8000/api/v1/health` | 通过 | 返回 `{"status":"ok","service":"backend-api","version":"0.1.0"}` |
| Docker Compose 服务状态 | `docker compose ps frontend backend-api postgres redis qdrant minio` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up 状态 |
| 真实 MinerU 在线解析 | 配置 `MINERU_API_TOKEN` 后触发真实解析 | 未执行 | 当前环境仍未提供 MinerU token；本步骤只联调页面到已有 API |
| 真实 embedding/Qdrant 端到端索引 | 上传文件后真实 embedding-service 写入 Qdrant | 未执行 | Compose 尚未定义真实 embedding-service 容器 |

## 7. 当前未完成事项

- 文件上传后不会自动由前端提交解析；当前后端上传成功后创建 queued parse_job，用户可通过“重新解析”提交 MinerU API。
- 当前环境未配置 `MINERU_API_TOKEN`，真实 MinerU 在线解析仍未执行。
- 当前 Compose 尚未定义真实 embedding-service 容器，真实 bge-m3 embedding 与完整索引仍未执行。
- 当前未实现 Celery worker；状态推进仍依赖已有同步 status/retry API。
- 文件列表当前固定读取前 50 条，尚未实现完整分页 UI。
- Chunk 调试页当前读取前 100 条 chunks，尚未实现完整分页 UI。
- 前端 KnowledgeBases、Users、AuditLogs 等页面仍有模拟数据，尚未全部真实联调。
- Chat 页面仍是非流式 JSON Demo，不是 SSE/LLM。

## 8. 风险与注意事项

- 本步骤没有修改后端业务逻辑；如果后端 Files API 的契约变化，前端 client 需要同步。
- `GET /files/{file_id}/status` 可能推进解析链路；当真实 MinerU、embedding 或 Qdrant 配置不完整时，页面会展示后端真实失败。
- `retry-parse` 在未配置 `MINERU_API_TOKEN` 时会返回 `UPSTREAM_SERVICE_ERROR`，这是当前环境限制，不是页面联调失败。
- Hash 重复强制上传依赖当前选中的 `selectedFiles`；清空选择后不能继续强制上传，需要重新选择文件。
- 文件/Chunk 页面当前仅面向 Admin Demo 使用；普通 User 的上传/状态权限边界由后端控制。

## 9. 下一步建议

建议进入 Step 016：真实文档解析链路的可演示推进策略。

原因：

- 第一版 Demo 现在已经可以登录、创建知识库、上传文件、查看文件状态、查看 chunks 空态、创建会话并问答拒答。
- 但要从“空知识库/queued 文件”推进到“带引用的问答”，还需要让至少一个文件产生 active chunks 并进入 indexed 状态。
- 当前最大外部缺口是 MinerU token、真实 embedding-service 和后续 LLM/reranker。

Step 016 建议范围：

- 在不新增无关功能的前提下，确认 MinerU API token 和 embedding-service 的可用配置。
- 如果外部服务仍不可用，优先实现一个 SDD 允许范围内的 Demo seed/fixture 路径，用于生成可检索 chunks 并验证 Chat citation 展示；该路径必须明确标记为开发 Demo，不伪装成真实解析。
- 如果外部服务可用，则执行真实上传 -> MinerU API -> 标准化 -> chunking -> embedding -> Qdrant -> Chat citation 的端到端验证。
