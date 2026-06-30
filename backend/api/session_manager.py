"""Session manager for streaming ask workflow with pause/resume."""

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.graph.workflow import GraphState, build_graph, clear_workflow_session_cache

EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]

SessionStatus = Literal["running", "paused", "done", "error"]


@dataclass
class AskSession:
    session_id: str
    question: str = ""
    datasource_id: int = 0
    deep_think: bool = False
    execution_mode: str = "AUTO"
    status: SessionStatus = "running"
    cancelled: bool = False
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: bool = False


_sessions: dict[str, AskSession] = {}


def get_session(session_id: str) -> AskSession | None:
    return _sessions.get(session_id)


def register_session(
    session_id: str,
    *,
    question: str,
    datasource_id: int,
    deep_think: bool,
    execution_mode: str,
    queue: asyncio.Queue | None = None,
) -> AskSession:
    session = AskSession(
        session_id=session_id,
        question=question,
        datasource_id=datasource_id,
        deep_think=deep_think,
        execution_mode=execution_mode,
        events=queue or asyncio.Queue(),
        status="running",
        cancelled=False,
        done=False,
    )
    _sessions[session_id] = session
    return session


def create_session(session_id: str, question: str = "") -> AskSession:
    return register_session(
        session_id,
        question=question,
        datasource_id=0,
        deep_think=False,
        execution_mode="AUTO",
    )


def request_stop(session_id: str) -> bool:
    ask_session = _sessions.get(session_id)
    if ask_session and ask_session.status == "running":
        ask_session.cancelled = True
        return True
    return False


def get_paused_session(session_id: str) -> AskSession | None:
    ask_session = _sessions.get(session_id)
    if ask_session and ask_session.status == "paused":
        return ask_session
    return None


async def push_event(session_id: str, event_type: str, data: dict[str, Any]) -> None:
    ask_session = _sessions.get(session_id)
    if ask_session:
        await ask_session.events.put({"type": event_type, "data": data})


def make_queue_emitter(queue: asyncio.Queue) -> EventEmitter:
    async def emit(event_type: str, data: dict[str, Any]) -> None:
        await queue.put({"type": event_type, "data": data})

    return emit


async def _finish_stream(
    ask_session: AskSession | None,
    event_emitter: EventEmitter | None,
    session_id: str,
    *,
    terminal: bool,
) -> None:
    if terminal and event_emitter:
        await event_emitter("DONE", {"session_id": session_id})
    if ask_session:
        if terminal:
            ask_session.done = True
            clear_workflow_session_cache(session_id)
        if ask_session.events:
            await ask_session.events.put(None)


async def run_workflow(
    session_id: str,
    initial_state: GraphState,
    db_session,
    event_emitter: EventEmitter | None = None,
    *,
    resume: bool = False,
) -> None:
    ask_session = _sessions.get(session_id)
    queue = ask_session.events if ask_session else None

    async def emit(event_type: str, data: dict[str, Any]) -> None:
        if event_emitter:
            await event_emitter(event_type, data)
        elif queue:
            await queue.put({"type": event_type, "data": data})

    if ask_session:
        ask_session.status = "running"
        ask_session.cancelled = False

    config = {"configurable": {"thread_id": session_id}}
    graph_input: GraphState | None = None if resume else initial_state

    try:
        graph = build_graph(db_session, event_emitter=emit)
        async for event in graph.astream(graph_input, config, stream_mode="values"):
            stream_events = event.get("stream_events", [])
            for e in stream_events:
                await emit(e["type"], e.get("data", {}))
            if ask_session and ask_session.cancelled:
                ask_session.status = "paused"
                await emit("PAUSED", {"session_id": session_id, "message": "已暂停，可继续生成"})
                await _finish_stream(ask_session, event_emitter, session_id, terminal=False)
                return
        if ask_session:
            ask_session.status = "done"
    except Exception as e:
        if ask_session:
            ask_session.status = "error"
        await emit("ERROR", {"message": str(e)})
    finally:
        if ask_session and ask_session.status in ("done", "error"):
            await _finish_stream(ask_session, event_emitter, session_id, terminal=True)


async def resume_workflow(
    session_id: str,
    db_session,
    event_emitter: EventEmitter,
) -> None:
    ask_session = get_paused_session(session_id)
    if not ask_session:
        raise ValueError("Session is not paused or does not exist")
    await run_workflow(
        session_id,
        {},
        db_session,
        event_emitter=event_emitter,
        resume=True,
    )


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
