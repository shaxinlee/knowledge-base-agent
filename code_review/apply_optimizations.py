#!/usr/bin/env python3
"""Apply the retrieval optimization patches described in optimization_plan.md."""
from __future__ import annotations

from pathlib import Path

REPO = Path("/root/workspace/knowledge-base-agent")


def patch(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"[FAIL] snippet not found in {path}:\n{old}")
    if text.count(old) > 1:
        raise SystemExit(f"[FAIL] snippet matches {text.count(old)} times in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"[OK] {path}")


# ---------- #1 retrieval.py: query heading alignment ----------
retrieval_py = REPO / "backend/app/services/retrieval.py"
patch(
    retrieval_py,
    "def search_vector_candidates(\n"
    "    *,\n"
    "    query: str,\n"
    "    knowledge_base_id: UUID,\n"
    "    limit: int,\n"
    "    embedding_client: EmbeddingClientProtocol,\n"
    "    vector_index_client: VectorIndexClientProtocol,\n"
    ") -> list[RetrievalCandidate]:\n"
    "    vectors = embedding_client.embed_texts([query])\n"
    "    if not vectors:\n"
    "        return []\n"
    "    hits = vector_index_client.search_points(\n"
    "        vector=vectors[0],\n"
    "        knowledge_base_id=str(knowledge_base_id),\n"
    "        limit=limit,\n"
    "    )\n",
    "def search_vector_candidates(\n"
    "    *,\n"
    "    query: str,\n"
    "    knowledge_base_id: UUID,\n"
    "    limit: int,\n"
    "    embedding_client: EmbeddingClientProtocol,\n"
    "    vector_index_client: VectorIndexClientProtocol,\n"
    ") -> list[RetrievalCandidate]:\n"
    "    enhanced_query = f\"检索知识库内容：{query}\"\n"
    "    vectors = embedding_client.embed_texts([enhanced_query])\n"
    "    if not vectors:\n"
    "        return []\n"
    "    hits = vector_index_client.search_points(\n"
    "        vector=vectors[0],\n"
    "        knowledge_base_id=str(knowledge_base_id),\n"
    "        limit=limit,\n"
    "    )\n",
)

# ---------- #2 retrieval.py: Postgres full-text Chinese note ----------
patch(
    retrieval_py,
    "def search_postgres_full_text(\n"
    "    db: Session,\n"
    "    *,\n"
    "    query: str,\n"
    "    knowledge_base_id: UUID,\n"
    "    limit: int,\n"
    ") -> list[RetrievalCandidate]:\n"
    "    ts_query = func.websearch_to_tsquery(\"simple\", query)\n",
    "def search_postgres_full_text(\n"
    "    db: Session,\n"
    "    *,\n"
    "    query: str,\n"
    "    knowledge_base_id: UUID,\n"
    "    limit: int,\n"
    ") -> list[RetrievalCandidate]:\n"
    "    # TODO(retrieval): Postgres `simple` dict does not segment Chinese — prefer\n"
    "    # OpenSearch + IK (`bm25_enabled=True`) for zh content. See optimization_plan.md #2.\n"
    "    ts_query = func.websearch_to_tsquery(\"simple\", query)\n",
)

# ---------- #3 conversations.py: evidence gate per-item filter ----------
conversations_py = REPO / "backend/app/services/conversations.py"
patch(
    conversations_py,
    "def apply_evidence_gate(\n"
    "    items: Sequence[RetrievalResultItem],\n"
    "    *,\n"
    "    route_decision: RouteDecision,\n"
    ") -> list[RetrievalResultItem]:\n"
    "    limit = 12 if route_decision.visual_result_mode == \"gallery\" else 6\n"
    "    contexts = list(items[:limit])\n"
    "    if not contexts:\n"
    "        return []\n"
    "    threshold = get_settings().evidence_min_reranker_score\n"
    "    if threshold is None:\n"
    "        return contexts\n"
    "    highest_score = max(item.score for item in contexts)\n"
    "    if highest_score < threshold:\n"
    "        return []\n"
    "    return contexts\n",
    "def apply_evidence_gate(\n"
    "    items: Sequence[RetrievalResultItem],\n"
    "    *,\n"
    "    route_decision: RouteDecision,\n"
    ") -> list[RetrievalResultItem]:\n"
    "    limit = 12 if route_decision.visual_result_mode == \"gallery\" else 6\n"
    "    contexts = list(items[:limit])\n"
    "    if not contexts:\n"
    "        return []\n"
    "    threshold = get_settings().evidence_min_reranker_score\n"
    "    if threshold is None:\n"
    "        return contexts\n"
    "    return [item for item in contexts if item.score >= threshold]\n",
)

# ---------- #4 conversations.py: heading-less chunk expansion ----------
patch(
    conversations_py,
    "def collect_section_chunks(\n"
    "    chunks: Sequence[ChunkMetadata],\n"
    "    *,\n"
    "    hit_chunk: ChunkMetadata,\n"
    ") -> list[ChunkMetadata]:\n"
    "    if not hit_chunk.heading_path:\n"
    "        return [hit_chunk]\n\n"
    "    hit_index = next(\n"
    "        (index for index, chunk in enumerate(chunks) if chunk.id == hit_chunk.id),\n"
    "        None,\n"
    "    )\n"
    "    if hit_index is None:\n"
    "        return [hit_chunk]\n",
    "def collect_section_chunks(\n"
    "    chunks: Sequence[ChunkMetadata],\n"
    "    *,\n"
    "    hit_chunk: ChunkMetadata,\n"
    ") -> list[ChunkMetadata]:\n"
    "    hit_index = next(\n"
    "        (index for index, chunk in enumerate(chunks) if chunk.id == hit_chunk.id),\n"
    "        None,\n"
    "    )\n"
    "    if hit_index is None:\n"
    "        return [hit_chunk]\n\n"
    "    if not hit_chunk.heading_path:\n"
    "        start_index = max(0, hit_index - 2)\n"
    "        end_index = min(len(chunks) - 1, hit_index + 2)\n"
    "        return list(chunks[start_index : end_index + 1])\n",
)

# ---------- #7 conversations.py: dynamic final_top_k by intent ----------
patch(
    conversations_py,
    "    final_top_k = 24 if route_decision.visual_result_mode == \"gallery\" else (\n"
    "        20 if route_decision.answer_policy.must_return_visual else 16\n"
    "    )\n",
    "    if route_decision.visual_result_mode == \"gallery\":\n"
    "        final_top_k = 24\n"
    "    elif route_decision.answer_policy.must_return_visual:\n"
    "        final_top_k = 20\n"
    "    elif route_decision.intent in (\"summarization\", \"comparison\"):\n"
    "        final_top_k = 24\n"
    "    else:\n"
    "        final_top_k = 16\n",
)

# ---------- #5 vector_index.py: score_threshold ----------
vector_index_py = REPO / "backend/app/services/vector_index.py"
patch(
    vector_index_py,
    "    def search_points(\n"
    "        self,\n"
    "        *,\n"
    "        vector: list[float],\n"
    "        knowledge_base_id: str,\n"
    "        limit: int,\n"
    "        modality: str | None = None,\n"
    "    ) -> list[VectorSearchHit]:\n"
    "        filters: list[dict[str, Any]] = [\n"
    "            {\n"
    "                \"key\": \"knowledge_base_id\",\n"
    "                \"match\": {\"value\": knowledge_base_id},\n"
    "            },\n"
    "            {\"key\": \"is_active\", \"match\": {\"value\": True}},\n"
    "        ]\n"
    "        if modality:\n"
    "            filters.append({\"key\": \"modality\", \"match\": {\"value\": modality}})\n"
    "        try:\n"
    "            response = httpx.post(\n"
    "                f\"{self.base_url}/collections/{self.collection_name}/points/search\",\n"
    "                json={\n"
    "                    \"vector\": vector,\n"
    "                    \"limit\": limit,\n"
    "                    \"with_payload\": True,\n"
    "                    \"filter\": {\"must\": filters},\n"
    "                },\n"
    "                timeout=self.timeout_seconds,\n"
    "            )\n",
    "    def search_points(\n"
    "        self,\n"
    "        *,\n"
    "        vector: list[float],\n"
    "        knowledge_base_id: str,\n"
    "        limit: int,\n"
    "        modality: str | None = None,\n"
    "        score_threshold: float | None = 0.5,\n"
    "    ) -> list[VectorSearchHit]:\n"
    "        filters: list[dict[str, Any]] = [\n"
    "            {\n"
    "                \"key\": \"knowledge_base_id\",\n"
    "                \"match\": {\"value\": knowledge_base_id},\n"
    "            },\n"
    "            {\"key\": \"is_active\", \"match\": {\"value\": True}},\n"
    "        ]\n"
    "        if modality:\n"
    "            filters.append({\"key\": \"modality\", \"match\": {\"value\": modality}})\n"
    "        search_body: dict[str, Any] = {\n"
    "            \"vector\": vector,\n"
    "            \"limit\": limit,\n"
    "            \"with_payload\": True,\n"
    "            \"filter\": {\"must\": filters},\n"
    "        }\n"
    "        if score_threshold is not None:\n"
    "            search_body[\"score_threshold\"] = score_threshold\n"
    "        try:\n"
    "            response = httpx.post(\n"
    "                f\"{self.base_url}/collections/{self.collection_name}/points/search\",\n"
    "                json=search_body,\n"
    "                timeout=self.timeout_seconds,\n"
    "            )\n",
)

patch(
    vector_index_py,
    "    def search_points(\n"
    "        self,\n"
    "        *,\n"
    "        vector: list[float],\n"
    "        knowledge_base_id: str,\n"
    "        limit: int,\n"
    "        modality: str | None = None,\n"
    "    ) -> list[VectorSearchHit]:\n"
    "        pass\n",
    "    def search_points(\n"
    "        self,\n"
    "        *,\n"
    "        vector: list[float],\n"
    "        knowledge_base_id: str,\n"
    "        limit: int,\n"
    "        modality: str | None = None,\n"
    "        score_threshold: float | None = 0.5,\n"
    "    ) -> list[VectorSearchHit]:\n"
    "        pass\n",
)

# ---------- #6 reranker.py: optional sigmoid normalization ----------
reranker_py = REPO / "backend/app/services/reranker.py"
patch(
    reranker_py,
    "def parse_reranker_scores(payload: Any, *, expected_count: int) -> list[float]:\n",
    "def sigmoid_normalize(scores: list[float]) -> list[float]:\n"
    "    \"\"\"Map raw reranker scores into (0, 1) via sigmoid 1/(1+e^-s).\n\n"
    "    Enable `evidence_normalize_reranker_scores` when the reranker emits\n"
    "    unbounded logits so that `evidence_min_reranker_score` reads as a\n"
    "    [0, 1] probability. Keep it disabled for rerankers whose raw output\n"
    "    is already in [0, 1] (e.g. BGE cross-encoder default).\n"
    "    \"\"\"\n"
    "    import math\n\n"
    "    return [1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, s)))) for s in scores]\n\n\n"
    "def parse_reranker_scores(payload: Any, *, expected_count: int) -> list[float]:\n",
)

# RerankerClient.rerank (the vLLM/standard path) — unique context: next line is `_build_vllm_score_request`.
patch(
    reranker_py,
    "        scores = parse_reranker_scores(response.json(), expected_count=len(documents))\n"
    "        return scores\n\n"
    "    def _build_vllm_score_request(\n",
    "        scores = parse_reranker_scores(response.json(), expected_count=len(documents))\n"
    "        if get_settings().evidence_normalize_reranker_scores:\n"
    "            scores = sigmoid_normalize(scores)\n"
    "        return scores\n\n"
    "    def _build_vllm_score_request(\n",
)

# DashScopeTextRerankerClient.rerank — unique context: next blank then `class LocalDemoRerankerClient`.
patch(
    reranker_py,
    "        scores = parse_reranker_scores(response.json(), expected_count=len(documents))\n"
    "        return scores\n\n\n"
    "class LocalDemoRerankerClient:\n",
    "        scores = parse_reranker_scores(response.json(), expected_count=len(documents))\n"
    "        if get_settings().evidence_normalize_reranker_scores:\n"
    "            scores = sigmoid_normalize(scores)\n"
    "        return scores\n\n\n"
    "class LocalDemoRerankerClient:\n",
)

# ---------- config.py: add normalize flag ----------
config_py = REPO / "backend/app/core/config.py"
patch(
    config_py,
    "    evidence_min_reranker_score: float | None = 0.35\n",
    "    evidence_min_reranker_score: float | None = 0.35\n"
    "    evidence_normalize_reranker_scores: bool = False\n",
)

print("All patches applied.")
