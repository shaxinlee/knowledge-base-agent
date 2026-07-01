# 知识库召回优化方案

> 基于 `accuracy_review.md` 审查结果，结合实际代码验证后整理。
> 生成时间：2026-06-29
> 实施时间：2026-06-30（通过 `apply_optimizations.py` 批量应用）

## 实施状态

| 项 | 状态 | 落点 |
|---|---|---|
| #1 query heading 对齐 | ✅ 已实施 | `retrieval.py::search_vector_candidates` 加 `检索知识库内容：` 前缀 |
| #2 Postgres 中文全文搜索 | 📝 TODO 注释 | 待 OpenSearch + IK 启用；已在 `search_postgres_full_text` 中标注 |
| #3 evidence gate 逐条过滤 | ✅ 已实施 | `conversations.py::apply_evidence_gate` 改为列表推导过滤 |
| #4 无 heading chunk 扩展 | ✅ 已实施 | `collect_section_chunks` 对无 heading 的 chunk 取前后各 2 个相邻 chunk |
| #5 向量相似度阈值 | ✅ 已实施 | `vector_index.py::search_points` 新增 `score_threshold`（默认 0.5） |
| #6 reranker 分数归一化 | ✅ 已实施（可选） | `reranker.py::sigmoid_normalize` + `evidence_normalize_reranker_scores=False` |
| #7 动态 final_top_k | ✅ 已实施 | 按 `route_decision.intent` 在 summarization/comparison 时提升到 24 |


## P0 — 必须修复

### 1. 向量搜索 query 缺少 heading 前缀（向量-索引文本不对齐）

**文件**: `backend/app/services/retrieval.py:186`（`search_vector_candidates`）

**问题**: 索引时使用 `build_indexable_chunk_text(chunk)` 生成包含 heading_path + source_locator + 正文的文本做 embedding。但搜索时直接用原始 `query` 做 embedding，没有任何上下文增强。两者在向量空间中落点不同，导致语义匹配质量下降。

```python
# 索引时（indexing.py:64-65）—— 含 heading 前缀
vectors = embed_texts_in_batches(
    embedding_client,
    [build_indexable_chunk_text(chunk) for chunk in chunks],
)

# 搜索时（retrieval.py:186）—— 只有原始 query
vectors = embedding_client.embed_texts([query])
```

**影响**: 短 query（如 "HiMedAgent是什么"）与带标题上下文的 chunk 向量不在同一语义子空间，召回相关性显著降低。

**修复方案**:

方案 A（推荐）：在 `search_vector_candidates` 中对 query 做轻量增强，加上知识库名称或检索目标的引导前缀：
```python
# 在 search_vector_candidates 中
enhanced_query = f"检索知识库内容：{query}"
vectors = embedding_client.embed_texts([enhanced_query])
```

方案 B：如果 embedding 模型支持 query/document 双模式（如 bge-m3 的 `input_type`），在 embed 时指定 `"query"` 模式，索引时用 `"document"` 模式。

**工作量**: 0.5h

---

### 2. Postgres 全文搜索对中文无效

**文件**: `backend/app/services/retrieval.py:318`（`search_postgres_full_text`）

**问题**: 使用 PostgreSQL 的 `simple` 词典做全文搜索：
```python
ts_vector = func.to_tsvector("simple", indexable_text)  # 索引
ts_query = func.websearch_to_tsquery("simple", query)   # 检索
```

`simple` 词典只做小写化和去停用词，按空格切分。中文没有空格，整段被当作一个 token，几乎永远无法匹配。

**影响**: `bm25_enabled=False` 时回退到此路径，中文关键词召回完全失效，hybrid 搜索退化为纯 vector 搜索。

**修复方案**:

方案 A（推荐）：启用 OpenSearch + IK 分词器（已在 `config.py:96-97` 配置了 `ik_max_word`/`ik_smart`），设 `bm25_enabled=True`，并重建索引。

方案 B（过渡）：在 Postgres 中安装 `zhparser` 扩展，创建中文分词配置：
```sql
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
-- 然后替换 "simple" 为 "chinese"
```

方案 C（最小改动）：如果暂时无法启用分词，至少将 `simple` 替换为对中文更友好的处理——将 query 按字符 n-gram 展开搜索（精度低但比完全无效好）。

**工作量**: 方案 A 2-4h（含重建索引）；方案 B 2h；方案 C 1h

---

## P1 — 高优先级

### 3. Evidence gate 是"全有或全无"，应改为逐条过滤

**文件**: `backend/app/services/conversations.py:1082-1097`

**问题**: 当前逻辑取 top-N 结果中的**最高分**与阈值比较，决定**全部保留或全部丢弃**：
```python
def apply_evidence_gate(items, *, route_decision):
    limit = 12 if route_decision.visual_result_mode == "gallery" else 6
    contexts = list(items[:limit])
    if not contexts:
        return []
    threshold = get_settings().evidence_min_reranker_score
    if threshold is None:
        return contexts          # ← 默认 None，直接放行
    if max(item.score for item in contexts) < threshold:
        return []                # ← 全部丢弃
    return contexts              # ← 全部保留（含低于阈值的）
```

**影响**:
- 最高分 0.36（刚过 0.35），其余都是 0.05 → 低质量结果全部送入 LLM
- 最高分 0.34（差一点），其余有 0.33、0.32 → 全部丢弃，丢失有用信息

**修复方案**:
```python
def apply_evidence_gate(items, *, route_decision):
    limit = 12 if route_decision.visual_result_mode == "gallery" else 6
    contexts = list(items[:limit])
    if not contexts:
        return []
    threshold = get_settings().evidence_min_reranker_score
    if threshold is None:
        return contexts
    # 逐条过滤，只保留分数达标的
    return [item for item in contexts if item.score >= threshold]
```

**工作量**: 0.5h

---

### 4. 无 heading_path 的 chunk 不扩展任何上下文

**文件**: `backend/app/services/conversations.py:1279`（`collect_section_chunks`）

**问题**: 当 chunk 没有 `heading_path`（纯文本文件、OCR 文档等），直接返回单个 chunk：
```python
if not hit_chunk.heading_path:
    return [hit_chunk]
```

**影响**: 约 1000 字符的单一 chunk 可能缺少关键上下文，LLM 回答不完整或断章取义。

**修复方案**: 无 heading 时扩展前后各 1-2 个同文件相邻 chunk：
```python
if not hit_chunk.heading_path:
    hit_index = next((i for i, c in enumerate(chunks) if c.id == hit_chunk.id), None)
    if hit_index is None:
        return [hit_chunk]
    start = max(0, hit_index - 2)
    end = min(len(chunks) - 1, hit_index + 2)
    return list(chunks[start : end + 1])
```

**工作量**: 0.5h

---

## P2 — 中优先级

### 5. 向量搜索无相似度阈值

**文件**: `backend/app/services/vector_index.py:176-239`（`search_points`）

**问题**: Qdrant 搜索只设 `limit`，不设 `score_threshold`，即使余弦相似度只有 0.1 也返回 top-k。

**修复方案**: 添加可选的 `score_threshold` 参数（建议 cosine 相似度 0.5）：
```python
response = httpx.post(
    f"{self.base_url}/collections/{self.collection_name}/points/search",
    json={
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "filter": {"must": filters},
        "score_threshold": 0.5,  # 新增
    },
)
```

**工作量**: 0.5h

---

### 6. Reranker 分数未归一化

**文件**: `backend/app/services/reranker.py` + `backend/app/core/config.py:88`

**问题**: `evidence_min_reranker_score=0.35` 假设分数在 [0,1]，但不同 reranker 模型分数范围不同。`parse_reranker_scores` 直接返回原始分数，不做归一化。

**修复方案**: 在 `parse_reranker_scores` 后添加 sigmoid 归一化，或在配置中支持 per-model 分数范围。

**工作量**: 1h

---

### 7. 最终 top_k 固定偏小

**文件**: `backend/app/services/conversations.py:1105-1107`（`build_routed_retrieval_request`）

**问题**: 普通查询最终只返回 16 个 chunk：
```python
final_top_k = 24 if route_decision.visual_result_mode == "gallery" else (
    120 if route_decision.answer_policy.must_return_visual else 16
)
```

对于复杂问题（"总结整个知识库功能"），16 个 chunk 可能不够。

**修复方案**: 根据意图动态调整：
```python
if route_decision.visual_result_mode == "gallery":
    final_top_k = 24
elif route_decision.answer_policy.must_return_visual:
    final_top_k = 120
elif route_decision.intent in ("summarization", "comparison"):
    final_top_k = 24
else:
    final_top_k = 16
```

**工作量**: 0.5h

---

## P3 — 低优先级

### 8. 提示词缺乏 XML 结构化

**文件**: `backend/app/services/llm.py:242-273`

**问题**: 上下文直接拼接，无 XML 标签分隔，弱模型容易混淆指令和内容。

**修复方案**: 用 `<context id="N">` 包裹每条上下文，增强系统提示中的拒答约束（已在之前的修改中完成）。

**工作量**: 0.5h

---

## 修复优先级建议

| 优先级 | 修复项 | 预期收益 | 工作量 |
|--------|--------|----------|--------|
| **第一批** | #1 query heading 对齐 | 大幅提升语义匹配 | 0.5h |
| | #3 evidence gate 逐条过滤 | 减少低质量输入 | 0.5h |
| **第二批** | #2 启用 OpenSearch BM25 | 中文关键词召回 | 2-4h |
| | #5 向量相似度阈值 | 过滤噪声 | 0.5h |
| | #4 无 heading chunk 扩展 | 补充上下文 | 0.5h |
| **第三批** | #6 reranker 分数归一化 | 阈值更可靠 | 1h |
| | #7 动态 top_k | 复杂问题更准 | 0.5h |
| | #8 提示词 XML 化 | 已完成 | — |

> 先解决第一批（#1 + #3），召回质量应有明显改善。第二批需要 OpenSearch 部署配合。
