"""Tests for template recommendation service."""

import pytest

from backend.db.models import (
    Conversation,
    Message,
    MessageSql,
    RagQualityScore,
    TemplateRecommendation,
)
from sqlalchemy import select
from backend.services.template_recommender import (
    approve_recommendation,
    reject_recommendation,
    scan_template_candidates,
)


@pytest.mark.asyncio
async def test_scan_template_candidates(patch_db, seeded_db):
    ds = seeded_db["datasource"]
    async with patch_db() as session:
        conv = Conversation(datasource_id=ds.id, title="test")
        session.add(conv)
        await session.flush()

        msg = Message(conversation_id=conv.id, role="user", content="count users")
        session.add(msg)
        await session.flush()

        sql_rec = MessageSql(
            message_id=msg.id,
            sql_text="SELECT COUNT(*) FROM users",
            was_executed=True,
        )
        session.add(sql_rec)
        await session.flush()

        session.add(
            RagQualityScore(
                chunk_id=1,
                question="count users",
                score=0.85,
                session_id="sess-1",
            )
        )
        await session.commit()

        created = await scan_template_candidates(session)
        assert created == 1

        rec = await session.execute(
            select(TemplateRecommendation).where(
                TemplateRecommendation.message_sql_id == sql_rec.id
            )
        )
        recommendation = rec.scalar_one()
        assert recommendation.status == "pending"


@pytest.mark.asyncio
async def test_approve_and_reject_recommendation(patch_db, seeded_db):
    ds = seeded_db["datasource"]
    async with patch_db() as session:
        rec = TemplateRecommendation(
            datasource_id=ds.id,
            message_sql_id=1,
            question="q",
            sql_text="SELECT 1",
            quality_score=0.9,
            status="pending",
        )
        session.add(rec)
        await session.commit()
        await session.refresh(rec)

        tpl = await approve_recommendation(session, rec.id)
        assert tpl is not None
        assert tpl.question == "q"

        rec2 = TemplateRecommendation(
            datasource_id=ds.id,
            message_sql_id=2,
            question="q2",
            sql_text="SELECT 2",
            quality_score=0.9,
            status="pending",
        )
        session.add(rec2)
        await session.commit()
        await session.refresh(rec2)

        ok = await reject_recommendation(session, rec2.id)
        assert ok is True
        await session.refresh(rec2)
        assert rec2.status == "rejected"
