"""Session manager for streaming ask workflow."""

import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator

from backend.graph.workflow import GraphState, build_graph


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


async def run_workflow(session_id: str, initial_state: GraphState, db_session) -> None:
    ask_session = _sessions.get(session_id)
    if not ask_session:
        return

    graph = build_graph(db_session)
    try:
        async for event in graph.astream(initial_state, stream_mode="values"):
            events = event.get("stream_events", [])
            for e in events:
                await ask_session.events.put(e)
    except Exception as e:
        await ask_session.events.put({"type": "ERROR", "data": {"message": str(e)}})
    finally:
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
