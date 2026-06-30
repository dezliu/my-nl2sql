"""Template recommendation from high-quality executed SQL."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    Conversation,
    Message,
    MessageSql,
    RagQualityScore,
    SqlTemplate,
    TemplateRecommendation,
)

MIN_QUALITY_SCORE = 0.8


async def scan_template_candidates(session: AsyncSession) -> int:
    """Find executed SQL with quality score >= 0.8 and create pending recommendations."""
    subq = (
        select(
            MessageSql.id.label("message_sql_id"),
            Message.content.label("question"),
            MessageSql.sql_text,
            Conversation.datasource_id,
            func.max(RagQualityScore.score).label("max_score"),
        )
        .join(Message, MessageSql.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(RagQualityScore, RagQualityScore.question == Message.content)
        .where(MessageSql.was_executed.is_(True))
        .group_by(
            MessageSql.id,
            Message.content,
            MessageSql.sql_text,
            Conversation.datasource_id,
        )
        .having(func.max(RagQualityScore.score) >= MIN_QUALITY_SCORE)
    )

    result = await session.execute(subq)
    created = 0

    for row in result.all():
        existing = await session.execute(
            select(TemplateRecommendation).where(
                TemplateRecommendation.message_sql_id == row.message_sql_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        rec = TemplateRecommendation(
            datasource_id=row.datasource_id,
            message_sql_id=row.message_sql_id,
            question=row.question,
            sql_text=row.sql_text,
            quality_score=float(row.max_score),
            status="pending",
        )
        session.add(rec)
        created += 1

    if created:
        await session.commit()
    return created


async def approve_recommendation(session: AsyncSession, rec_id: int) -> SqlTemplate | None:
    rec = await session.get(TemplateRecommendation, rec_id)
    if not rec or rec.status != "pending":
        return None

    template = SqlTemplate(
        datasource_id=rec.datasource_id,
        question=rec.question,
        sql_text=rec.sql_text,
        description=f"Auto-recommended (score={rec.quality_score:.2f})",
    )
    session.add(template)
    rec.status = "approved"
    await session.commit()
    await session.refresh(template)
    return template


async def reject_recommendation(session: AsyncSession, rec_id: int) -> bool:
    rec = await session.get(TemplateRecommendation, rec_id)
    if not rec or rec.status != "pending":
        return False
    rec.status = "rejected"
    await session.commit()
    return True
