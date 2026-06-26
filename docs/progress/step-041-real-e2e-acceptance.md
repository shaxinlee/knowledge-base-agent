# Step 041：真实端到端验收

## 1. 本步骤目标

本步骤目标是验证真实文件能从上传走到带引用回答的完整链路：

Admin 登录 -> 创建知识库 -> 上传真实文件 -> MinerU API 解析 -> document_blocks -> chunks -> embedding API -> Qdrant -> User 提问 -> hybrid retrieval -> reranker API -> LLM API SSE 回答 -> citation/feedback/trace 回显。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：完整 RAG 链路，从文档解析到带引用回答、会话与反馈保存。
- SDD v0.1 1.4：Admin 登录、知识库、文件上传、MinerU、embedding、Qdrant、全文检索、reranker、SSE、引用、拒答、trace、feedback、Docker Compose。
- SDD v0.1 2.1.5：上传解析索引状态流。
- SDD v0.1 2.1.6：每个 chunk 必须有 source_locator，用于引用溯源。
- 用户确认方向：MinerU、embedding、reranker、LLM 均按 API 调用方式验收。

## 3. 本步骤完成内容

- 检查当前环境中的真实外部 API 配置。
- 确认 Docker Compose 运行服务状态。
- 确认前端代理 health 正常。
- 执行运行态 smoke：
  - Admin 登录成功。
  - 创建知识库成功。
  - 上传 `.txt` 文件成功。
  - 触发 retry-parse 时，因 `MINERU_API_TOKEN` 未配置返回明确 `UPSTREAM_SERVICE_ERROR`。
- 因关键外部配置缺失，本步骤不能执行真实 MinerU 在线解析、真实 embedding、真实 reranker、真实 LLM 或真实带引用回答验收。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `docs/progress/step-041-real-e2e-acceptance.md` | 新增 | 记录真实端到端验收的环境检查、阻塞条件和下一步人工确认项 |
| `docs/progress/README.md` | 修改 | 同步 Step 041 状态为“需要人工确认”，记录缺失配置 |

## 5. 关键实现说明

本步骤没有新增业务代码。

Step 038-040 已经准备好真实链路所需入口：

- Step 038：MinerU API 提交、轮询、parsed-results 保存、失败隔离。
- Step 039：MinerU zip 到 document_blocks/chunks 的标准化和 chunking。
- Step 040：API 化 embedding/reranker/LLM client、Chat LLM 生成、evidence gate。

但当前 `.env` 缺少真实外部服务配置，因此无法从真实文件解析推进到真实带引用问答。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| MinerU token 配置检查 | 读取 `get_settings().mineru_api_token` | 失败/需要人工确认 | `MINERU_API_TOKEN=False` |
| Embedding API 配置检查 | 读取 `EMBEDDING_API_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | 失败/需要人工确认 | base/key 均未配置，model 已配置为 `bge-m3` |
| Reranker API 配置检查 | 读取 `RERANKER_API_BASE_URL` / `RERANKER_API_KEY` / `RERANKER_MODEL` | 失败/需要人工确认 | base/key 均未配置，model 已配置为 `bge-reranker` |
| LLM API 配置检查 | 读取 `LLM_API_BASE_URL` 或 `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` | 失败/需要人工确认 | base/key/model 均未配置 |
| Docker Compose 服务状态 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均 Up |
| 服务健康检查 | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回 `status=ok` |
| 运行态上传 smoke | Admin 登录 -> 创建 KB -> 上传 `.txt` | 通过 | 登录 200，创建 KB 201，上传 202 |
| retry-parse 真实错误 smoke | `POST /files/{file_id}/retry-parse` | 通过/按预期失败 | 返回 503，message 为 `MinerU API token is not configured.` |
| 真实 MinerU 在线解析 | 上传真实 `.pdf/.docx/.txt` 后触发 MinerU API | 未执行 | 缺少 `MINERU_API_TOKEN` |
| 真实 document_blocks/chunks 在线样本 | 基于真实 MinerU zip 标准化 | 未执行 | 依赖真实 MinerU 在线解析 |
| 真实 embedding API 索引 | 调用真实 embedding API 并写入 Qdrant | 未执行 | 缺少 embedding API base/key |
| 真实 reranker API 重排 | 调用真实 reranker API | 未执行 | 缺少 reranker API base/key |
| 真实 LLM API SSE 回答 | 调用真实 LLM API 并返回带引用回答 | 未执行 | 缺少 LLM API base/key/model |
| feedback/trace 真实端到端 | 对真实回答提交 feedback 并查看 trace | 未执行 | 依赖真实带引用回答 |

## 7. 当前未完成事项

- 未完成真实 MinerU 在线解析。
- 未完成真实 document_blocks/chunks 在线样本验证。
- 未完成真实 embedding API 索引和 Qdrant 写入验收。
- 未完成真实 reranker API 重排验收。
- 未完成真实 LLM API SSE 带引用回答验收。
- 未完成真实 feedback/trace 端到端验收。

## 8. 风险与注意事项

- 不能在缺少外部 API 配置的情况下宣称真实端到端验收完成。
- 当前本地 Demo 仍可使用 demo/template client 展示受限流程，但该结果不等同于真实 RAG 验收。
- 用户确认的 API 化 embedding/reranker/LLM 方向偏离 SDD 原文的本地模型服务要求，后续验收报告需继续注明。
- 配置真实 API 后，应优先补跑 Step 038-041 的真实样本文档验收，并把结果追加到对应进度文件。

## 9. 下一步建议

本步骤状态建议保持为“需要人工确认”。

请提供或配置以下环境变量后继续真实验收：

- `MINERU_API_TOKEN`
- `EMBEDDING_API_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `RERANKER_API_BASE_URL`
- `RERANKER_API_KEY`
- `RERANKER_MODEL`
- `LLM_API_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

配置完成后，应重新执行：真实 `.pdf/.docx/.txt` 上传解析、parsed-results 保存、blocks/chunks 生成、embedding API 索引、Qdrant 写入、User 提问、reranker API、LLM SSE、citation、feedback 和 trace 回显。
