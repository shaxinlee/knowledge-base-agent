from app.rag.query_router import RuleBasedQueryRouter
from app.rag.retriever import Evidence, ImageBlock, MultimodalRetriever, image_block_to_evidence


def _evidence(evidence_id: str, modality: str, score: float = 0.5) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        modality=modality,  # type: ignore[arg-type]
        content=f"{modality} content",
        score=score,
        source={"file_name": f"{modality}.txt"},
        raw={},
    )


def test_multimodal_retriever_does_not_call_disabled_image_route() -> None:
    calls: list[str] = []

    def text_retriever(_query: str, _top_k: int) -> list[Evidence]:
        calls.append("text")
        return [_evidence("text-1", "text")]

    def table_retriever(_query: str, _top_k: int) -> list[Evidence]:
        calls.append("table")
        return [_evidence("table-1", "table")]

    def image_retriever(_query: str, _top_k: int) -> list[Evidence]:
        calls.append("image")
        return [_evidence("image-1", "image")]

    decision = RuleBasedQueryRouter().route("交付日期是什么？")
    retriever = MultimodalRetriever(
        text_retriever=text_retriever,
        table_retriever=table_retriever,
        image_retriever=image_retriever,
    )

    retriever.retrieve(query=decision.query, route_decision=decision)

    assert calls == ["text", "table"]


def test_multimodal_retriever_calls_enabled_modalities_only() -> None:
    calls: list[tuple[str, int]] = []

    def make_retriever(modality: str) -> object:
        def retrieve(_query: str, top_k: int) -> list[Evidence]:
            calls.append((modality, top_k))
            return [_evidence(f"{modality}-1", modality)]

        return retrieve

    decision = RuleBasedQueryRouter().route("哪些文件提到了验收日期？")
    retriever = MultimodalRetriever(
        text_retriever=make_retriever("text"),  # type: ignore[arg-type]
        table_retriever=make_retriever("table"),  # type: ignore[arg-type]
        image_retriever=make_retriever("image"),  # type: ignore[arg-type]
        metadata_retriever=make_retriever("metadata"),  # type: ignore[arg-type]
    )

    results = retriever.retrieve(query=decision.query, route_decision=decision)

    assert calls == [("text", 30), ("table", 30), ("metadata", 10)]
    assert {result.modality for result in results} == {"text", "table", "metadata"}


def test_multimodal_retriever_fuses_results_with_weighted_rrf() -> None:
    decision = RuleBasedQueryRouter().route("找一下支付系统架构图")
    retriever = MultimodalRetriever(
        text_retriever=lambda _query, _top_k: [_evidence("shared", "text")],
        image_retriever=lambda _query, _top_k: [
            _evidence("image-1", "image"),
            _evidence("shared", "image"),
        ],
    )

    results = retriever.retrieve(query=decision.query, route_decision=decision)

    assert results[0].evidence_id == "shared"
    assert results[0].score > results[1].score


def test_image_block_to_evidence_contains_required_source_fields() -> None:
    image_block = ImageBlock(
        image_id="image-1",
        doc_id="doc-1",
        file_name="architecture.pdf",
        page=12,
        image_path="assets/image-1.png",
        caption="系统架构图",
        ocr_text="Frontend -> Backend -> Qdrant",
        surrounding_text="本节说明系统总体架构。",
        metadata={"section_path": "设计 > 架构"},
    )

    evidence = image_block_to_evidence(image_block, score=0.8)

    assert evidence.evidence_id == "image-1"
    assert evidence.modality == "image"
    assert evidence.source["file_name"] == "architecture.pdf"
    assert evidence.source["page"] == 12
    assert evidence.source["image_path"] == "assets/image-1.png"
    assert evidence.source["caption"] == "系统架构图"
    assert evidence.source["ocr_text"] == "Frontend -> Backend -> Qdrant"
    assert "系统架构图" in evidence.content
    assert "设计 > 架构" in evidence.content
