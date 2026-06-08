# Step 016：真实解析索引端到端可用性确认

## 1. 本步骤目标

本步骤目标是在 Step 015 文件上传页面真实联调完成后，确认第一版 Demo 是否具备真实“上传文件 -> MinerU API 解析 -> 标准化 -> chunking -> embedding -> Qdrant -> Chat citation”端到端运行条件。

本步骤只做环境与链路可用性确认，不新增无关功能，不伪造解析或索引成功。

本步骤状态：需要人工确认。

## 2. 对应 SDD 条目

- `1.4 MVP 必须做什么`：
  - `6. 使用独立 mineru-service 解析文件`：用户已要求 MinerU 部分改为 API 调用方式；当前实现沿用 MinerU API client。
  - `10. 使用本地 bge-m3 embedding 服务生成向量`：本步骤确认当前 Compose 尚未提供真实 embedding-service。
  - `11. 将向量写入 Qdrant`：Qdrant 服务当前可用，但无真实 embedding-service 时无法完成真实向量写入。
  - `13. 实现 Vector + Full-text 混合召回`：真实召回依赖 chunks 和 embedding/Qdrant 索引。
  - `17. 回答必须带引用编号`、`18. 引用必须包含文件名、定位信息和原文片段`：需要至少一个 active indexed chunk 才能演示真实引用。
  - `23. Docker Compose 一键启动完整系统`：当前 Compose 仍缺真实 embedding-service、reranker-service、backend-worker、mineru-service/API token 配置等完整服务条件。
- `2.1.5 解析链路`：本步骤验证从 MinerU 到 embedding/Qdrant 的链路外部依赖是否满足。
- `3.4 模型服务`：mineru-service、embedding-service、reranker-service、LLM Provider 的服务边界。

## 3. 本步骤完成内容

- 重新查阅 MinerU API 文档：
  - 用户指定参考地址：`https://mineru.net/apiManage/docs`。
  - 当前实现使用的批量上传解析模式仍与文档方向一致：申请上传 URL、上传文件、查询批量解析结果、下载解析产物。
  - MinerU 精准解析需要 API token；当前本地未配置 token。
- 检查本地后端配置：
  - `mineru_api_base_url=https://mineru.net`。
  - `mineru_api_token_configured=False`。
  - `embedding_service_url=http://embedding-service:8200`。
  - `qdrant_url=http://qdrant:6333`。
  - `minio_endpoint=http://minio:9000`。
- 检查 Docker Compose 服务：
  - frontend、backend-api、postgres、redis、qdrant、minio 均处于 Up。
  - Compose 中不存在 `embedding-service` 服务。
- 检查本机模型服务端口：
  - `localhost:8200` 不可达。
  - `localhost:8300` 不可达。
- 检查 Qdrant：
  - Qdrant 服务可访问。
  - 当前 collections 为空。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `docs/progress/step-016-real-e2e-readiness.md` | 新增 | 记录真实解析索引端到端可用性检查、阻塞条件和下一步人工确认项 |
| `docs/progress/README.md` | 修改 | 同步 Step 016 状态为“需要人工确认”，并记录当前阻塞条件 |

## 5. 关键实现说明

- 本步骤没有修改业务代码。
- 本步骤没有新增 Demo 假数据入口。
- 本步骤没有绕过 MinerU API。
- 本步骤没有将 queued/failed 文件伪装为 indexed。
- 当前后端 MinerU client 的真实解析路径仍依赖 `MINERU_API_TOKEN`。
- 当前索引路径仍依赖 embedding-service 的 `POST /embed` 接口。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| MinerU API 文档确认 | 查阅 `https://mineru.net/apiManage/docs` | 通过 | 文档包含 API 方式；当前实现继续采用 MinerU API 调用方式 |
| 后端配置检查 | 使用 `backend/.venv/bin/python` 读取 `get_settings()` | 需要人工确认 | `MINERU_API_TOKEN` 未配置；embedding-service URL 存在但服务未启动 |
| Compose 服务检查 | `docker compose ps` | 部分通过 | frontend、backend-api、postgres、redis、qdrant、minio 正常；无 embedding-service |
| embedding-service 服务检查 | `docker compose ps embedding-service` | 失败 | `no such service: embedding-service` |
| 本机 embedding/reranker 端口检查 | 使用 socket 检查 `localhost:8200` 和 `localhost:8300` | 失败 | 两个端口均不可达 |
| Qdrant 检查 | `curl -sS http://localhost:6333/collections` | 通过 | Qdrant 返回 `status:"ok"`，当前 collections 为空 |
| 真实 MinerU 在线解析 | 配置 token 后触发真实解析 | 未执行 | 缺少 `MINERU_API_TOKEN` |
| 真实 embedding/Qdrant 索引 | 调用真实 embedding-service 并写入 Qdrant | 未执行 | 缺少 embedding-service |
| 真实 Chat citation 端到端 | 上传真实文档后问答返回 citation | 未执行 | 依赖真实解析与索引，当前外部条件不满足 |

## 7. 当前未完成事项

- 未完成真实 MinerU 在线解析。
- 未完成真实 embedding-service 接入。
- 未完成真实 Qdrant 向量写入。
- 未完成真实 indexed chunks 后的 Chat citation 演示。
- 未完成 reranker-service。
- 未完成真实 LLM Provider 与 SSE。

## 8. 风险与注意事项

- 如果在缺少 MinerU token 和 embedding-service 的情况下继续强行做“带引用回答”，只能通过开发 fixture 或假向量服务完成，必须明确标记为 Demo/开发路径，不能作为真实解析索引链路。
- 如果要严格按 SDD 完整 MVP 推进，需要补齐真实 embedding-service、reranker-service、LLM Provider 和 worker/任务系统。
- 当前 Step 015 的页面上传能力是真实的，但上传后的 parse_job 仍停留在 queued，除非人工触发 retry-parse 并配置 MinerU token。
- 当前 `GET /files/{file_id}/status` 可能推进状态机；当外部服务缺失时，会记录真实失败状态。

## 9. 下一步建议

需要人工确认下一步路线：

- 路线 A：提供 `MINERU_API_TOKEN`，并提供或允许新增真实 embedding-service 后，继续执行真实端到端解析索引验证。
- 路线 B：先实现一个明确标记为开发 Demo 的 seed/fixture 路径，用于产生 active chunks 和可检索向量，以演示 Chat citations；该路径不得伪装成 MinerU 真实解析结果。
- 路线 C：先继续完善不依赖模型服务的前端管理页面真实联调，例如 KnowledgeBases、Users、AuditLogs。

建议优先路线 A。若短期无法提供外部服务，则建议路线 B，但需人工确认其 Demo 边界。
