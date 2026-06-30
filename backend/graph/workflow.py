"""LangGraph NL2SQL workflow."""

import json
import re
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import Datasource, FkRelationship, TableMetadata
from backend.db.prompts import load_active_prompts
from backend.rag.retriever import HybridRetriever
from backend.sql.schema import SchemaGraph, SqlValidator, execute_sql


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
    schema_graph: SchemaGraph
    allowed_tables: set[str]
    generated_sql: str
    sql_valid: bool
    sql_errors: list[str]
    query_result: dict | None
    summary: str
    direct_reply: str
    cache_hit_type: str
    stream_events: Annotated[list[StreamEvent], lambda a, b: a + b]
    connection_url: str
    event_emitter: Any


def _emit(state: GraphState, event_type: str, data: Any) -> list[StreamEvent]:
    return [{"type": event_type, "data": data}]


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key or "sk-placeholder",
        streaming=True,
    )


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


async def load_context(state: GraphState, session: AsyncSession) -> GraphState:
    prompts = await load_active_prompts(session)
    ds = await session.get(Datasource, state["datasource_id"])
    connection_url = ds.connection_url if ds else ""

    tables_result = await session.execute(
        select(TableMetadata).where(
            TableMetadata.datasource_id == state["datasource_id"],
            TableMetadata.is_allowed.is_(True),
        )
    )
    tables = tables_result.scalars().all()

    fk_result = await session.execute(
        select(FkRelationship).where(FkRelationship.datasource_id == state["datasource_id"])
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

    return {
        **state,
        "session_id": state.get("session_id") or str(uuid.uuid4()),
        "system_prompts": prompts,
        "connection_url": connection_url,
        "schema_graph": schema_graph,
        "allowed_tables": schema_graph.allowed_tables,
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
            "intent_classifier", prompt, session_id=state.get("session_id")
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
            "rag_router", prompt, session_id=state.get("session_id")
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

    table_names = _extract_table_names_from_chunks(chunk_dicts)
    schema_context = state["schema_graph"].build_schema_context(
        [{"table_name": t, "description": ""} for t in table_names],
        [],
        table_names,
    )
    return {
        **state,
        "rag_chunks": chunk_dicts,
        "schema_context": schema_context,
        "stream_events": events,
    }


def _extract_table_names_from_chunks(chunks: list[dict]) -> list[str]:
    names: list[str] = []
    for c in chunks:
        content = c.get("content", "")
        match = re.search(r"Table:\s*(\w+)", content)
        if match:
            names.append(match.group(1))
    return list(dict.fromkeys(names)) or list(
        {t for t in re.findall(r"\b(\w+)\s*\.", " ".join(c.get("content", "") for c in chunks))}
    )


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
            "retrieval_judge", prompt, session_id=state.get("session_id")
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


async def query_expander(state: GraphState, llm_service=None) -> GraphState:
    prompt = _format_prompt(
        state["system_prompts"].get("query_expander", ""),
        question=state["question"],
        intent=state.get("intent", ""),
    )
    if llm_service:
        expanded, _ = await llm_service.invoke(
            "query_expander", prompt, session_id=state.get("session_id")
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
    prompt = state["question"]

    async def on_token(role: str, delta: str) -> None:
        emitter = state.get("event_emitter")
        if emitter:
            await emitter("LLM_TOKEN", {"role": "summary", "delta": delta})

    if llm_service:
        summary, _ = await llm_service.astream(
            "result_summarizer",
            prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
            cacheable=False,
        )
    else:
        llm = _get_llm()
        parts: list[str] = []
        async for chunk in llm.astream(
            [SystemMessage(content="You are a helpful data assistant."), HumanMessage(content=prompt)]
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
    safety_rules = "SELECT only; whitelist tables; include LIMIT"
    if state.get("sql_errors"):
        chunks_text += f"\n\nPrevious errors: {state['sql_errors']}"
    prompt = _format_prompt(
        state["system_prompts"].get(role, ""),
        question=state["question"],
        schema_context=state.get("schema_context", ""),
        chunks=chunks_text,
        safety_rules=safety_rules,
    )

    cacheable = not state.get("deep_think")
    events: list[StreamEvent] = []
    stream_role = "thought" if state.get("deep_think") else "sql"

    async def on_token(role: str, delta: str) -> None:
        emitter = state.get("event_emitter")
        if emitter:
            await emitter("LLM_TOKEN", {"role": stream_role, "delta": delta})

    if llm_service:
        content, _ = await llm_service.astream(
            role,
            prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
            cacheable=cacheable,
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

    if state.get("deep_think"):
        events = _emit(state, "THOUGHT", {"text": "Starting ReAct reasoning..."})
        events += _emit(state, "THOUGHT", {"text": content[:500]})
        sql_match = re.search(r"SELECT\s+.+?(?:;|$)", content, re.IGNORECASE | re.DOTALL)
        sql = sql_match.group(0).strip().rstrip(";") if sql_match else ""
    else:
        parsed = _parse_json(content)
        sql = parsed.get("sql", content)

    retry_count = state.get("sql_retry_count", 0)
    if state.get("sql_errors"):
        retry_count += 1

    return {
        **state,
        "generated_sql": sql,
        "sql_retry_count": retry_count,
        "sql_errors": [],
        "stream_events": events + _emit(state, "SQL", {"sql": sql}),
    }


async def sql_safety(state: GraphState) -> GraphState:
    validator = SqlValidator(state.get("allowed_tables", set()), state["schema_graph"])
    result = validator.validate(state.get("generated_sql", ""))
    return {
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
        emitter = state.get("event_emitter")
        if emitter:
            await emitter("LLM_TOKEN", {"role": "summary", "delta": delta})

    if llm_service:
        summary, _ = await llm_service.astream(
            "result_summarizer",
            prompt,
            on_token=on_token,
            session_id=state.get("session_id"),
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


def build_graph(session: AsyncSession, event_emitter=None):
    from backend.llm.service import LlmService

    llm_service = LlmService(session)

    async def wrap(fn):
        async def node(state: GraphState) -> GraphState:
            if event_emitter and not state.get("event_emitter"):
                state["event_emitter"] = event_emitter
            if fn.__name__ == "load_context":
                return await load_context(state, session)
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
    graph.add_edge("sql_generate", "sql_safety")
    graph.add_conditional_edges(
        "sql_safety",
        route_after_safety,
        {"execute_or_return": "execute_or_return", "sql_generate": "sql_generate"},
    )
    graph.add_edge("execute_or_return", "result_summarizer")
    graph.add_edge("result_summarizer", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
