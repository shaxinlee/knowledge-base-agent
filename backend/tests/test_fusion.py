from app.rag.fusion import weighted_rrf_fusion
from app.rag.retriever import Evidence


def _evidence(
    evidence_id: str,
    modality: str,
    *,
    score: float = 0.5,
    source: dict[str, object] | None = None,
    raw: dict[str, object] | None = None,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        modality=modality,  # type: ignore[arg-type]
        content=f"{modality} content",
        score=score,
        source=source or {"file_name": f"{modality}.txt"},
        raw=raw or {},
    )


def test_weighted_rrf_prefers_enabled_modality_weight() -> None:
    fused = weighted_rrf_fusion(
        result_groups={
            "text": [_evidence("text-1", "text")],
            "image": [_evidence("image-1", "image")],
        },
        route_weights={"text": 0.1, "image": 2.0},
    )

    assert [item.evidence_id for item in fused] == ["image-1", "text-1"]


def test_weighted_rrf_merges_duplicate_evidence_scores() -> None:
    fused = weighted_rrf_fusion(
        result_groups={
            "text": [_evidence("shared", "text"), _evidence("text-2", "text")],
            "image": [_evidence("image-1", "image"), _evidence("shared", "image")],
        },
        route_weights={"text": 1.0, "image": 1.0},
    )

    shared = next(item for item in fused if item.evidence_id == "shared")
    assert fused[0].evidence_id == "shared"
    assert shared.score == (1 / 61) + (1 / 62)


def test_weighted_rrf_skips_disabled_or_missing_route_weights() -> None:
    fused = weighted_rrf_fusion(
        result_groups={
            "text": [_evidence("text-1", "text")],
            "metadata": [_evidence("metadata-1", "metadata")],
            "image": [_evidence("image-1", "image")],
        },
        route_weights={"text": 1.0, "image": 0.0},
    )

    assert [item.evidence_id for item in fused] == ["text-1"]


def test_weighted_rrf_preserves_richer_duplicate_source() -> None:
    fused = weighted_rrf_fusion(
        result_groups={
            "text": [
                _evidence("shared", "text", source={"file_name": "doc.pdf"}, raw={}),
            ],
            "image": [
                _evidence(
                    "shared",
                    "image",
                    source={
                        "doc_id": "doc-1",
                        "file_name": "doc.pdf",
                        "page": 3,
                        "image_path": "assets/img.png",
                        "caption": "架构图",
                        "ocr_text": "API -> DB",
                    },
                    raw={"image_id": "shared"},
                ),
            ],
        },
        route_weights={"text": 1.0, "image": 1.0},
    )

    assert fused[0].source["image_path"] == "assets/img.png"
    assert fused[0].raw["image_id"] == "shared"
