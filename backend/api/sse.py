"""SSE streaming endpoints for ask workflow."""

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.session_manager import (
    get_paused_session,
    make_queue_emitter,
    register_session,
    request_stop,
    resume_workflow,
    run_workflow,
    sse_event_generator,
)
from backend.db.session import async_session_factory

router = APIRouter(prefix="/api", tags=["sse"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class AskStreamRequest(BaseModel):
    question: str
    datasource_id: int
    deep_think: bool = False
    execution_mode: str = Field(default="AUTO")


class SessionIdRequest(BaseModel):
    session_id: str


def _streaming_response(queue: asyncio.Queue, session_id: str) -> StreamingResponse:
    return StreamingResponse(
        sse_event_generator(queue),
        media_type="text/event-stream",
        headers={**_SSE_HEADERS, "X-Session-Id": session_id},
    )


@router.post("/ask/stream")
async def ask_stream(body: AskStreamRequest) -> StreamingResponse:
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    emitter = make_queue_emitter(queue)

    register_session(
        session_id,
        question=body.question,
        datasource_id=body.datasource_id,
        deep_think=body.deep_think,
        execution_mode=body.execution_mode,
        queue=queue,
    )

    initial_state = {
        "session_id": session_id,
        "question": body.question,
        "deep_think": body.deep_think,
        "execution_mode": body.execution_mode,
        "datasource_id": body.datasource_id,
        "stream_events": [],
    }

    async def _run() -> None:
        try:
            await emitter(
                "STATUS",
                {
                    "message": "已连接，开始处理…",
                    "phase": "connected",
                    "session_id": session_id,
                },
            )
            async with async_session_factory() as db_session:
                await run_workflow(session_id, initial_state, db_session, event_emitter=emitter)
        except Exception as e:
            await emitter("ERROR", {"message": str(e)})
            await emitter("DONE", {"session_id": session_id})
        finally:
            await queue.put(None)

    asyncio.create_task(_run())

    return _streaming_response(queue, session_id)


@router.post("/ask/stop")
async def ask_stop(body: SessionIdRequest) -> dict:
    if not request_stop(body.session_id):
        raise HTTPException(status_code=404, detail="Session not found or not running")
    return {"ok": True, "session_id": body.session_id}


@router.post("/ask/resume")
async def ask_resume(body: SessionIdRequest) -> StreamingResponse:
    ask_session = get_paused_session(body.session_id)
    if not ask_session:
        raise HTTPException(status_code=404, detail="Session not paused or not found")

    queue: asyncio.Queue = asyncio.Queue()
    ask_session.events = queue
    ask_session.done = False
    emitter = make_queue_emitter(queue)

    async def _run() -> None:
        try:
            await emitter(
                "STATUS",
                {
                    "message": "继续生成…",
                    "phase": "resume",
                    "session_id": body.session_id,
                },
            )
            async with async_session_factory() as db_session:
                await resume_workflow(body.session_id, db_session, emitter)
        except Exception as e:
            await emitter("ERROR", {"message": str(e)})
            await emitter("DONE", {"session_id": body.session_id})
        finally:
            await queue.put(None)

    asyncio.create_task(_run())

    return _streaming_response(queue, body.session_id)
