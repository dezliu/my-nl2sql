"""Celery workers for async RAG scoring and alerts."""

from celery import Celery

from backend.config import settings

celery_app = Celery(
    "nl2sql",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="score_rag_chunks")
def score_rag_chunks(question: str, chunks: list[dict], session_id: str | None = None) -> dict:
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        _score_rag_chunks_async(question, chunks, session_id)
    )


async def _score_rag_chunks_async(
    question: str, chunks: list[dict], session_id: str | None = None
) -> dict:
    import json
    import re

    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI
    from sqlalchemy import select

    from backend.config import settings
    from backend.db.models import RagAlert, RagQualityScore
    from backend.db.prompts import load_active_prompts
    from backend.db.session import async_session_factory

    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key or "sk-placeholder")
    scored = 0
    alerts = 0

    async with async_session_factory() as session:
        prompts = await load_active_prompts(session)
        scorer_prompt = prompts.get("rag_scorer", "")

        for chunk in chunks:
            chunk_id = int(chunk.get("chunk_id", 0))
            if not chunk_id:
                continue

            prompt = scorer_prompt.format(question=question, chunk=chunk.get("content", ""))
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            match = re.search(r"\{.*\}", str(response.content), re.DOTALL)
            score = 0.5
            if match:
                try:
                    score = float(json.loads(match.group()).get("score", 0.5))
                except (json.JSONDecodeError, ValueError):
                    pass

            score_record = RagQualityScore(
                chunk_id=chunk_id,
                question=question,
                score=score,
                session_id=session_id,
            )
            session.add(score_record)
            scored += 1

            if score < settings.rag_alert_threshold:
                alert = RagAlert(
                    chunk_id=chunk_id,
                    question=question,
                    score=score,
                )
                session.add(alert)
                alerts += 1

        await session.commit()

    return {"scored": scored, "alerts": alerts}


@celery_app.task(name="scan_template_candidates")
def scan_template_candidates() -> dict:
    import asyncio

    return asyncio.get_event_loop().run_until_complete(_scan_template_candidates_async())


async def _scan_template_candidates_async() -> dict:
    from backend.db.session import async_session_factory
    from backend.services.template_recommender import scan_template_candidates

    async with async_session_factory() as session:
        created = await scan_template_candidates(session)
    return {"created": created}
