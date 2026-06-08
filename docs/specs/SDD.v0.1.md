# 知识库 Agent 助手 v0.1 SDD

本文档是知识库 Agent 助手 v0.1 的 SDD（Specification-Driven Development）主规范。内容已去除口语讨论，保留技术契约、实现边界与验收标准。

| 字段 | 内容 |
| --- | --- |
| 版本 | v0.1 |
| 定位 | 开发前规格冻结文档 |
| 目标读者 | 前端开发 Agent、后端开发 Agent、数据库开发 Agent、RAG / 检索链路开发 Agent |
| 系统类型 | 小团队内部使用的独立 Web 知识库 Agent |

⸻

1. 产品定位与边界

1.1 一句话定义

知识库 Agent 助手是一个面向小团队内部使用的独立 Web 应用，用于将项目资料上传、解析、切片、索引，并基于混合检索与大模型生成带明确引用溯源的知识问答结果。

1.2 目标用户

* 小团队内部成员
* 特定项目的开发人员、研究人员、产品人员
* 第一版不面向外部客户开放

1.3 核心目标

系统应支持用户上传多格式项目资料，并在用户提问时完成：

文档解析
→ 文本标准化
→ Chunking
→ Embedding
→ 向量检索
→ PostgreSQL 全文检索
→ Reranker 重排
→ LLM 生成回答
→ 引用溯源
→ 会话与反馈保存

1.4 MVP 必须做什么

v0.1 必须完成以下能力：

1. Admin 登录与用户管理。
2. Admin 创建、编辑、删除知识库空间。
3. Admin 上传多格式文件。
4. 文件格式、大小、同名、Hash 校验。
5. 原始文件保存到 MinIO。
6. 使用独立 mineru-service 解析文件。
7. 解析结果持久化。
8. 文档标准化为 blocks。
9. 文档切片生成 chunks。
10. 使用本地 bge-m3 embedding 服务生成向量。
11. 将向量写入 Qdrant。
12. 使用 PostgreSQL tsvector 做全文检索。
13. 实现 Vector + Full-text 混合召回。
14. 使用本地 BGE Reranker 重排。
15. User 基于单个知识库空间提问。
16. SSE 流式返回回答。
17. 回答必须带引用编号。
18. 引用必须包含文件名、定位信息和原文片段。
19. 证据不足时必须拒答。
20. 保存会话、消息、引用、trace。
21. 支持 helpful / unhelpful 反馈。
22. 记录 Admin 高危操作审计日志。
23. Docker Compose 一键启动完整系统。

1.5 MVP 明确不做什么

v0.1 严格禁止自动扩展以下能力：

1. 不做跨知识库查询。
2. 不做 GraphRAG 实际召回。
3. 不做实体抽取、关系抽取、社区摘要和图谱可视化。
4. 不做文件版本管理。
5. 不做文档级权限。
6. 不做复杂多租户隔离。
7. 不做 OpenAI-compatible 对外网关。
8. 不做 Text2SQL。
9. 不做复杂 Excel / CSV 聚合计算。
10. 不做跨表 join、公式执行、统计分析。
11. 不做手动编辑 chunk。
12. 不做复杂标签体系。
13. 不做主动修改、删除或写回用户文件。
14. 不做移动端 App。
15. 不做公网开放注册。
16. 不做 Editor 角色。
17. 不做用户组和团队空间。
18. 不做支付、计费和套餐系统。

1.6 GraphRAG 决策

GraphRAG 不进入首个内测版本。

v0.1 可以预留以下表结构，但不实现实际功能：

graph_entities
graph_relationships
entity_chunk_links

v0.1 不要求完成：

实体抽取
关系抽取
子图召回
社区摘要
GraphRAG Query Router
图谱可视化

⸻

2. 核心业务流

2.1 文档上传与解析流

2.1.1 上传入口

只有 admin 可以上传文件。

上传限制：

单文件最大：50MB
单次最多上传：50 个
第一版目标文档规模：约 1,000 份
第一版总容量：10GB 内

支持格式：

.pdf
.md
.docx
.txt
.xlsx
.xls
.csv
.pptx
.png
.jpg
.jpeg
.webp

2.1.2 上传校验规则

后端必须执行以下校验：

1. 校验用户角色是否为 admin。
2. 校验 knowledge_base_id 是否存在且状态为 active。
3. 校验文件大小不超过 50MB。
4. 校验文件扩展名在白名单内。
5. 计算 file_hash，推荐 SHA-256。
6. 同一知识库内，同名文件直接拒绝。
7. 同一知识库内，file_hash 相同但文件名不同，返回 warning，由 Admin 决定是否强制上传。

2.1.3 文件保存

通过后端接收 multipart/form-data，由后端写入 MinIO。

MinIO 建议 bucket：

raw-files
parsed-results
normalized-docs
assets
exports

2.1.4 解析任务状态流转

上传成功后创建 parse_job，由 Celery 异步执行。

parse_jobs.status 状态机：

queued
parsing
normalizing
chunking
embedding
indexing
indexed
partially_indexed
failed
cancelled

说明：

* v0.1 保留 cancelled 状态，但前端不提供取消按钮。
* partially_indexed 表示部分解析或索引成功。
* 失败任务必须保留 error log。
* Admin 可触发重新解析。
* 每次重新解析创建新的 parse_job。
* 只有最新成功的 parse_job 产物允许进入 active 检索集合。
* 失败 job 不能污染线上检索。

2.1.5 解析链路

file uploaded
→ create parse_job
→ call mineru-service
→ save MinerU markdown/json/assets
→ normalize document blocks
→ chunking
→ save chunks metadata
→ call embedding-service
→ write vectors to Qdrant
→ build PostgreSQL tsvector
→ mark parse_job as indexed / partially_indexed / failed

2.1.6 source_locator 规则

每个 chunk 必须生成 source_locator，用于引用溯源。

示例：

pdf:p12-p13
pptx:slide-8
xlsx:Sheet1!A20:F35
csv:rows-20-35
md:Chapter 2 > Method
image:ocr-region-3
txt:chunk-12

⸻

2.2 检索流

用户每次提问必须绑定一个固定的 knowledge_base_id。

MVP 不允许跨知识库查询。

检索流程：

user question
→ validate conversation belongs to knowledge_base
→ query embedding
→ Qdrant vector search with payload filter
→ PostgreSQL tsvector full-text search
→ merge results
→ deduplicate by chunk_id
→ reranker-service rerank
→ select final chunks
→ construct LLM context

默认检索参数：

vector_top_k = 30
full_text_top_k = 30
reranker_top_k = 8-12
final_context_chunks = 6-8

Qdrant 检索必须携带过滤条件：

{
  "must": [
    {
      "key": "knowledge_base_id",
      "match": {
        "value": "<knowledge_base_id>"
      }
    },
    {
      "key": "is_active",
      "match": {
        "value": true
      }
    }
  ]
}

⸻

2.3 问答生成流

问答流程：

user sends message
→ create user message
→ retrieve chunks
→ rerank chunks
→ build grounded prompt
→ call LLM provider
→ SSE streaming answer
→ create assistant message
→ create citations
→ create message_trace

2.3.1 回答约束

LLM 必须遵守：

1. 只能基于当前知识库召回内容回答。
2. 不允许使用通用知识自由补充。
3. 每个关键事实必须带引用编号。
4. 引用必须来自最终上下文 chunk。
5. 证据不足时必须拒答。
6. 用户画像只能影响回答风格，不能影响事实、引用、证据阈值和安全策略。

2.3.2 证据不足模板

当检索证据不足时，必须使用类似结构：

当前知识库中没有找到足够依据回答该问题。
我检索到的最接近内容包括：
[1] 《xxx.pdf》p.12：……
[2] 《yyy.md》/背景/chunk-04：……
这些内容不足以支持明确结论。建议补充包含该问题细节的文档后重新提问。

2.3.3 引用格式

回答正文示例：

根据资料，系统采用了混合检索策略，包括向量召回和全文召回 [1]。

参考来源示例：

[1] 《architecture.md》/RAG Pipeline/chunk-08：原文片段……
[2] 《demo.pdf》p.12：原文片段……
[3] 《slides.pptx》slide 8：原文片段……
[4] 《data.xlsx》Sheet1!A20:F35：表格片段……

⸻

3. 系统架构与技术栈

3.1 前端

Vue 3
Vite
TypeScript strict
Pinia
Vue Router
Element Plus
ESLint
Prettier

前端模块：

auth
users
knowledge-bases
files
chat
feedback
audit-logs
shared-components

3.2 后端

Python 3.11+
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
Celery
Redis
JWT access token + refresh token
bcrypt

后端模块：

auth
users
knowledge_bases
files
parse_jobs
documents
chunks
retrieval
reranker
chat
citations
feedback
audit_logs
cleanup

3.3 数据库与存储

PostgreSQL：关系数据、全文索引、metadata、trace
Qdrant：向量索引
MinIO：原始文件、解析结果、assets
Redis：Celery broker / result backend

3.4 模型服务

mineru-service：独立文档解析服务
embedding-service：bge-m3 本地 embedding 服务
reranker-service：BGE reranker 本地重排服务
LLM Provider：Qwen / DeepSeek API 优先，后续支持私有化

3.5 部署方式

Monorepo
Docker Compose
NVIDIA GPU 环境

服务边界：

frontend
backend-api
backend-worker
postgres
redis
qdrant
minio
mineru-service
embedding-service
reranker-service
nginx

⸻

4. 数据库设计规范

4.1 全局规范

* 主键统一使用 UUID。
* 所有业务表必须包含 created_at。
* 可修改表必须包含 updated_at。
* 需要软删除的表必须包含 deleted_at。
* 软删除记录不得参与默认查询。
* 后端查询必须默认过滤 deleted_at IS NULL。
* 文件、知识库、会话等对象不做物理即时删除。
* 物理清理由 Celery 异步任务完成。
* 枚举字段使用字符串枚举。
* 大型 trace 可使用 JSONB 存储。

⸻

4.2 users

id UUID PK
email VARCHAR UNIQUE NOT NULL
username VARCHAR UNIQUE NOT NULL
password_hash TEXT NOT NULL
role VARCHAR NOT NULL
status VARCHAR NOT NULL
failed_login_count INT DEFAULT 0
locked_until TIMESTAMP NULL
last_login_at TIMESTAMP NULL
created_at TIMESTAMP
updated_at TIMESTAMP
deleted_at TIMESTAMP NULL

约束：

role in ('admin', 'user')
status in ('active', 'disabled')

规则：

* 第一版内置默认 Admin。
* 后续用户只能由 Admin 创建。
* 不开放公开注册。
* disabled 用户不能登录。
* 禁用用户时保留历史会话和审计日志。

⸻

4.3 user_profiles

id UUID PK
user_id UUID FK users.id UNIQUE
display_name VARCHAR
occupation VARCHAR
answer_style VARCHAR
preferences JSONB
created_at TIMESTAMP
updated_at TIMESTAMP

用途：

* 存储用户姓名、职业角色、回答风格倾向。
* 用户画像仅用于回答风格，不得影响事实和引用。

⸻

4.4 knowledge_bases

id UUID PK
name VARCHAR NOT NULL
description TEXT
status VARCHAR NOT NULL
settings JSONB
created_by UUID FK users.id
created_at TIMESTAMP
updated_at TIMESTAMP
deleted_at TIMESTAMP NULL

状态：

active
deleting
deleted

settings 示例：

{
  "default_top_k": 8,
  "strict_citation": true,
  "answer_language": "zh"
}

规则：

* 只有 Admin 可创建、编辑、删除知识库。
* User 可查看 active 知识库并提问。
* 删除知识库采用软删除。
* 删除后创建 cleanup job 异步清理关联资源。

⸻

4.5 files

id UUID PK
knowledge_base_id UUID FK knowledge_bases.id
file_name VARCHAR NOT NULL
file_ext VARCHAR NOT NULL
mime_type VARCHAR
file_size BIGINT
file_hash VARCHAR NOT NULL
storage_bucket VARCHAR NOT NULL
storage_key TEXT NOT NULL
status VARCHAR NOT NULL
latest_parse_job_id UUID NULL
created_by UUID FK users.id
created_at TIMESTAMP
updated_at TIMESTAMP
deleted_at TIMESTAMP NULL

状态：

uploaded
queued
processing
indexed
partially_indexed
failed
deleting
deleted

唯一约束：

CREATE UNIQUE INDEX uq_files_kb_filename_active
ON files (knowledge_base_id, file_name)
WHERE deleted_at IS NULL;

Hash 去重逻辑：

同一 knowledge_base 内 file_name 相同：拒绝上传。
同一 knowledge_base 内 file_hash 相同但 file_name 不同：返回 warning，由 Admin 决定是否继续。

⸻

4.6 parse_jobs

id UUID PK
file_id UUID FK files.id
knowledge_base_id UUID FK knowledge_bases.id
status VARCHAR NOT NULL
progress INT DEFAULT 0
error_code VARCHAR NULL
error_message TEXT NULL
logs JSONB
started_at TIMESTAMP NULL
finished_at TIMESTAMP NULL
created_by UUID FK users.id
created_at TIMESTAMP
updated_at TIMESTAMP

状态：

queued
parsing
normalizing
chunking
embedding
indexing
indexed
partially_indexed
failed
cancelled

规则：

* 同一个 file 可以有多个 parse_job。
* 最新成功 parse_job 才能成为 active index 来源。
* 失败 parse_job 保留日志。
* retry 会创建新 parse_job。

⸻

4.7 document_blocks

id UUID PK
knowledge_base_id UUID FK knowledge_bases.id
file_id UUID FK files.id
parse_job_id UUID FK parse_jobs.id
block_index INT
block_type VARCHAR
content TEXT
page_number INT NULL
slide_number INT NULL
sheet_name VARCHAR NULL
row_start INT NULL
row_end INT NULL
bbox JSONB NULL
metadata JSONB
created_at TIMESTAMP

用途：

* 保存 MinerU / 原生 parser 标准化后的 block。
* 支持 chunk 回溯。
* 支持引用定位。
* 支持后续重新 chunk。

⸻

4.8 chunks_metadata

表名建议使用 chunks 或 chunks_metadata。若向量只存 Qdrant，PostgreSQL 中该表保存 chunk 元数据和原文内容。

id UUID PK
knowledge_base_id UUID FK knowledge_bases.id
file_id UUID FK files.id
parse_job_id UUID FK parse_jobs.id
chunk_index INT
content TEXT NOT NULL
content_hash VARCHAR NOT NULL
token_count INT
page_start INT NULL
page_end INT NULL
slide_number INT NULL
sheet_name VARCHAR NULL
row_start INT NULL
row_end INT NULL
heading_path JSONB NULL
source_type VARCHAR NOT NULL
source_locator TEXT NOT NULL
metadata JSONB
is_active BOOLEAN DEFAULT true
tsv tsvector
created_at TIMESTAMP

source_type：

pdf
docx
markdown
txt
pptx
xlsx
csv
image

索引建议：

CREATE INDEX idx_chunks_kb_active
ON chunks_metadata (knowledge_base_id, is_active);
CREATE INDEX idx_chunks_file
ON chunks_metadata (file_id);
CREATE INDEX idx_chunks_tsv
ON chunks_metadata USING GIN (tsv);

⸻

4.9 conversations

id UUID PK
user_id UUID FK users.id
knowledge_base_id UUID FK knowledge_bases.id
title VARCHAR
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
deleted_at TIMESTAMP NULL

状态：

active
deleted

规则：

* 每个会话固定绑定一个 knowledge_base_id。
* MVP 不支持跨知识库查询。
* 用户只能查看自己的会话。
* Admin 不默认读取用户私人会话，除非后续引入管理审计功能。

⸻

4.10 messages

id UUID PK
conversation_id UUID FK conversations.id
user_id UUID FK users.id
role VARCHAR NOT NULL
content TEXT
status VARCHAR
model_name VARCHAR NULL
prompt_version VARCHAR NULL
token_input INT NULL
token_output INT NULL
latency_ms INT NULL
created_at TIMESTAMP

role：

user
assistant
system

⸻

4.11 message_citations

id UUID PK
message_id UUID FK messages.id
chunk_id UUID FK chunks_metadata.id
file_id UUID FK files.id
citation_index INT NOT NULL
source_label TEXT
excerpt TEXT
source_locator TEXT
created_at TIMESTAMP

规则：

* 每条 assistant message 可有多个 citation。
* citation_index 对应正文中的 [1]、[2]。
* citation 必须关联真实 chunk。

⸻

4.12 message_traces

id UUID PK
message_id UUID FK messages.id UNIQUE
query_text TEXT
retrieved_chunk_ids JSONB
reranked_chunk_ids JSONB
final_context_chunk_ids JSONB
final_cited_chunk_ids JSONB
reranker_scores JSONB
embedding_model VARCHAR
reranker_model VARCHAR
chat_model VARCHAR
prompt_version VARCHAR
latency_breakdown JSONB
token_usage JSONB
raw_prompt_snapshot TEXT NULL
created_at TIMESTAMP

规则：

* raw_prompt_snapshot 是否保存由环境变量控制。
* 默认可关闭，避免数据库膨胀。
* trace 是 RAG 调试、反馈归因和评估闭环的核心数据。

⸻

4.13 feedback

id UUID PK
message_id UUID FK messages.id
user_id UUID FK users.id
knowledge_base_id UUID FK knowledge_bases.id
rating VARCHAR NOT NULL
comment TEXT NULL
query_text TEXT
retrieved_chunk_ids JSONB
final_cited_chunk_ids JSONB
model_name VARCHAR
prompt_version VARCHAR
embedding_model VARCHAR
reranker_model VARCHAR
latency_ms INT
token_input INT
token_output INT
created_at TIMESTAMP

rating：

helpful
unhelpful

⸻

4.14 audit_logs

id UUID PK
actor_user_id UUID FK users.id
action VARCHAR NOT NULL
resource_type VARCHAR NOT NULL
resource_id UUID NULL
details JSONB
ip_address VARCHAR NULL
user_agent TEXT NULL
created_at TIMESTAMP

记录范围：

create_user
disable_user
enable_user
reset_password
create_knowledge_base
update_knowledge_base
delete_knowledge_base
upload_file
delete_file
retry_parse_file

⸻

4.15 cleanup_jobs

id UUID PK
resource_type VARCHAR
resource_id UUID
status VARCHAR NOT NULL
error_message TEXT NULL
created_at TIMESTAMP
started_at TIMESTAMP NULL
finished_at TIMESTAMP NULL

状态：

cleanup_queued
cleanup_running
cleanup_done
cleanup_failed

⸻

5. Qdrant 设计规范

5.1 Collection 策略

MVP 使用一个全局 collection：

chunks

通过 payload 过滤知识库：

knowledge_base_id
is_active

不建议 v0.1 为每个知识库创建独立 collection。

5.2 Payload 字段

{
  "chunk_id": "chunk_xxx",
  "knowledge_base_id": "kb_xxx",
  "file_id": "file_xxx",
  "parse_job_id": "job_xxx",
  "file_name": "xxx.pdf",
  "source_type": "pdf",
  "page_start": 12,
  "page_end": 13,
  "heading_path": ["Chapter 1", "Method"],
  "is_active": true,
  "token_count": 768,
  "content_hash": "sha256..."
}

5.3 删除策略

文件删除时：

1. PostgreSQL files.deleted_at 软删除。
2. PostgreSQL chunks is_active=false。
3. Qdrant payload is_active=false 或异步删除 points。
4. 创建 cleanup job。
5. 异步清理 MinIO 和 Qdrant 残留对象。

⸻

6. API 契约规范

6.1 API 前缀

所有业务 API 使用：

/api/v1

6.2 认证方式

JWT access token + refresh token
Authorization: Bearer <access_token>

6.3 统一错误返回格式

所有错误必须使用统一 JSON：

{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds 50MB limit.",
    "details": {},
    "request_id": "req_xxx"
  }
}

字段说明：

code：稳定的业务错误码，供前端映射提示。
message：可读错误信息。
details：结构化上下文。
request_id：后端日志追踪 ID。

6.4 Auth API

POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me

登录响应：

{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 1800
}

⸻

6.5 Users API

GET    /api/v1/users
POST   /api/v1/users
PATCH  /api/v1/users/{user_id}
POST   /api/v1/users/{user_id}/disable
POST   /api/v1/users/{user_id}/enable
POST   /api/v1/users/{user_id}/reset-password
GET    /api/v1/users/me/profile
PATCH  /api/v1/users/me/profile

权限：

GET /users：admin only
POST /users：admin only
disable / enable / reset-password：admin only
me/profile：当前登录用户

⸻

6.6 Knowledge Bases API

GET    /api/v1/knowledge-bases
POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{kb_id}
PATCH  /api/v1/knowledge-bases/{kb_id}
DELETE /api/v1/knowledge-bases/{kb_id}

权限：

GET：admin 和 user
POST/PATCH/DELETE：admin only

删除规则：

软删除
创建 cleanup_job
前端二次确认

⸻

6.7 Files API

GET    /api/v1/knowledge-bases/{kb_id}/files
POST   /api/v1/knowledge-bases/{kb_id}/files/upload
GET    /api/v1/files/{file_id}
GET    /api/v1/files/{file_id}/status
DELETE /api/v1/files/{file_id}
POST   /api/v1/files/{file_id}/retry-parse
GET    /api/v1/files/{file_id}/chunks

权限：

GET file list：admin；user 可选只读
upload/delete/retry-parse：admin only
status：admin only
chunks：admin only，MVP 可用于调试

上传：

multipart/form-data

上传限制：

MAX_FILE_SIZE_MB=50
MAX_BATCH_UPLOAD_COUNT=50

⸻

6.8 Conversations API

GET    /api/v1/conversations?knowledge_base_id=<kb_id>
POST   /api/v1/conversations
GET    /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}

创建会话请求：

{
  "knowledge_base_id": "kb_xxx",
  "title": "optional title"
}

规则：

会话必须绑定单个 knowledge_base_id。
用户只能访问自己的会话。
MVP 不支持多知识库会话。

⸻

6.9 Messages / Chat API

主问答接口：

POST /api/v1/conversations/{conversation_id}/messages

请求：

{
  "content": "这个项目的核心方法是什么？",
  "stream": true
}

响应：

SSE stream

最终完成事件应包含：

{
  "message_id": "msg_xxx",
  "answer": "根据资料……[1]",
  "citations": [
    {
      "index": 1,
      "file_name": "xxx.pdf",
      "source_locator": "p.12",
      "excerpt": "原文片段……",
      "chunk_id": "chunk_xxx"
    }
  ]
}

⸻

6.10 Feedback API

POST /api/v1/messages/{message_id}/feedback

请求：

{
  "rating": "helpful",
  "comment": "引用准确"
}

⸻

6.11 Audit Logs API

GET /api/v1/audit-logs

权限：

admin only

⸻

7. 开发里程碑 Task Breakdown

Phase 0：工程骨架

目标：搭建可运行的 Monorepo 和基础服务。

任务：

初始化 monorepo
创建 FastAPI 项目骨架
创建 Vue 3 + Vite + Element Plus 项目骨架
配置 PostgreSQL / Redis / Qdrant / MinIO
配置 docker-compose.yml
配置 .env.example
配置 pre-commit
配置 ruff / black / mypy / pytest
配置 ESLint / Prettier
创建 /api/v1/health

验收标准：

docker compose up 后所有基础服务可启动。
前端页面可访问。
后端 /api/v1/health 返回正常。
Alembic migration 可执行。

⸻

Phase 1：认证、用户与权限

目标：完成登录、JWT、RBAC 和默认 Admin。

任务：

users 表
user_profiles 表
默认 Admin 初始化
bcrypt 密码哈希
JWT access token
JWT refresh token
登录失败计数
失败 5 次锁定 15 分钟
Admin 创建用户
Admin 禁用/启用用户
Admin 重置密码
RBAC dependency
auth/me

验收标准：

Admin 可登录。
Admin 可创建 user。
disabled 用户无法登录。
普通 user 无法访问 Admin API。
连续登录失败会锁定账号。

⸻

Phase 2：知识库 CRUD 与文件管理

目标：完成知识库、文件上传、MinIO 存储、Hash 去重。

任务：

knowledge_bases 表
files 表
KnowledgeBase CRUD
文件上传 API
文件大小校验
文件类型校验
单次上传数量限制
file_hash 计算
同名文件拒绝
hash 重复 warning
MinIO raw-files 写入
文件列表
文件状态查询
文件软删除
audit_logs 写入

验收标准：

Admin 可创建知识库。
Admin 可上传文件。
User 不能上传文件。
超 50MB 文件被拒绝。
同一知识库内同名文件被拒绝。
hash 重复但不同名返回 warning。
MinIO 中存在原始文件。

⸻

Phase 3：文档解析与 Chunking

目标：完成解析任务状态机、MinerU 服务调用、blocks 和 chunks 生成。

任务：

parse_jobs 表
document_blocks 表
chunks_metadata 表
Celery worker
parse_job 状态机
mineru-service HTTP/gRPC 调用
解析结果写入 MinIO parsed-results
标准化 document_blocks
chunking
source_locator 生成
token_count 计算
content_hash 计算
retry-parse

验收标准：

上传文件后自动创建 parse_job。
parse_job 状态可轮询。
成功解析后生成 document_blocks。
成功 chunking 后生成 chunks_metadata。
每个 chunk 必须有 source_locator。
解析失败可 retry。
旧失败日志保留。

⸻

Phase 4：Embedding 与 Qdrant 索引

目标：完成 embedding-service 与 Qdrant 入库。

任务：

embedding-service
bge-m3 模型加载
chunk embedding
Qdrant collection 初始化
Qdrant point 写入
payload 写入
knowledge_base_id filter
is_active filter
删除文件时 chunks is_active=false
删除文件时 Qdrant points 异步清理或失效

验收标准：

指定 knowledge_base_id 可检索到对应 chunk。
不同 knowledge_base 的内容不会互相污染。
删除文件后旧 chunk 不再参与检索。

⸻

Phase 5：全文检索、混合召回与 Reranker

目标：完成 PostgreSQL tsvector 检索、向量召回合并和重排。

任务：

chunks_metadata.tsv 字段
GIN index
PostgreSQL full-text search
Qdrant vector search
merge results
deduplicate by chunk_id
reranker-service
BGE reranker
reranker top_k 截断
retrieval trace

验收标准：

同一 query 返回 vector + full-text 合并结果。
结果按 reranker score 重排。
每次检索保存 retrieved_chunk_ids。
每次重排保存 reranked_chunk_ids 和 reranker_scores。

⸻

Phase 6：RAG 问答与引用溯源

目标：完成对话、消息、SSE、LLM 调用、引用生成和证据不足拒答。

任务：

conversations 表
messages 表
message_citations 表
message_traces 表
conversation CRUD
POST message API
SSE streaming
ModelProvider 抽象
OpenAI-compatible LLM API 调用
Prompt version 管理
citation builder
grounded answer prompt
insufficient evidence policy
trace 保存

验收标准：

User 可在指定知识库内提问。
回答以 SSE 流式返回。
回答正文包含 [1] [2] 引用编号。
参考来源包含文件名、source_locator、原文片段。
无足够证据时拒答。
每次 assistant message 保存 citations。
每次问答保存 message_trace。

⸻

Phase 7：反馈与基础评估闭环

目标：完成 helpful / unhelpful 反馈和基本 bad case 数据积累。

任务：

feedback 表
POST feedback API
前端反馈按钮
保存 query_text
保存 retrieved_chunk_ids
保存 final_cited_chunk_ids
保存 model_name
保存 prompt_version
保存 embedding_model
保存 reranker_model
基础 bad case 查询接口，可选

验收标准：

每条 assistant message 可点赞/点踩。
反馈记录包含完整 telemetry。
后续可基于 feedback 判断召回失败、重排失败或生成失败。

⸻

Phase 8：前后端联调与内测准备

目标：打通完整用户路径。

任务：

登录页面
Admin 用户管理页面
KnowledgeBase 管理页面
文件上传页面
文件状态轮询
对话页面
SSE 渲染
引用展示
反馈按钮
错误提示映射
基础权限菜单
Docker Compose 全链路验证

验收标准：

Admin 可完成知识库创建、上传、解析、索引。
User 可登录、选择知识库、提问、查看引用、提交反馈。
普通 User 无法访问上传和管理功能。
系统可通过 docker compose 一键启动。

⸻

8. 全局开发约束

8.1 Python 代码规范

必须使用：

ruff
black
mypy
pytest
pydantic v2
SQLAlchemy 2.x
Alembic

要求：

所有 API request/response 使用 Pydantic Schema。
所有数据库变更必须通过 Alembic migration。
核心业务逻辑必须有单元测试。
外部服务调用必须封装 client。
禁止在 route handler 中堆叠复杂业务逻辑。

推荐后端分层：

api/routes
schemas
models
services
repositories
core
workers
clients

⸻

8.2 前端代码规范

必须使用：

Vue 3
Vite
TypeScript strict
Pinia
Vue Router
Element Plus
ESLint
Prettier

要求：

组件按 feature 分层。
API 请求统一封装。
鉴权 token 统一管理。
权限菜单根据 role 渲染。
所有后端错误根据 error.code 处理。
避免在页面组件中堆叠复杂业务逻辑。

推荐前端目录：

src/
  api/
  stores/
  router/
  views/
  components/
  features/
    auth/
    users/
    knowledge-bases/
    files/
    chat/
    feedback/
  types/
  utils/

⸻

8.3 Git 规范

必须使用：

main/dev 分支
Conventional Commits
PR review
CI lint + test

提交格式：

feat: add knowledge base CRUD
fix: handle duplicate file hash warning
refactor: split retrieval service
test: add parse job state transition tests
docs: update API contract

⸻

8.4 环境变量规范

所有配置必须来自环境变量。

禁止：

禁止 hardcode API key。
禁止 hardcode 数据库密码。
禁止把 secret 提交到 Git。
禁止在代码中写死模型服务地址。

必须维护 .env.example。

推荐环境变量：

DATABASE_URL=
REDIS_URL=
QDRANT_URL=
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
JWT_SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
MAX_FILE_SIZE_MB=50
MAX_BATCH_UPLOAD_COUNT=50
CHAT_HISTORY_RETENTION_DAYS=0
ENABLE_PROMPT_TRACE=false
LLM_PROVIDER=
LLM_API_BASE=
LLM_API_KEY=
LLM_MODEL=
EMBEDDING_SERVICE_URL=
EMBEDDING_MODEL=bge-m3
RERANKER_SERVICE_URL=
RERANKER_MODEL=bge-reranker
MINERU_SERVICE_URL=

⸻

8.5 安全约束

默认不开放注册。
默认只有 Admin 可创建用户。
密码必须 bcrypt 哈希。
登录失败 5 次锁定 15 分钟。
JWT secret 必须通过环境变量提供。
Admin 高危操作必须写 audit_logs。
普通 user 不得上传、删除、重解析文件。
所有知识库检索必须强制 knowledge_base_id 过滤。

⸻

8.6 RAG 质量约束

所有回答必须基于最终上下文 chunks。
关键事实必须有引用编号。
引用必须能回溯到 chunk_id。
证据不足必须拒答。
不得使用通用知识补全缺失事实。
不得编造文档名、页码、slide、sheet、row 或 chunk。
不得引用未进入 final_context 的 chunk。

⸻

8.7 Trace 与调试约束

每次 assistant message 必须保存：

query_text
retrieved_chunk_ids
reranked_chunk_ids
final_context_chunk_ids
final_cited_chunk_ids
reranker_scores
embedding_model
reranker_model
chat_model
prompt_version
latency_breakdown
token_usage

raw_prompt_snapshot 是否保存由环境变量控制：

ENABLE_PROMPT_TRACE=false

⸻

9. v0.1 内测通过标准

系统满足以下条件后，允许进入小团队内部内测：

1. Docker Compose 可一键启动完整系统。
2. Admin 可登录并创建普通用户。
3. Admin 可创建知识库。
4. Admin 可上传支持格式文件。
5. 文件上传具备大小、格式、同名、Hash 校验。
6. 文件可异步解析并生成 chunks。
7. chunks 可写入 PostgreSQL 和 Qdrant。
8. User 可选择一个知识库提问。
9. 系统可完成向量检索 + PostgreSQL 全文检索。
10. 系统可完成 Reranker 重排。
11. 系统可调用 LLM 生成回答。
12. 回答必须包含引用编号。
13. 引用必须包含文件名、source_locator 和原文片段。
14. 证据不足时系统必须拒答。
15. 每次问答必须保存 message_trace。
16. User 可对回答提交 helpful / unhelpful。
17. 普通 User 不能上传、删除、重解析文件。
18. 删除文件后相关 chunks 和 vectors 不再参与检索。
19. Admin 高危操作进入 audit_logs。
20. 核心链路测试通过。

⸻

10. 禁止 AI Agent 自行变更的架构决策

后续代码生成 Agent 不得自行修改以下决策：

前端必须使用 Vue 3 + Vite + TypeScript + Pinia + Element Plus。
后端必须使用 Python + FastAPI。
任务队列必须使用 Celery + Redis。
关系数据库必须使用 PostgreSQL。
向量数据库必须使用 Qdrant。
对象存储必须使用 MinIO。
文件解析必须通过独立 mineru-service。
Embedding 必须通过独立 embedding-service。
Reranker 必须通过独立 reranker-service。
认证必须使用 JWT access token + refresh token。
密码哈希必须使用 bcrypt。
MVP 不实现 GraphRAG。
MVP 不实现跨知识库查询。
MVP 不实现文件版本管理。
MVP 不实现文档级权限。
MVP 不实现 OpenAI-compatible 对外网关。

如需变更，必须先更新本规格文档并经人工确认。

这份可以直接作为 docs/product/agent-kb-v0.1-spec.md 的初始内容。
