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

    body = await response.aread()
    text = body.decode("utf-8")
    assert "event: INTENT" in text
    assert "event: LLM_TOKEN" in text
    assert "event: DONE" in text
    assert "测试" in text


@pytest.mark.asyncio
async def test_sse_invalid_body_rejected(client):
    response = await client.post("/api/ask/stream", json={"question": "only question"})
    assert response.status_code == 422
