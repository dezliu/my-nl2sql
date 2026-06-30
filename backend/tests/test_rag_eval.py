"""Unit tests for offline RAG evaluation metrics."""

from backend.eval.rag_eval import (
    compute_metrics,
    is_chunk_relevant_weak,
    resolve_match_mode,
)
from backend.rag.retriever import RetrievedChunk


def _chunk(
    chunk_id: str,
    content: str = "",
    *,
    table_name: str | None = None,
) -> RetrievedChunk:
    metadata = {"table_name": table_name} if table_name else {}
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        score=0.9,
        doc_type="table_metadata",
        metadata=metadata,
    )


def test_resolve_match_mode_prefers_chunk_ids():
    class Case:
        expected_chunk_ids = [1, 2]
        expected_tables = ["users"]

    assert resolve_match_mode(Case()) == "chunk"


def test_resolve_match_mode_table_fallback():
    class Case:
        expected_chunk_ids = None
        expected_tables = ["users"]

    assert resolve_match_mode(Case()) == "table"


def test_resolve_match_mode_none():
    class Case:
        expected_chunk_ids = None
        expected_tables = None

    assert resolve_match_mode(Case()) is None


def test_is_chunk_relevant_weak_by_metadata():
    chunk = _chunk("1", table_name="users")
    assert is_chunk_relevant_weak(chunk, ["users"]) is True
    assert is_chunk_relevant_weak(chunk, ["orders"]) is False


def test_is_chunk_relevant_weak_by_content_prefix():
    chunk = _chunk("2", content="Table: orders\nColumns:\n")
    assert is_chunk_relevant_weak(chunk, ["orders"]) is True


def test_compute_metrics_strict_recall_and_mrr():
    retrieved = [
        _chunk("10"),
        _chunk("2"),
        _chunk("3"),
    ]
    recall, mrr, retrieved_ids, hit_ids = compute_metrics(
        retrieved,
        match_mode="chunk",
        gold_chunk_ids={"1", "2", "3"},
        expected_tables=[],
    )
    assert recall == 2 / 3
    assert mrr == 0.5
    assert retrieved_ids == ["10", "2", "3"]
    assert hit_ids == ["2", "3"]


def test_compute_metrics_strict_no_hit():
    recall, mrr, _, hit_ids = compute_metrics(
        [_chunk("99")],
        match_mode="chunk",
        gold_chunk_ids={"1"},
        expected_tables=[],
    )
    assert recall == 0.0
    assert mrr == 0.0
    assert hit_ids == []


def test_compute_metrics_table_mode_with_gold_from_db():
    retrieved = [
        _chunk("a", content="noise"),
        _chunk("b", table_name="users"),
    ]
    recall, mrr, _, hit_ids = compute_metrics(
        retrieved,
        match_mode="table",
        gold_chunk_ids={"b"},
        expected_tables=["users"],
    )
    assert recall == 1.0
    assert mrr == 0.5
    assert hit_ids == ["b"]


def test_compute_metrics_table_mode_without_gold_uses_table_coverage():
    retrieved = [
        _chunk("1", table_name="users"),
        _chunk("2", table_name="orders"),
    ]
    recall, mrr, _, _ = compute_metrics(
        retrieved,
        match_mode="table",
        gold_chunk_ids=set(),
        expected_tables=["users", "orders"],
    )
    assert recall == 1.0
    assert mrr == 1.0
