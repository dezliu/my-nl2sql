"""Tests for SSE streaming endpoint (workflow mocked, no LLM)."""

import pytest


@pytest.mark.asyncio
async def test_sse_ask_stream_events(client, seeded_db, mock_run_workflow):
    ds_id = seeded_db["datasource"].id
    response = await client.post(
        "/api/ask/stream",
        json={
            "question": "查询用户数",
            "datasource_id": ds_id,
            "deep_think": False,
            "execution_mode": "GENERATE_ONLY",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("x-session-id")

    body = await response.aread()
    text = body.decode("utf-8")
    assert "event: INTENT" in text
    assert "event: LLM_TOKEN" in text
    assert "event: DONE" in text
    assert "测试" in text


@pytest.mark.asyncio
async def test_sse_stop_unknown_session(client):
    response = await client.post(
        "/api/ask/stop",
        json={"session_id": "nonexistent"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sse_stop_and_resume(client, seeded_db, mock_run_workflow):
    ds_id = seeded_db["datasource"].id
    from backend.api.session_manager import get_session, register_session

    session_id = "test-pause-session"
    register_session(
        session_id,
        question="q",
        datasource_id=ds_id,
        deep_think=False,
        execution_mode="AUTO",
    )
    sess = get_session(session_id)
    assert sess is not None
    sess.status = "paused"

    response = await client.post("/api/ask/resume", json={"session_id": session_id})
    assert response.status_code == 200
    assert response.headers.get("x-session-id") == session_id


@pytest.mark.asyncio
async def test_sse_invalid_body_rejected(client):
    response = await client.post("/api/ask/stream", json={"question": "only question"})
    assert response.status_code == 422
