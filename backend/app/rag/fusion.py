from app.rag.retriever import Evidence

RRF_K = 60


def weighted_rrf_fusion(
    result_groups: dict[str, list[Evidence]],
    route_weights: dict[str, float],
    k: int = RRF_K,
) -> list[Evidence]:
    fused: dict[str, Evidence] = {}
    scores: dict[str, float] = {}
    for modality, evidences in result_groups.items():
        weight = route_weights.get(modality, 0.0)
        if weight <= 0:
            continue
        for rank, evidence in enumerate(evidences, start=1):
            current_score = scores.get(evidence.evidence_id, 0.0)
            scores[evidence.evidence_id] = current_score + weight * (1.0 / (k + rank))
            existing = fused.get(evidence.evidence_id)
            if existing is None or evidence_quality(evidence) > evidence_quality(existing):
                fused[evidence.evidence_id] = evidence

    results = []
    for evidence_id, evidence in fused.items():
        results.append(evidence.model_copy(update={"score": scores[evidence_id]}))
    return sorted(results, key=lambda item: item.score, reverse=True)


def evidence_quality(evidence: Evidence) -> tuple[float, int, int]:
    source_quality = sum(1 for value in evidence.source.values() if value not in (None, ""))
    raw_quality = len(evidence.raw)
    return evidence.score, source_quality, raw_quality
