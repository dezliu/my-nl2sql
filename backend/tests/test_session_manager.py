"""Tests for session pause/stop/resume."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.session_manager import (
    AskSession,
    register_session,
    request_stop,
    run_workflow,
)


@pytest.mark.asyncio
async def test_request_stop_sets_cancelled():
    queue: asyncio.Queue = asyncio.Queue()
    register_session(
        "sess-1",
        question="q",
        datasource_id=1,
        deep_think=False,
        execution_mode="AUTO",
        queue=queue,
    )
    assert request_stop("sess-1") is True

    from backend.api.session_manager import get_session

    session = get_session("sess-1")
    assert session is not None
    assert session.cancelled is True


@pytest.mark.asyncio
async def test_run_workflow_emits_paused_on_cancel():
    events: list[tuple[str, dict]] = []

    async def emitter(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    register_session(
        "sess-pause",
        question="test",
        datasource_id=1,
        deep_think=False,
        execution_mode="AUTO",
    )

    async def fake_astream(input_state, config, stream_mode="values"):
        yield {
            "stream_events": [{"type": "INTENT", "data": {"intent": "query_data"}}],
            "session_id": "sess-pause",
        }
        from backend.api.session_manager import get_session

        sess = get_session("sess-pause")
        assert sess is not None
        sess.cancelled = True
        yield {
            "stream_events": [{"type": "STATUS", "data": {"message": "next"}}],
            "session_id": "sess-pause",
        }

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with patch("backend.api.session_manager.build_graph", return_value=mock_graph):
        await run_workflow(
            "sess-pause",
            {"session_id": "sess-pause", "question": "test", "datasource_id": 1},
            MagicMock(),
            event_emitter=emitter,
        )

    event_types = [e[0] for e in events]
    assert "INTENT" in event_types
    assert "PAUSED" in event_types
    assert "DONE" not in event_types

    from backend.api.session_manager import get_paused_session

    assert get_paused_session("sess-pause") is not None


@pytest.mark.asyncio
async def test_run_workflow_emits_done_on_completion():
    events: list[tuple[str, dict]] = []

    async def emitter(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    register_session(
        "sess-done",
        question="test",
        datasource_id=1,
        deep_think=False,
        execution_mode="AUTO",
    )

    async def fake_astream(input_state, config, stream_mode="values"):
        yield {"stream_events": [], "session_id": "sess-done"}

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with patch("backend.api.session_manager.build_graph", return_value=mock_graph):
        await run_workflow(
            "sess-done",
            {"session_id": "sess-done", "question": "test", "datasource_id": 1},
            MagicMock(),
            event_emitter=emitter,
        )

    assert ("DONE", {"session_id": "sess-done"}) in events

    from backend.api.session_manager import get_session

    sess = get_session("sess-done")
    assert sess is not None
    assert sess.status == "done"
