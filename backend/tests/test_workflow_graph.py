"""Tests that LangGraph workflow compiles and registers valid nodes."""

from unittest.mock import MagicMock

from backend.graph.workflow import build_graph, route_after_sql_generate


def test_build_graph_compiles():
    session = MagicMock()
    graph = build_graph(session)
    assert graph is not None


def test_graph_has_sql_generate_conditional_edges():
    session = MagicMock()
    graph = build_graph(session)
    drawable = graph.get_graph()
    edge_labels = {
        (e.source, e.target): getattr(e, "data", None) for e in drawable.edges
    }
    assert route_after_sql_generate({"cannot_answer": True}) == "finalize"
    assert any(
        src == "sql_generate" and tgt == "finalize" for src, tgt in edge_labels
    )
    assert any(
        src == "sql_generate" and tgt == "sql_safety" for src, tgt in edge_labels
    )
