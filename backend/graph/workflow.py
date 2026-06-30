"""LangGraph NL2SQL workflow."""

import json
import re
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.cache.llm_cache import LlmCache
from backend.db.models import ColumnMetadata, Datasource, FkRelationship, TableMetadata
from backend.db.prompts import ROLE_GUARDRAILS, USER_LANGUAGE_POLICY, load_active_prompts
from backend.llm.client import create_chat_llm
from backend.rag.retriever import HybridRetriever
from backend.sql.schema import SchemaGraph, SqlValidator, execute_sql

_CHECKPOINTER = MemorySaver()
_emitter_cache: dict[str, Any] = {}
_schema_graph_cache: dict[str, SchemaGraph] = {}


def get_workflow_checkpointer() -> MemorySaver:
    return _CHECKPOINTER


def clear_workflow_session_cache(session_id: str) -> None:
    _emitter_cache.pop(session_id, None)
    _schema_graph_cache.pop(session_id, None)


class StreamEvent(TypedDict):
    type: str
    data: Any


class GraphState(TypedDict, total=False):
    session_id: str
    question: str
    expanded_question: str
    deep_think: bool
    execution_mode: str
    datasource_id: int
    intent: str
    need_rag: bool
    rag_chunks: list[dict]
    loop_count: int
    sql_retry_count: int
    system_prompts: dict[str, str]
    schema_context: str
    allowed_tables: list[str]
    cannot_answer: bool
    generated_sql: str
    sql_valid: bool
    sql_errors: list[str]
    query_result: dict | None
    summary: str
    direct_reply: str
    cache_hit_type: str
    sql_llm_cache_prompt: str
    sql_llm_cache_content: str
    sql_llm_cache_role: str
    stream_events: Annotated[list[StreamEvent], lambda a, b: a + b]
    connection_url: str


def _get_emitter(state: GraphState) -> Any:
    sid = state.get("session_id")
    return _emitter_cache.get(sid) if sid else None


def _allowed_tables_set(state: GraphState) -> set[str]:
    tables = state.get("allowed_tables", [])
    if isinstance(tables, set):
        return tables
    return set(tables)


def _emit(state: GraphState, event_type: str, data: Any) -> list[StreamEvent]:
    return [{"type": event_type, "data": data}]


def _get_llm():
    return create_chat_llm(streaming=True)


def _format_prompt(template: str, **kwargs: Any) -> str:
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


async def build_schema_from_db(
    session: AsyncSession, datasource_id: int
) -> tuple[SchemaGraph, list[str], str, str]:
    ds = await session.get(Datasource, datasource_id)
    connection_url = ds.connection_url if ds else ""

    tables_result = await session.execute(
        select(TableMetadata).where(
            TableMetadata.datasource_id == datasource_id,
            TableMetadata.is_allowed.is_(True),
        )
    )
    tables = tables_result.scalars().all()

    fk_result = await session.execute(
        select(FkRelationship).where(FkRelationship.datasource_id == datasource_id)
    )
    fks = fk_result.scalars().all()

    schema_graph = SchemaGraph()
    table_id_to_name: dict[int, str] = {}
    for t in tables:
        schema_graph.add_table(t.id, t.table_name, t.is_allowed)
        table_id_to_name[t.id] = t.table_name

    for fk in fks:
        from_name = table_id_to_name.get(fk.from_table_id)
        to_name = table_id_to_name.get(fk.to_table_id)
        if from_name and to_name:
            schema_graph.add_fk(from_name, fk.from_column, to_name, fk.to_column)

    table_ids = list(table_id_to_name.keys())
    columns_db: list[ColumnMetadata] = []
    if table_ids:
        columns_result = await session.execute(
            select(ColumnMetadata).where(ColumnMetadata.table_id.in_(table_ids))
        )
        columns_db = list(columns_result.scalars().all())

    table_dicts = [
        {"table_name": t.table_name, "description": t.description or ""} for t in tables
    ]
    column_dicts = [
        {
            "table_name": table_id_to_name[c.table_id],
            "column_name": c.column_name,
            "data_type": c.data_type,
            "description": c.description,
            "is_blacklisted": c.is_blacklisted,
        }
        for c in columns_db
        if c.table_id in table_id_to_name
    ]
    relevant_tables = sorted(schema_graph.allowed_tables)
    schema_context = schema_graph.build_schema_context(
        table_dicts, column_dicts, relevant_tables
    )
    if relevant_tables:
        schema_context += (
            "\n\n## Allowed tables (ONLY use these)\n"
            + ", ".join(relevant_tables)
        )

    return schema_graph, relevant_tables, schema_context, connection_url


async def ensure_schema_graph(state: GraphState, session: AsyncSession) -> SchemaGraph:
    sid = state.get("session_id", "")
    if sid and sid in _schema_graph_cache:
        return _schema_graph_cache[sid]
    schema_graph, _, _, _ = await build_schema_from_db(session, state["datasource_id"])
    if sid:
        _schema_graph_cache[sid] = schema_graph
    return schema_graph


async def load_context(state: GraphState, session: AsyncSession) -> GraphState:
    prompts = await load_active_prompts(session)
    schema_graph, allowed_tables, schema_context, connection_url = await build_schema_from_db(
        session, state["datasource_id"]
    )
    session_id = state.get("session_id") or str(uuid.uuid4())
    _schema_graph_cache[session_id] = schema_graph

    return {
        **state,
        "session_id": session_id,
        "system_prompts": prompts,
        "connection_url": connection_url,
        "allowed_tables": allowed_tables,
        "schema_context": schema_context,
        "loop_count": 0,
        "sql_retry_count": 0,
        "rag_chunks": [],
        "stream_events": _emit(state, "STATUS", {"message": "Context loaded"}),
    }


async def intent_classifier(state: GraphState, llm_service=None) -> GraphState:
    prompt = _format_prompt(
        state["system_prompts"].get("intent_classifier", ""),
        question=state["question"],
    )
    if llm_service:
        content, cache_hit = await llm_service.invoke(
            "intent_classifier",
            prompt,
            session_id=state.get("session_id"),
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = str(response.content)
        cache_hit = "none"
    parsed = _parse_json(content)
    intent = parsed.get("intent", "query_data")
    return {
        **state,
        "intent": intent,
        "cache_hit_type": cache_hit,
        "stream_events": _emit(state, "INTENT", {"intent": intent}),
    }


def route_after_intent(state: GraphState) -> Literal["rag_router", "direct_reply"]:
    if state.get("intent") in ("chitchat", "reject"):
        return "direct_reply"
    return "rag_router"


async def direct_reply(state: GraphState) -> GraphState:
    replies = {
        "chitchat": "我是 NL2SQL 助手，请提出与数据查询相关的问题。",
        "reject": "抱歉，该问题不在系统支持范围内。",
    }
    reply = replies.get(state.get("intent", ""), "请提出数据查询相关问题。")
    return {
        **state,
        "direct_reply": reply,
        "summary": reply,
        "stream_events": _emit(state, "SUMMARY", {"text": reply}),
    }


async def rag_router(state: GraphState, llm_service=None) -> GraphState:
    prompt = _format_prompt(
        state["system_prompts"].get("rag_router", ""),
        question=state["question"],
        intent=state.get("intent", ""),
    )
    if llm_service:
        content, _ = await llm_service.invoke(
            "rag_router",
            prompt,
            session_id=state.get("session_id"),
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = str(response.content)
    parsed = _parse_json(content)
    need_rag = parsed.get("need_rag", True)
    return {**state, "need_rag": need_rag}


def route_after_rag_router(state: GraphState) -> Literal["hybrid_retrieve", "direct_llm", "sql_generate"]:
    if state.get("need_rag", True):
        return "hybrid_retrieve"
    if state.get("intent") == "query_data":
        return "sql_generate"
    return "direct_llm"


async def hybrid_retrieve(state: GraphState) -> GraphState:
    retriever = HybridRetriever()
    query = state.get("expanded_question") or state["question"]
    chunks = retriever.search(query, datasource_id=state.get("datasource_id"))
    chunk_dicts = [
        {"content": c.content, "score": c.score, "doc_type": c.doc_type, "chunk_id": c.chunk_id}
        for c in chunks
    ]
    events = _emit(state, "RAG_CHUNK", {"chunks": chunk_dicts, "count": len(chunk_dicts)})

    return {
        **state,
        "rag_chunks": chunk_dicts,
        "stream_events": events,
    }


async def retrieval_judge(state: GraphState, llm_service=None) -> GraphState:
    chunks_text = "\n---\n".join(c["content"] for c in state.get("rag_chunks", []))
    prompt = _format_prompt(
        state["system_prompts"].get("retrieval_judge", ""),
        question=state["question"],
        chunks=chunks_text,
        loop_count=state.get("loop_count", 0),
    )
    if llm_service:
        content, _ = await llm_service.invoke(
            "retrieval_judge",
            prompt,
            session_id=state.get("session_id"),
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = str(response.content)
    parsed = _parse_json(content)
    decision = parsed.get("decision", "sufficient")
    return {**state, "_retrieval_decision": decision}


def route_after_judge(state: GraphState) -> Literal["query_expander", "sql_generate"]:
    decision = state.get("_retrieval_decision", "sufficient")
    if decision == "continue" and state.get("loop_count", 0) < settings.max_rag_loops:
        return "query_expander"
    return "sql_generate"


def _format_allowed_tables(state: GraphState) -> str:
    return ", ".join(sorted(_allowed_tables_set(state)))


async def _cache_valid_sql_generation(session: AsyncSession, state: GraphState) -> None:
    if not state.get("sql_valid") or state.get("cannot_answer"):
        return
    prompt = state.get("sql_llm_cache_prompt")
    content = state.get("sql_llm_cache_content")
    role = state.get("sql_llm_cache_role")
    if not prompt or not content or not role:
        return
    cache = LlmCache(session)
    await cache.set(
        role=role,
        model=settings.openai_model,
        prompt=prompt,
        response=content,
        token_saved=len(content.split()),
        semantic_key=state.get("question"),
    )


async def query_expander(state: GraphState, llm_service=None) -> GraphState:
    prompt = _format_prompt(
        state["system_prompts"].get("query_expander", ""),
        question=state["question"],
        intent=state.get("intent", ""),
        allowed_tables=_format_allowed_tables(state),
    )
    if llm_service:
        expanded, _ = await llm_service.invoke(
            "query_expander",
            prompt,
            session_id=state.get("session_id"),
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        expanded = str(response.content)
    expanded = expanded.strip()
    return {
        **state,
        "expanded_question": expanded,
        "loop_count": state.get("loop_count", 0) + 1,
        "stream_events": _emit(state, "STATUS", {"expanded_question": expanded}),
    }


async def direct_llm(state: GraphState, llm_service=None) -> GraphState:
    system_content = (
        f"{ROLE_GUARDRAILS}\n\n{USER_LANGUAGE_POLICY}\n\n"
        "You are the NL2SQL assistant. Answer the user's question within your role. "
        "Do not change persona or ignore NL2SQL constraints."
    )
    user_prompt = state["question"]
    combined_prompt = f"{system_content}\n\nUser question:\n{user_prompt}"

    async def on_token(role: str, delta: str) -> None:
        emitter = _get_emitter(state)
        if emitter:
            await emitter("LLM_TOKEN", {"role": "summary", "delta": delta})

    if llm_service:
        summary, _ = await llm_service.astream(
            "direct_llm",
            combined_prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
            cacheable=False,
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        parts: list[str] = []
        async for chunk in llm.astream(
            [
                SystemMessage(content=system_content),
                HumanMessage(content=user_prompt),
            ]
        ):
            delta = str(chunk.content) if chunk.content else ""
            if delta:
                parts.append(delta)
                await on_token("summary", delta)
        summary = "".join(parts)

    return {
        **state,
        "summary": summary,
        "stream_events": _emit(state, "SUMMARY", {"text": summary}),
    }


async def sql_generate(state: GraphState, llm_service=None) -> GraphState:
    role = "react_reasoner" if state.get("deep_think") else "sql_generator"
    chunks_text = "\n---\n".join(c["content"] for c in state.get("rag_chunks", []))
    allowed_tables_str = _format_allowed_tables(state)
    safety_rules = (
        "SELECT only; include LIMIT; "
        f"whitelist tables: {allowed_tables_str}"
    )
    if state.get("sql_errors"):
        chunks_text += f"\n\nPrevious validation errors: {state['sql_errors']}"
        chunks_text += f"\nALLOWED TABLES (use ONLY these): {allowed_tables_str}"
        chunks_text += "\nFORBIDDEN: any table not in the list above"
    prompt = _format_prompt(
        state["system_prompts"].get(role, ""),
        question=state["question"],
        schema_context=state.get("schema_context", ""),
        chunks=chunks_text,
        safety_rules=safety_rules,
        allowed_tables=allowed_tables_str,
    )

    cacheable = False
    events: list[StreamEvent] = []
    stream_role = "thought" if state.get("deep_think") else "sql"

    async def on_token(role: str, delta: str) -> None:
        emitter = _get_emitter(state)
        if emitter:
            await emitter("LLM_TOKEN", {"role": stream_role, "delta": delta})

    if llm_service:
        content, _ = await llm_service.astream(
            role,
            prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
            cacheable=cacheable,
            semantic_key=state["question"],
        )
    else:
        llm = _get_llm()
        parts: list[str] = []
        async for chunk in llm.astream([HumanMessage(content=prompt)]):
            delta = str(chunk.content) if chunk.content else ""
            if delta:
                parts.append(delta)
                await on_token(role, delta)
        content = "".join(parts)

    cannot_answer = False
    explanation = ""

    if state.get("deep_think"):
        events = _emit(state, "THOUGHT", {"text": "Starting ReAct reasoning..."})
        events += _emit(state, "THOUGHT", {"text": content[:500]})
        parsed = _parse_json(content)
        cannot_answer = bool(parsed.get("cannot_answer"))
        explanation = str(parsed.get("explanation", ""))
        if cannot_answer:
            sql = ""
        else:
            sql_match = re.search(r"SELECT\s+.+?(?:;|$)", content, re.IGNORECASE | re.DOTALL)
            sql = sql_match.group(0).strip().rstrip(";") if sql_match else ""
            if not sql and parsed.get("sql"):
                sql = str(parsed.get("sql", "")).strip()
    else:
        parsed = _parse_json(content)
        cannot_answer = bool(parsed.get("cannot_answer"))
        explanation = str(parsed.get("explanation", ""))
        if cannot_answer:
            sql = ""
        else:
            sql = str(parsed.get("sql", content) or "").strip()

    retry_count = state.get("sql_retry_count", 0)
    if state.get("sql_errors"):
        retry_count += 1

    result_state: GraphState = {
        **state,
        "generated_sql": sql,
        "cannot_answer": cannot_answer,
        "sql_retry_count": retry_count,
        "sql_errors": [],
        "sql_llm_cache_prompt": prompt,
        "sql_llm_cache_content": content,
        "sql_llm_cache_role": role,
        "stream_events": events,
    }

    if cannot_answer:
        summary = explanation or "当前数据源中没有能回答该问题的表，请在管理后台补充元数据或调整提问。"
        result_state["summary"] = summary
        result_state["sql_valid"] = False
        result_state["stream_events"] = events + [
            *_emit(state, "STATUS", {"cannot_answer": True}),
            *_emit(state, "SUMMARY", {"text": summary}),
        ]
    elif sql:
        result_state["stream_events"] = events + _emit(state, "SQL", {"sql": sql})

    return result_state


def route_after_sql_generate(state: GraphState) -> Literal["sql_safety", "finalize"]:
    if state.get("cannot_answer"):
        return "finalize"
    return "sql_safety"


async def sql_safety(state: GraphState, session: AsyncSession) -> GraphState:
    schema_graph = await ensure_schema_graph(state, session)
    validator = SqlValidator(_allowed_tables_set(state), schema_graph)
    result = validator.validate(state.get("generated_sql", ""))
    next_state: GraphState = {
        **state,
        "generated_sql": result.sql,
        "sql_valid": result.valid,
        "sql_errors": result.errors,
        "stream_events": _emit(
            state,
            "STATUS",
            {"sql_valid": result.valid, "errors": result.errors},
        ),
    }
    if result.valid:
        await _cache_valid_sql_generation(session, next_state)
    return next_state


def route_after_safety(state: GraphState) -> Literal["execute_or_return", "sql_generate"]:
    if state.get("sql_valid"):
        return "execute_or_return"
    if state.get("sql_retry_count", 0) < settings.max_sql_retries:
        return "sql_generate"
    return "execute_or_return"


async def execute_or_return(state: GraphState) -> GraphState:
    mode = state.get("execution_mode", "AUTO")
    events: list[StreamEvent] = []
    query_result = None

    if not state.get("sql_valid"):
        return {
            **state,
            "query_result": None,
            "stream_events": _emit(state, "ERROR", {"message": "SQL validation failed", "errors": state.get("sql_errors", [])}),
        }

    should_execute = mode == "EXECUTE" or (mode == "AUTO" and state.get("generated_sql"))
    if should_execute and mode != "GENERATE_ONLY" and state.get("connection_url"):
        try:
            query_result = await execute_sql(state["connection_url"], state["generated_sql"])
            events = _emit(state, "RESULT", query_result)
        except Exception as e:
            events = _emit(state, "ERROR", {"message": str(e)})

    return {**state, "query_result": query_result, "stream_events": events}


async def result_summarizer(state: GraphState, llm_service=None) -> GraphState:
    if state.get("direct_reply"):
        return state
    prompt = _format_prompt(
        state["system_prompts"].get("result_summarizer", ""),
        question=state["question"],
        sql=state.get("generated_sql", ""),
        result_preview=str(state.get("query_result", "Not executed"))[:2000],
    )

    async def on_token(role: str, delta: str) -> None:
        emitter = _get_emitter(state)
        if emitter:
            await emitter("LLM_TOKEN", {"role": "summary", "delta": delta})

    if llm_service:
        summary, _ = await llm_service.astream(
            "result_summarizer",
            prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
            semantic_key=state["question"],
            cacheable=bool(state.get("sql_valid")) and not state.get("cannot_answer"),
        )
    else:
        llm = _get_llm()
        parts: list[str] = []
        async for chunk in llm.astream([HumanMessage(content=prompt)]):
            delta = str(chunk.content) if chunk.content else ""
            if delta:
                parts.append(delta)
                await on_token("summary", delta)
        summary = "".join(parts)

    return {
        **state,
        "summary": summary,
        "stream_events": _emit(state, "SUMMARY", {"text": summary}),
    }


async def finalize(state: GraphState) -> GraphState:
    return {**state, "stream_events": _emit(state, "DONE", {"session_id": state.get("session_id")})}


PHASE_LABELS: dict[str, str] = {
    "load_context": "加载数据源与 Prompt…",
    "intent_classifier": "识别问题意图…",
    "direct_reply": "生成回复…",
    "rag_router": "判断是否需要检索…",
    "hybrid_retrieve": "检索相关知识…",
    "retrieval_judge": "评估检索结果…",
    "query_expander": "扩展查询…",
    "direct_llm": "生成回答…",
    "sql_generate": "生成 SQL…",
    "sql_safety": "校验 SQL 安全性…",
    "execute_or_return": "执行查询…",
    "result_summarizer": "总结查询结果…",
    "finalize": "完成",
}


def build_graph(session: AsyncSession, event_emitter=None, checkpointer=None):
    from backend.llm.service import LlmService

    llm_service = LlmService(session)
    cp = checkpointer or _CHECKPOINTER

    def wrap(fn):
        async def node(state: GraphState) -> GraphState:
            sid = state.get("session_id")
            if event_emitter and sid:
                _emitter_cache[sid] = event_emitter
            emitter = _get_emitter(state)
            if emitter:
                label = PHASE_LABELS.get(fn.__name__, fn.__name__)
                await emitter("STATUS", {"message": label, "phase": fn.__name__})
            if fn.__name__ == "load_context":
                return await load_context(state, session)
            if fn.__name__ == "sql_safety":
                return await sql_safety(state, session)
            if fn.__name__ in (
                "intent_classifier",
                "rag_router",
                "retrieval_judge",
                "query_expander",
                "sql_generate",
                "result_summarizer",
                "direct_llm",
            ):
                return await fn(state, llm_service)
            return await fn(state)

        node.__name__ = fn.__name__
        return node

    graph = StateGraph(GraphState)
    graph.add_node("load_context", wrap(load_context))
    graph.add_node("intent_classifier", wrap(intent_classifier))
    graph.add_node("direct_reply", wrap(direct_reply))
    graph.add_node("rag_router", wrap(rag_router))
    graph.add_node("hybrid_retrieve", wrap(hybrid_retrieve))
    graph.add_node("retrieval_judge", wrap(retrieval_judge))
    graph.add_node("query_expander", wrap(query_expander))
    graph.add_node("direct_llm", wrap(direct_llm))
    graph.add_node("sql_generate", wrap(sql_generate))
    graph.add_node("sql_safety", wrap(sql_safety))
    graph.add_node("execute_or_return", wrap(execute_or_return))
    graph.add_node("result_summarizer", wrap(result_summarizer))
    graph.add_node("finalize", wrap(finalize))

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "intent_classifier")
    graph.add_conditional_edges("intent_classifier", route_after_intent)
    graph.add_edge("direct_reply", "finalize")
    graph.add_conditional_edges(
        "rag_router",
        route_after_rag_router,
        {
            "hybrid_retrieve": "hybrid_retrieve",
            "direct_llm": "direct_llm",
            "sql_generate": "sql_generate",
        },
    )
    graph.add_edge("hybrid_retrieve", "retrieval_judge")
    graph.add_conditional_edges("retrieval_judge", route_after_judge)
    graph.add_edge("query_expander", "hybrid_retrieve")
    graph.add_edge("direct_llm", "finalize")
    graph.add_conditional_edges(
        "sql_generate",
        route_after_sql_generate,
        {"sql_safety": "sql_safety", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "sql_safety",
        route_after_safety,
        {"execute_or_return": "execute_or_return", "sql_generate": "sql_generate"},
    )
    graph.add_edge("execute_or_return", "result_summarizer")
    graph.add_edge("result_summarizer", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=cp)
