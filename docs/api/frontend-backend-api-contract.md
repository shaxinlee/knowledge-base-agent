# 知识库 Agent 助手 v0.1 前后端接口契约

版本：v0.1
来源：`docs/specs/SDD.v0.1.md`
用途：前端、后端、测试、联调共同遵守的 API 与数据结构约定。

## 1. 全局约定

### 1.1 Base URL

所有业务接口统一使用：

```text
/api/v1
```

本地开发默认：

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
API Base: /api/v1
```

### 1.2 认证

除登录、用户端可进入用户列表、用户端免密会话、刷新 token、健康检查外，所有业务接口默认要求：

```http
Authorization: Bearer <access_token>
```

Token 类型：

- `access_token`：短期访问令牌，默认有效期 1800 秒。
- `refresh_token`：刷新令牌，用于获取新的 access token。

### 1.3 角色

```text
admin
user
```

v0.1 不实现 Editor 角色、用户组、团队空间、文档级权限。

### 1.4 时间格式

所有时间字段使用 ISO 8601 UTC 字符串：

```text
2026-06-06T02:30:00Z
```

### 1.5 ID 格式

前端不要解析 ID 语义，只作为字符串处理。

推荐前缀：

- `usr_`：用户
- `kb_`：知识库
- `file_`：文件
- `job_`：解析任务
- `block_`：文档块
- `chunk_`：切片
- `conv_`：会话
- `msg_`：消息
- `cite_`：引用
- `trace_`：链路追踪
- `fb_`：反馈
- `audit_`：审计日志

### 1.6 成功响应

单对象接口直接返回对象。

列表接口统一返回：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### 1.7 错误响应

所有错误必须使用统一结构：

```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds 50MB limit.",
    "details": {},
    "request_id": "req_xxx"
  }
}
```

前端展示优先级：

1. 如果 `code` 在前端错误映射表中，展示本地化文案。
2. 否则展示 `message`。
3. 调试面板可展示 `request_id`。

### 1.8 常用 HTTP 状态码

| Status | 场景 |
| --- | --- |
| 200 | 查询、更新、操作成功 |
| 201 | 创建成功 |
| 202 | 异步任务已创建 |
| 204 | 删除或退出成功，无响应体 |
| 400 | 参数错误或业务校验失败 |
| 401 | 未登录或 token 失效 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突，例如同名文件 |
| 413 | 文件过大 |
| 422 | 请求结构校验失败 |
| 423 | 账号锁定 |
| 500 | 服务端错误 |

### 1.9 稳定错误码

| Code | 含义 |
| --- | --- |
| `UNAUTHORIZED` | 未登录或 token 无效 |
| `FORBIDDEN` | 权限不足 |
| `VALIDATION_ERROR` | 请求参数校验失败 |
| `RESOURCE_NOT_FOUND` | 资源不存在 |
| `ACCOUNT_DISABLED` | 账号已禁用 |
| `ACCOUNT_LOCKED` | 登录失败次数过多，账号暂时锁定 |
| `INVALID_CREDENTIALS` | 用户名或密码错误 |
| `FILE_TOO_LARGE` | 文件超过 50MB |
| `TOO_MANY_FILES` | 单次上传超过 50 个文件 |
| `UNSUPPORTED_FILE_TYPE` | 文件格式不支持 |
| `DUPLICATE_FILE_NAME` | 同一知识库内文件名重复 |
| `DUPLICATE_FILE_HASH` | 同一知识库内 hash 重复但文件名不同 |
| `KNOWLEDGE_BASE_INACTIVE` | 知识库不存在或不可用 |
| `PARSE_JOB_NOT_READY` | 解析任务尚未完成 |
| `INSUFFICIENT_EVIDENCE` | 检索证据不足，系统拒答 |
| `UPSTREAM_SERVICE_ERROR` | MinerU、Embedding、Reranker 或 LLM 服务异常 |

## 2. 枚举

### 2.1 KnowledgeBaseStatus

```text
active
deleting
deleted
```

### 2.2 FileStatus

```text
uploaded
queued
processing
indexed
partially_indexed
failed
deleting
deleted
```

### 2.3 ParseJobStatus

```text
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
```

v0.1 前端不提供取消按钮，但可以展示 `cancelled`。

### 2.4 MessageRole

```text
user
assistant
system
```

### 2.5 FeedbackRating

```text
helpful
unhelpful
```

## 3. Auth API

### POST `/api/v1/auth/login`

权限：公开接口。

请求：

```json
{
  "username": "admin",
  "password": "password"
}
```

响应：

```json
{
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "usr_xxx",
    "username": "admin",
    "display_name": "Administrator",
    "role": "admin",
    "is_active": true
  }
}
```

错误：

- `INVALID_CREDENTIALS`
- `ACCOUNT_DISABLED`
- `ACCOUNT_LOCKED`

### GET `/api/v1/auth/consumer-users`

权限：公开接口。

用途：to C 用户端入口页展示可进入用户下拉菜单。列表只返回 Admin 用户管理中已注册且启用的普通 `user` 账号，不返回 admin 或已禁用账号。

请求：无请求体。

响应：

```json
{
  "items": [
    {
      "username": "alice",
      "display_name": "Alice Zhang"
    }
  ]
}
```

### POST `/api/v1/auth/consumer-session`

权限：公开接口。

用途：to C 用户端选择用户名后创建对应普通 `user` 角色会话。该接口不得签发 admin 权限，不要求用户输入密码。

请求：

```json
{
  "username": "alice"
}
```

响应：同 `/auth/login`，其中 `user.role` 必须为 `user`。

```json
{
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "usr_xxx",
    "username": "alice",
    "display_name": "Alice Zhang",
    "role": "user",
    "is_active": true
  }
}
```

### POST `/api/v1/auth/refresh`

权限：公开接口，但需要 refresh token。

请求：

```json
{
  "refresh_token": "jwt_refresh_token"
}
```

响应：

```json
{
  "access_token": "new_jwt_access_token",
  "refresh_token": "new_jwt_refresh_token",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST `/api/v1/auth/logout`

权限：当前登录用户。

请求：

```json
{
  "refresh_token": "jwt_refresh_token"
}
```

响应：`204 No Content`

说明：logout 成功后，该 refresh token 不可继续用于 `/auth/refresh`。

### GET `/api/v1/auth/me`

权限：当前登录用户。

响应：

```json
{
  "id": "usr_xxx",
  "username": "admin",
  "display_name": "Administrator",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-06-06T02:30:00Z",
  "last_login_at": "2026-06-06T02:30:00Z"
}
```

## 4. Users API

### GET `/api/v1/users`

权限：admin only。

Query：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | number | 1 | 页码 |
| `page_size` | number | 20 | 每页数量，最大 100 |
| `keyword` | string | 空 | 按用户名或显示名搜索 |
| `role` | string | 空 | `admin` 或 `user` |
| `is_active` | boolean | 空 | 是否启用 |

响应：

```json
{
  "items": [
    {
      "id": "usr_xxx",
      "username": "alice",
      "display_name": "Alice",
      "role": "user",
      "is_active": true,
      "created_at": "2026-06-06T02:30:00Z",
      "last_login_at": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST `/api/v1/users`

权限：admin only。

请求：

```json
{
  "email": "alice@example.local",
  "username": "alice",
  "display_name": "Alice",
  "password": "InitialPassword123",
  "role": "user"
}
```

响应：`201 Created`

```json
{
  "id": "usr_xxx",
  "username": "alice",
  "display_name": "Alice",
  "role": "user",
  "is_active": true,
  "created_at": "2026-06-06T02:30:00Z",
  "last_login_at": null
}
```

### PATCH `/api/v1/users/{user_id}`

权限：admin only。

请求：

```json
{
  "display_name": "Alice Zhang",
  "role": "user"
}
```

响应：User 对象。

### POST `/api/v1/users/{user_id}/disable`

权限：admin only。

响应：User 对象，`is_active=false`。

### POST `/api/v1/users/{user_id}/enable`

权限：admin only。

响应：User 对象，`is_active=true`。

### POST `/api/v1/users/{user_id}/reset-password`

权限：admin only。

请求：

```json
{
  "new_password": "NewPassword123"
}
```

响应：

```json
{
  "user_id": "usr_xxx",
  "reset_at": "2026-06-06T02:30:00Z"
}
```

### 当前用户资料

当前实现使用 `GET /api/v1/auth/me` 作为 Profile 页面只读数据来源。

`GET /api/v1/users/me/profile` 与 `PATCH /api/v1/users/me/profile` 当前未实现。v0.1 Demo 不提供用户自助编辑 answer_style / language 偏好的接口。

响应：Profile 对象。

### Assistant Profile

用于配置知识库助手在身份、能力、寒暄、感谢、使用说明、转人工和闲聊兜底等非知识库检索问题上的固定话术。

#### GET `/api/v1/assistant-profile`

权限：admin only。

响应：

```json
{
  "name": "知识库问答助手",
  "identity_answer": "我是你的知识库问答助手，可以基于已接入的文档、制度、产品资料和业务知识回答问题。",
  "capability_answer": "我可以帮你查询知识库内容、总结文档、解释流程、定位相关资料，并在答案中给出引用来源。",
  "greeting_answer": "你好，我是知识库问答助手。你可以直接提问需要查询的制度、流程、产品资料或业务知识。",
  "thanks_answer": "不客气，有需要查询知识库内容时可以继续问我。",
  "usage_answer": "你可以直接输入问题，我会判断是否需要检索知识库；如果需要，我会基于已接入资料回答并给出引用来源。",
  "handoff_answer": "当前我无法直接转接人工客服。你可以联系系统管理员或相关业务负责人处理人工支持需求。",
  "fallback_casual_answer": "我是知识库问答助手，更擅长回答已接入资料中的制度、流程、产品和业务知识问题。"
}
```

#### PATCH `/api/v1/assistant-profile`

权限：admin only。

请求：与 `GET /api/v1/assistant-profile` 响应字段一致，所有字段均为非空字符串。

响应：更新后的 Assistant Profile 对象。

## 5. Knowledge Bases API

### GET `/api/v1/knowledge-bases`

权限：admin 和 user。

Query：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | number | 1 | 页码 |
| `page_size` | number | 20 | 每页数量 |
| `keyword` | string | 空 | 按名称搜索 |
| `status` | string | `active` | 知识库状态。以 SDD 为准：`active`、`deleting`、`deleted` |

响应：

```json
{
  "items": [
    {
      "id": "kb_xxx",
      "name": "项目知识库",
      "description": "内部项目资料",
      "status": "active",
      "file_count": 12,
      "chunk_count": 340,
      "created_by": "usr_admin",
      "created_at": "2026-06-06T02:30:00Z",
      "updated_at": "2026-06-06T02:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST `/api/v1/knowledge-bases`

权限：admin only。

请求：

```json
{
  "name": "项目知识库",
  "description": "内部项目资料"
}
```

响应：`201 Created`，KnowledgeBase 对象。

### GET `/api/v1/knowledge-bases/{kb_id}`

权限：admin 和 user。

响应：KnowledgeBase 对象。

### PATCH `/api/v1/knowledge-bases/{kb_id}`

权限：admin only。

请求：

```json
{
  "name": "项目知识库",
  "description": "更新后的描述",
  "status": "active"
}
```

响应：KnowledgeBase 对象。

### DELETE `/api/v1/knowledge-bases/{kb_id}`

权限：admin only。

规则：

- 软删除。
- 创建 cleanup job。
- 写入 audit log。
- 前端必须二次确认。

响应：`204 No Content`

## 6. Files API

### GET `/api/v1/knowledge-bases/{kb_id}/files`

权限：admin；user v0.1 可只读。

Query：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | number | 1 | 页码 |
| `page_size` | number | 20 | 每页数量 |
| `keyword` | string | 空 | 按文件名搜索 |
| `status` | string | 空 | 文件状态 |

响应：

```json
{
  "items": [
    {
      "id": "file_xxx",
      "knowledge_base_id": "kb_xxx",
      "file_name": "report.pdf",
      "file_ext": ".pdf",
      "mime_type": "application/pdf",
      "size_bytes": 102400,
      "file_hash": "sha256_hex",
      "status": "indexed",
      "latest_parse_job_id": "job_xxx",
      "created_by": "usr_admin",
      "created_at": "2026-06-06T02:30:00Z",
      "updated_at": "2026-06-06T02:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST `/api/v1/knowledge-bases/{kb_id}/files/upload`

权限：admin only。

Content-Type：

```http
multipart/form-data
```

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `files` | file[] | 是 | 最多 50 个 |
| `force` | boolean | 否 | hash 重复 warning 后强制上传 |

限制：

- 单文件最大 50MB。
- 单次最多 50 个文件。
- 支持 `.pdf .md .docx .txt .xlsx .xls .csv .pptx .png .jpg .jpeg .webp`。

成功响应：`202 Accepted`

```json
{
  "uploaded": [
    {
      "file": {
        "id": "file_xxx",
        "knowledge_base_id": "kb_xxx",
        "file_name": "report.pdf",
        "file_ext": ".pdf",
        "mime_type": "application/pdf",
        "size_bytes": 102400,
        "file_hash": "sha256_hex",
        "status": "queued",
        "latest_parse_job_id": "job_xxx",
        "created_by": "usr_admin",
        "created_at": "2026-06-06T02:30:00Z",
        "updated_at": "2026-06-06T02:30:00Z"
      },
      "parse_job": {
        "id": "job_xxx",
        "file_id": "file_xxx",
        "status": "queued",
        "error_message": null,
        "created_at": "2026-06-06T02:30:00Z",
        "updated_at": "2026-06-06T02:30:00Z"
      }
    }
  ],
  "warnings": []
}
```

hash 重复 warning 响应：`409 Conflict`

```json
{
  "error": {
    "code": "DUPLICATE_FILE_HASH",
    "message": "File content already exists in this knowledge base.",
    "details": {
      "duplicates": [
        {
          "incoming_file_name": "copy.pdf",
          "existing_file_id": "file_xxx",
          "existing_file_name": "report.pdf",
          "file_hash": "sha256_hex"
        }
      ],
      "can_force_upload": true
    },
    "request_id": "req_xxx"
  }
}
```

前端交互：

- `DUPLICATE_FILE_NAME`：直接提示失败，不允许继续。
- `DUPLICATE_FILE_HASH` 且 `can_force_upload=true`：弹出二次确认，确认后以 `force=true` 重传。

### GET `/api/v1/files/{file_id}`

权限：admin；user v0.1 可只读。

响应：File 对象。

### GET `/api/v1/files/{file_id}/status`

权限：admin only。

响应：

```json
{
  "file_id": "file_xxx",
  "file_status": "processing",
  "latest_parse_job": {
    "id": "job_xxx",
    "status": "indexing",
    "progress": 80,
    "error_code": null,
    "error_message": null,
    "logs": {
      "provider": "mineru",
      "mineru_latest_state": "done",
      "parsed_result": {
        "bucket": "parsed-results",
        "key": "knowledge-bases/kb_xxx/files/file_xxx/parse-jobs/job_xxx/mineru-full.zip"
      }
    },
    "started_at": "2026-06-06T02:30:00Z",
    "finished_at": null,
    "updated_at": "2026-06-06T02:35:00Z"
  }
}
```

### DELETE `/api/v1/files/{file_id}`

权限：admin only。

规则：

- 文件软删除。
- chunks 设置 `is_active=false`。
- Qdrant points 异步删除或失效。
- 创建 cleanup job。
- 写入 audit log。

响应：`204 No Content`

### POST `/api/v1/files/{file_id}/retry-parse`

权限：admin only。

响应：`202 Accepted`

```json
{
  "id": "job_xxx",
  "file_id": "file_xxx",
  "status": "parsing",
  "progress": 10,
  "error_code": null,
  "error_message": null,
  "logs": {
    "provider": "mineru",
    "mode": "api_v4_file_urls_batch",
    "mineru": {
      "batch_id": "batch_xxx",
      "data_id": "job_xxx"
    }
  },
  "created_at": "2026-06-06T02:30:00Z",
  "updated_at": "2026-06-06T02:30:00Z"
}
```

说明：

- 当前实现会在 retry-parse 请求中直接提交 MinerU API，提交成功后返回 `parsing`。
- 未配置 `MINERU_API_TOKEN` 时返回 `UPSTREAM_SERVICE_ERROR`，不会创建可污染检索集合的成功产物。
- `logs` 仅用于 Admin 调试解析链路，可能包含 MinerU batch/result 摘要和 parsed-results 存储位置。

### GET `/api/v1/files/{file_id}/chunks`

权限：admin only，MVP 调试用。

Query：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | number | 1 | 页码 |
| `page_size` | number | 20 | 每页数量 |

响应：

```json
{
  "items": [
    {
      "id": "chunk_xxx",
      "file_id": "file_xxx",
      "knowledge_base_id": "kb_xxx",
      "content": "原文切片内容",
      "source_locator": "pdf:p12-p13",
      "token_count": 320,
      "is_active": true,
      "created_at": "2026-06-06T02:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## 7. Conversations API

### GET `/api/v1/conversations?knowledge_base_id=<kb_id>`

权限：当前登录用户。

规则：

- 必须传 `knowledge_base_id`。
- 只返回当前用户自己的会话。
- v0.1 不支持跨知识库查询。

响应：

```json
{
  "items": [
    {
      "id": "conv_xxx",
      "knowledge_base_id": "kb_xxx",
      "title": "项目核心方法",
      "created_at": "2026-06-06T02:30:00Z",
      "updated_at": "2026-06-06T02:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST `/api/v1/conversations`

权限：当前登录用户。

请求：

```json
{
  "knowledge_base_id": "kb_xxx",
  "title": "optional title"
}
```

响应：`201 Created`

```json
{
  "id": "conv_xxx",
  "knowledge_base_id": "kb_xxx",
  "title": "optional title",
  "created_at": "2026-06-06T02:30:00Z",
  "updated_at": "2026-06-06T02:30:00Z"
}
```

### GET `/api/v1/conversations/{conversation_id}`

权限：当前登录用户。

响应：

```json
{
  "id": "conv_xxx",
  "knowledge_base_id": "kb_xxx",
  "title": "项目核心方法",
  "created_at": "2026-06-06T02:30:00Z",
  "updated_at": "2026-06-06T02:30:00Z",
  "messages": [
    {
      "id": "msg_user",
      "conversation_id": "conv_xxx",
      "role": "user",
      "content": "这个项目的核心方法是什么？",
      "created_at": "2026-06-06T02:30:00Z",
      "citations": [],
      "feedback_rating": null
    },
    {
      "id": "msg_assistant",
      "conversation_id": "conv_xxx",
      "role": "assistant",
      "content": "根据资料……[1]",
      "created_at": "2026-06-06T02:30:10Z",
      "feedback_rating": "helpful",
      "citations": [
        {
          "id": "cite_xxx",
          "index": 1,
          "file_name": "report.pdf",
          "source_locator": "pdf:p12-p13",
          "excerpt": "原文片段……",
          "chunk_id": "chunk_xxx"
        }
      ]
    }
  ]
}
```

### DELETE `/api/v1/conversations/{conversation_id}`

权限：当前登录用户。

响应：`204 No Content`

## 8. Retrieval API

### POST `/api/v1/knowledge-bases/{knowledge_base_id}/retrieval/search`

权限：当前登录用户。

说明：基础检索接口，用于在单个知识库内执行 query embedding、Qdrant vector search、关键词召回、RRF 合并与 chunk_id 去重，并在候选结果合并后调用 reranker-service 进行重排。当前关键词召回在 `BM25_ENABLED=true` 时使用 OpenSearch BM25 + IK Analyzer；`BM25_ENABLED=false` 时回退 PostgreSQL full-text。该接口不调用 LLM，不生成 SSE 或最终回答。

请求：

```json
{
  "query": "这个项目的核心方法是什么？",
  "vector_top_k": 30,
  "full_text_top_k": 30,
  "top_k": 8
}
```

规则：

- 后端必须校验 knowledge_base_id 存在且为 active。
- Qdrant vector search 必须携带 `knowledge_base_id` 和 `is_active=true` filter。
- OpenSearch BM25 search 必须限定 `knowledge_base_id` 和 `is_active=true`；fallback PostgreSQL full-text 也必须限定 `knowledge_base_id` 和 active chunks。
- 合并结果必须按 `chunk_id` 去重。
- 合并后的候选结果必须调用 reranker-service 重排。
- 返回结果必须包含 `file_name`、`source_locator`、`excerpt` 和 `chunk_id`。

响应：

```json
{
  "knowledge_base_id": "kb_xxx",
  "query": "这个项目的核心方法是什么？",
  "items": [
    {
      "chunk_id": "chunk_xxx",
      "file_id": "file_xxx",
      "file_name": "report.pdf",
      "source_locator": "pdf:p12",
      "excerpt": "原文片段……",
      "score": 1.42,
      "source": "hybrid"
    }
  ],
  "total": 1
}
```

## 9. Messages / Chat API

### POST `/api/v1/conversations/{conversation_id}/messages`

权限：当前登录用户。

请求：

```json
{
  "content": "这个项目的核心方法是什么？",
  "stream": true
}
```

规则：

- conversation 必须属于当前用户。
- conversation 必须绑定单个 knowledge_base_id。
- 检索只允许在该 knowledge_base_id 内执行。
- 回答只能基于最终上下文 chunks。
- 证据不足必须拒答。
- “这个知识库讲什么”“知识库整体概览”“有哪些资料”等整体总结问题走
  `knowledge_base_overall` 路由，不执行相似度 Top-K 检索；回答上下文必须包含
  知识库创建时间、当前社区摘要，以及当前知识库下每个未删除文件的最新文档摘要
  或摘要状态。该类整体概览回答不生成 Chunk citation。

响应：

- `stream=false`：返回 JSON，包含 `user_message` 与 `assistant_message`。
- `stream=true`：返回 SSE stream，事件格式保持不变；配置 `LLM_API_BASE_URL`/`LLM_MODEL` 后回答内容来自 LLM API，否则使用明确标记的 template demo client。

`stream=false` 响应示例：

```json
{
  "user_message": {
    "id": "msg_user",
    "conversation_id": "conv_xxx",
    "role": "user",
    "content": "这个项目的核心方法是什么？",
    "created_at": "2026-06-06T02:30:10Z",
    "citations": [],
    "feedback_rating": null
  },
  "assistant_message": {
    "id": "msg_assistant",
    "conversation_id": "conv_xxx",
    "role": "assistant",
    "content": "根据当前知识库检索结果……[1]",
    "created_at": "2026-06-06T02:30:11Z",
    "feedback_rating": null,
    "citations": [
      {
        "id": "cite_xxx",
        "index": 1,
        "file_name": "report.pdf",
        "source_locator": "pdf:p12",
        "excerpt": "原文片段……",
        "chunk_id": "chunk_xxx"
      }
    ]
  }
}
```

`stream=true` 响应：SSE stream。

响应头：

```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

SSE 事件：

```text
event: message_created
data: {"user_message":{"id":"msg_user","conversation_id":"conv_xxx","role":"user","content":"这个项目的核心方法是什么？","created_at":"2026-06-06T02:30:10Z","citations":[],"feedback_rating":null},"assistant_message":{"id":"msg_assistant","conversation_id":"conv_xxx","role":"assistant","content":"","created_at":"2026-06-06T02:30:11Z","citations":[{"id":"cite_xxx","index":1,"file_name":"report.pdf","source_locator":"pdf:p12","excerpt":"原文片段……","chunk_id":"chunk_xxx"}],"feedback_rating":null}}

event: retrieval
data: {"retrieved_count":1,"reranked_count":0,"final_context_count":1}

event: token
data: {"text":"根据"}

event: token
data: {"text":"资料"}

event: done
data: {"message_id":"msg_assistant","answer":"根据资料……[1]","citations":[{"index":1,"file_name":"report.pdf","source_locator":"pdf:p12-p13","excerpt":"原文片段……","chunk_id":"chunk_xxx"}]}
```

错误事件：

```text
event: error
data: {"code":"INSUFFICIENT_EVIDENCE","message":"当前知识库中没有足够证据回答该问题。","request_id":"req_xxx"}
```

前端处理规则：

- `token`：追加到当前 assistant 临时消息。
- `done`：用最终 answer、citations 覆盖临时消息。
- `error`：停止流式渲染并展示错误提示。
- 网络中断：允许用户重新发送问题，v0.1 不要求断点续传。

## 10. Feedback API

### POST `/api/v1/messages/{message_id}/feedback`

权限：当前登录用户。

请求：

```json
{
  "rating": "helpful",
  "comment": "引用准确"
}
```

响应：`201 Created`

```json
{
  "id": "fb_xxx",
  "message_id": "msg_xxx",
  "user_id": "usr_xxx",
  "knowledge_base_id": "kb_xxx",
  "rating": "helpful",
  "comment": "引用准确",
  "query_text": "这个项目的核心方法是什么？",
  "retrieved_chunk_ids": ["chunk_xxx"],
  "final_cited_chunk_ids": ["chunk_xxx"],
  "model_name": "configured-llm-model-or-template-demo",
  "prompt_version": "rag-citations-v1",
  "embedding_model": "bge-m3",
  "reranker_model": "bge-reranker",
  "latency_ms": null,
  "token_input": null,
  "token_output": null,
  "created_at": "2026-06-06T02:30:00Z",
  "updated_at": "2026-06-06T02:30:00Z"
}
```

规则：

- 只能对 assistant message 反馈。
- 同一用户对同一 message 重复反馈时，后端更新原反馈。
- 反馈记录必须关联 message_trace，用于后续 bad case 分析。
- `model_name` / `prompt_version` 来自 message trace；真实 LLM API 配置后记录实际 `LLM_MODEL` 和 `rag-citations-v1`，未配置时记录 template demo client。

## 11. Audit Logs API

### GET `/api/v1/audit-logs`

权限：admin only。

Query：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | number | 1 | 页码 |
| `page_size` | number | 20 | 每页数量 |
| `actor_id` | string | 空 | 操作人 |
| `action` | string | 空 | 操作类型 |
| `resource_type` | string | 空 | 资源类型 |

响应：

```json
{
  "items": [
    {
      "id": "audit_xxx",
      "actor_id": "usr_admin",
      "action": "file.delete",
      "resource_type": "file",
      "resource_id": "file_xxx",
      "details": {},
      "created_at": "2026-06-06T02:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## 11. Health API

### GET `/api/v1/health`

权限：公开接口。

响应：

```json
{
  "status": "ok",
  "service": "backend-api",
  "version": "0.1.0"
}
```

## 12. 前端页面与接口映射

| 页面 | 需要调用的接口 |
| --- | --- |
| 入口选择页 | 用户页面：`GET /auth/consumer-users`、`POST /auth/consumer-session`；管理员页面：进入登录页 |
| 管理员登录页 | `POST /auth/login` |
| 当前用户初始化 | `GET /auth/me` |
| Admin 用户管理 | `GET /users`、`POST /users`、`PATCH /users/{id}`、`disable/enable/reset-password` |
| 个人资料 | `GET /auth/me`、管理员额外调用 `GET/PATCH /assistant-profile` |
| 知识库列表 | `GET /knowledge-bases` |
| 知识库管理 | `POST/PATCH/DELETE /knowledge-bases` |
| 文件列表 | `GET /knowledge-bases/{kb_id}/files` |
| 文件上传 | `POST /knowledge-bases/{kb_id}/files/upload` |
| 文件状态 | `GET /files/{file_id}/status` |
| Chunk 调试 | `GET /files/{file_id}/chunks` |
| 会话列表 | `GET /conversations?knowledge_base_id=<kb_id>` |
| 对话页 | `POST /conversations`、`GET /conversations/{id}`、`POST /conversations/{id}/messages` |
| 反馈 | `POST /messages/{message_id}/feedback` |
| 审计日志 | `GET /audit-logs` |

## 13. v0.1 不提供的接口

以下接口 v0.1 不实现：

- 跨知识库查询接口。
- GraphRAG 查询接口。
- 实体抽取、关系抽取、社区摘要接口。

例外：2026-06-21 批准的文档结构化摘要提供以下 Admin 接口，但不提供关系图谱或
GraphRAG 接口：

- `GET /api/v1/files/{file_id}/summary`：返回当前 parse job 的摘要状态、正文、
  Chunk 总数、完成数、成功数、失败数、模型和 prompt 版本。
- `POST /api/v1/files/{file_id}/summary/retry`：Body 为 `{"force": false}`；
  `false` 仅重试失败/缺失项，`true` 重建当前 active chunks。
- `GET /api/v1/files/{file_id}/chunks` 的每个 Chunk 增加可空
  `knowledge_extraction`，用于 Admin 调试完整结构化 JSON。

摘要状态为 `pending | running | completed | partially_completed | failed |
not_ready`。摘要状态独立于文件解析/索引状态，摘要失败不得把 indexed 文件改为
failed。

### 文档摘要关系图与社区摘要

- `GET /api/v1/knowledge-graph`
  - Admin 与普通 User 均可访问。
  - Query：`knowledge_base_id`、`include_cross_knowledge_base`、
    `min_similarity`。
  - 返回文档节点、相似度边、跨库标记、全局构建状态和相关知识库社区摘要。
  - 同时返回 `total_document_count`、`summarized_document_count`、
    `pending_summary_count`、`failed_summary_count` 和
    `not_ready_document_count`，用于区分“图谱节点少”与“文档摘要仍在生成”。
- `POST /api/v1/knowledge-graph/refresh`
  - 仅 Admin。
  - Body：`{"force_embeddings": false}`。
  - 普通刷新重建关系与变化的社区摘要；`true` 时清空文档摘要向量缓存后重算。
- `GET /api/v1/knowledge-bases/{knowledge_base_id}/community-summary`
  - Admin 与普通 User 均可访问 active 知识库。
  - 返回 `pending | running | completed | failed | not_ready`、社区摘要正文、
    文档数、模型、prompt 版本和更新时间。

关系图仅使用当前 active 文件的最新 `completed` 或 `partially_completed` 文档
摘要。跨知识库边只能连接 active 知识库中的可见文件。
- OpenAI-compatible 对外网关。
- Text2SQL 接口。
- 文档级权限接口。
- 用户组、团队空间、Editor 角色接口。
- 文件版本管理接口。
- 手动编辑 chunk 接口。
