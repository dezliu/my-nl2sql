"""Tests for session manager SSE helpers."""

import asyncio
import json

import pytest

from backend.api.session_manager import (
    format_sse_event,
    make_queue_emitter,
    sse_event_generator,
)


@pytest.mark.asyncio
async def test_format_sse_event():
    out = format_sse_event("INTENT", {"intent": "query_data"})
    assert out.startswith("event: INTENT\n")
    payload = json.loads(out.split("data: ", 1)[1].strip())
    assert payload["intent"] == "query_data"


@pytest.mark.asyncio
async def test_sse_event_generator():
    queue: asyncio.Queue = asyncio.Queue()
    emitter = make_queue_emitter(queue)

    async def produce():
        await emitter("STATUS", {"message": "ok"})
        await queue.put(None)

    asyncio.create_task(produce())

    events: list[str] = []
    async for chunk in sse_event_generator(queue):
        events.append(chunk)

    assert len(events) == 1
    assert "event: STATUS" in events[0]
