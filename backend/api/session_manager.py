"""Session manager for streaming ask workflow."""

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from backend.graph.workflow import GraphState, build_graph

EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class AskSession:
    session_id: str
    question: str = ""
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: bool = False


_sessions: dict[str, AskSession] = {}


def get_session(session_id: str) -> AskSession | None:
    return _sessions.get(session_id)


def create_session(session_id: str, question: str = "") -> AskSession:
    session = AskSession(session_id=session_id, question=question)
    _sessions[session_id] = session
    return session


async def push_event(session_id: str, event_type: str, data: dict[str, Any]) -> None:
    ask_session = _sessions.get(session_id)
    if ask_session:
        await ask_session.events.put({"type": event_type, "data": data})


def make_queue_emitter(queue: asyncio.Queue) -> EventEmitter:
    async def emit(event_type: str, data: dict[str, Any]) -> None:
        await queue.put({"type": event_type, "data": data})

    return emit


async def run_workflow(
    session_id: str,
    initial_state: GraphState,
    db_session,
    event_emitter: EventEmitter | None = None,
) -> None:
    ask_session = _sessions.get(session_id)
    queue = ask_session.events if ask_session else None

    async def emit(event_type: str, data: dict[str, Any]) -> None:
        if event_emitter:
            await event_emitter(event_type, data)
        elif queue:
            await queue.put({"type": event_type, "data": data})

    initial_state["event_emitter"] = emit
    graph = build_graph(db_session, event_emitter=emit)
    try:
        async for event in graph.astream(initial_state, stream_mode="values"):
            events = event.get("stream_events", [])
            for e in events:
                await emit(e["type"], e.get("data", {}))
    except Exception as e:
        await emit("ERROR", {"message": str(e)})
    finally:
        if ask_session:
            ask_session.done = True
            await ask_session.events.put(None)


async def stream_events(session_id: str) -> AsyncGenerator[dict, None]:
    ask_session = _sessions.get(session_id)
    if not ask_session:
        return
    while True:
        event = await ask_session.events.get()
        if event is None:
            break
        yield event


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def sse_event_generator(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    while True:
        event = await queue.get()
        if event is None:
            break
        yield format_sse_event(event["type"], event.get("data", {}))
