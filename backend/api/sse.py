"""SSE streaming endpoints for ask workflow."""

import asyncio
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.session_manager import make_queue_emitter, run_workflow, sse_event_generator
from backend.db.session import async_session_factory

router = APIRouter(prefix="/api", tags=["sse"])


class AskStreamRequest(BaseModel):
    question: str
    datasource_id: int
    deep_think: bool = False
    execution_mode: str = Field(default="AUTO")


@router.post("/ask/stream")
async def ask_stream(body: AskStreamRequest) -> StreamingResponse:
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    emitter = make_queue_emitter(queue)

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
            await emitter("STATUS", {"message": "已连接，开始处理…", "phase": "connected"})
            async with async_session_factory() as db_session:
                await run_workflow(session_id, initial_state, db_session, event_emitter=emitter)
        except Exception as e:
            await emitter("ERROR", {"message": str(e)})
            await emitter("DONE", {"session_id": session_id})
        finally:
            await queue.put(None)

    asyncio.create_task(_run())

    return StreamingResponse(
        sse_event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
