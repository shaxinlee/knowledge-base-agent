# Step 051：文档摘要召回——总结类提问直接返回文件摘要

## 目标

当用户提问"某个文件讲了什么"、"帮我总结一下XX文档"等总结类问题时，系统
不再检索零散的 chunk 段落（召回不全），而是直接从 `document_summaries` 表中
召回对应文件的完整摘要，作为上下文交给 LLM 生成回答。

该能力复用 Step 049 已有的文档摘要数据，不新增数据库表和 migration，不改变
现有 chunk 级 RAG 主链路。

## 实现

### 意图识别层（query_router.py）

- 新增 `DOC_SUMMARY_ACTION_KEYWORDS`：总结意图关键词，包括"讲了什么"、
  "总结一下"、"帮我概括"、"主要内容"、"概要"、"简要介绍"等。
- 新增 `DOC_SUMMARY_FILE_KEYWORDS`：文件/文档引用词，包括"文件"、"文档"、
  "手册"、"报告"、"方案"、"这个"、"这份"等。
- 新增 `DOC_SUMMARY_KB_SCOPE_KEYWORDS`：知识库范围词（"知识库"、
  "本知识库"等），用于排除应走 `knowledge_base_overall` 的提问。
- 新增 `is_document_summary_query()`：同时满足"有总结意图词"和"有文件引用词"
  且"不含知识库范围词"时判定为文档摘要类查询。
- `RuleBasedKnowledgeSearchRouter.decide()` 中 `document_summary` 检测
  优先于 `knowledge_base_overall`，避免"XX文件的主要内容"被误判为知识库总览。
- `LLMKnowledgeSearchRouter` 的 prompt、system message、分类解析正则均已
  加入 `document_summary` 类别。规则匹配命中时直接返回，不经过 LLM 分类器。
- `parse_knowledge_route_category()` 正则已接受 `document_summary`。

### 检索与回答生成层（conversations.py）

- 新增 `search_document_summaries()`：查询 `document_summaries` 表中
  `completed` 状态的最新摘要，按以下优先级匹配：
  1. 文件名匹配：查询中包含文件名（含去扩展名 stem）的文件优先返回。
  2. 内容匹配：摘要正文包含查询中非停用词关键词的文件。
  3. 兜底：以上均无命中时返回所有已完成摘要。
- 新增 `build_summary_context_item()` / `is_summary_context_item()`：使用
  哨兵 UUID `00000000-0000-0000-0000-000000000002` 标识摘要上下文项，区分于
  普通 chunk 和 knowledge-base-overall。
- `get_citable_context_items()` 排除摘要项：摘要不是 chunk，不生成 citation。
- `expand_context_to_section_chunks()` 保留摘要项：哨兵 UUID 不存在于
  chunks_metadata 表中，不会被 section 展开逻辑丢弃。
- 非流式 `prepare_message_context()`：检测到 `document_summary` 后搜索摘要，
  命中则直接用摘要作为 `final_context_items` 返回；未命中则降级为 `normal_rag`
  继续走 chunk 级检索。
- 流式 `stream_create_message_events()`：检测到 `document_summary` 后搜索
  摘要，命中则直接流式生成回答（SSE stage "检索文档摘要"）并保存 trace；未命中
  则降级为 `normal_rag`。

## 边界

- 不新增数据库表或 migration；完全复用 `document_summaries` 现有数据。
- 不改变现有 chunk 级 RAG 主链路（vector + BM25 + RRF + reranker）。
- 摘要项不参与 citation 生成，不影响现有引用展示。
- 摘要项不参与 section chunk 展开，保持原样传递给 LLM。
- 无可用摘要时自动降级为 normal_rag，不阻断用户提问。

## 工作流程

```text
用户提问："帮我总结一下安全管理手册"
    ↓
路由器识别为 document_summary
（规则优先，LLM 分类器兜底）
    ↓
查询 document_summaries 表
    ├── 命中文件摘要 → 摘要作为上下文 → LLM 生成回答
    └── 未命中       → 降级 normal_rag → chunk 级检索
```

## 验证

- 后端 query_router 全量测试：18 passed（2 个环境配置类 pre-existing failure）。
- 手动验证 9 种 document_summary 类提问全部正确路由：
  - "这个文件讲了什么？" → document_summary
  - "帮我总结一下安全管理手册" → document_summary
  - "XX方案的主要内容是什么？" → document_summary
  - "概括一下这份报告" → document_summary
  - "这份文档说了什么？" → document_summary
  - "那个资料讲的什么内容？" → document_summary
  - "帮我概括一下这个手册" → document_summary
  - "简要介绍一下这篇论文" → document_summary
  - "那篇文章大致内容是什么？" → document_summary
- 知识库总览类提问不受影响：
  - "这个知识库讲什么的？" → knowledge_base_overall
  - "当前知识库都包含什么数据？" → knowledge_base_overall
  - "这个知识库的主要内容是什么？" → knowledge_base_overall
- 普通 RAG 类提问不受影响：
  - "公司的报销流程是什么？" → normal_rag
  - "DIP是什么？" → normal_rag
- 安全类别不受影响：identity / greeting / thanks。
