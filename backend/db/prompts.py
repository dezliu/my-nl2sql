"""System prompt loading and management."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import PromptRole, SystemPrompt

DEFAULT_PROMPTS: dict[str, str] = {
    PromptRole.INTENT_CLASSIFIER.value: """You are an intent classifier for an NL2SQL system.
Classify the user question into one of: query_data, explain_schema, chitchat, reject.
Respond with JSON: {{"intent": "<category>", "confidence": 0.0-1.0}}

Question: {question}""",
    PromptRole.RAG_ROUTER.value: """Determine if RAG retrieval is needed for this question.
RAG is needed when the question requires schema knowledge, SQL templates, or business terms.
Respond with JSON: {{"need_rag": true/false, "reason": "..."}}

Intent: {intent}
Question: {question}""",
    PromptRole.QUERY_EXPANDER.value: """Expand the user question to improve retrieval recall.
Add synonyms, business terms, and related table/column names.
Respond with the expanded question only.

Question: {question}
Intent: {intent}""",
    PromptRole.RETRIEVAL_JUDGE.value: """Judge if retrieved chunks are sufficient to answer the question.
Respond with JSON: {{"decision": "sufficient" or "continue", "reason": "..."}}

Question: {question}
Retrieved chunks:
{chunks}
Loop count: {loop_count}""",
    PromptRole.SQL_GENERATOR.value: """You are an expert SQL generator. Generate MySQL SELECT only.
Use the schema context and retrieved examples. Follow safety rules strictly.

Safety rules:
- SELECT only, no DDL/DML
- Use tables from whitelist only
- Include LIMIT clause
- Use recommended JOIN paths when joining tables

Question: {question}
Schema context:
{schema_context}

Retrieved examples:
{chunks}

Safety rules: {safety_rules}

Respond with JSON: {{"sql": "...", "explanation": "..."}}""",
    PromptRole.REACT_REASONER.value: """You are a SQL expert using ReAct reasoning.
Think step by step: Thought -> Action -> Observation.
Available actions: query_schema, validate_sql, execute_sql.
Generate correct MySQL SELECT queries.

Question: {question}
Schema context:
{schema_context}
Retrieved examples:
{chunks}
Safety rules: {safety_rules}""",
    PromptRole.SQL_SAFETY.value: """Validate the SQL against safety rules.
Respond with JSON: {{"valid": true/false, "errors": [...]}}

SQL: {sql}
Allowed tables: {allowed_tables}""",
    PromptRole.RESULT_SUMMARIZER.value: """Summarize SQL query results in natural language for the user.

Question: {question}
SQL: {sql}
Result preview: {result_preview}""",
    PromptRole.RAG_SCORER.value: """Score the relevance of a retrieved chunk to the user question.
Score from 0.0 (irrelevant) to 1.0 (highly relevant).
Respond with JSON: {{"score": 0.0-1.0, "reason": "..."}}

Question: {question}
Chunk: {chunk}""",
}


async def load_active_prompts(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        select(SystemPrompt).where(SystemPrompt.is_active.is_(True))
    )
    prompts = {p.role: p.content for p in result.scalars().all()}
    for role, default in DEFAULT_PROMPTS.items():
        if role not in prompts:
            prompts[role] = default
    return prompts


async def seed_default_prompts(session: AsyncSession) -> None:
    for role, content in DEFAULT_PROMPTS.items():
        existing = await session.execute(
            select(SystemPrompt).where(SystemPrompt.role == role, SystemPrompt.is_active.is_(True))
        )
        if existing.scalar_one_or_none():
            continue
        prompt = SystemPrompt(role=role, version=1, content=content, is_active=True)
        session.add(prompt)
    await session.commit()


async def create_prompt_version(
    session: AsyncSession, role: str, content: str, activate: bool = True
) -> SystemPrompt:
    result = await session.execute(
        select(SystemPrompt.version)
        .where(SystemPrompt.role == role)
        .order_by(SystemPrompt.version.desc())
        .limit(1)
    )
    max_version = result.scalar_one_or_none() or 0
    if activate:
        await session.execute(
            update(SystemPrompt).where(SystemPrompt.role == role).values(is_active=False)
        )
    prompt = SystemPrompt(
        role=role,
        version=max_version + 1,
        content=content,
        is_active=activate,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return prompt


async def get_prompt_versions(session: AsyncSession, role: str) -> list[SystemPrompt]:
    result = await session.execute(
        select(SystemPrompt)
        .where(SystemPrompt.role == role)
        .order_by(SystemPrompt.version.desc())
    )
    return list(result.scalars().all())


async def activate_prompt_version(session: AsyncSession, prompt_id: int) -> SystemPrompt | None:
    prompt = await session.get(SystemPrompt, prompt_id)
    if not prompt:
        return None
    await session.execute(
        update(SystemPrompt).where(SystemPrompt.role == prompt.role).values(is_active=False)
    )
    prompt.is_active = True
    await session.commit()
    await session.refresh(prompt)
    return prompt
