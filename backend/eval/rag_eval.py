"""Offline RAG evaluation: Recall@K and MRR with chunk/table gold labels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import RagChunk, RagDocument, RagEvalCase, RagEvalRun, RagEvalRunItem
from backend.rag.retriever import HybridRetriever, RetrievedChunk

DEFAULT_BENCHMARK_PATH = Path(__file__).resolve().parent / "rag_benchmark.json"


@dataclass
class CaseEvalResult:
    case_id: int
    question: str
    recall: float
    mrr: float
    match_mode: str
    retrieved_chunk_ids: list[str]
    hit_chunk_ids: list[str]
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class EvalSummary:
    run_id: int
    case_count: int
    evaluated_count: int
    skipped_count: int
    recall_at_k: float
    mrr: float


def resolve_match_mode(case: RagEvalCase) -> Optional[str]:
    if case.expected_chunk_ids:
        return "chunk"
    if case.expected_tables:
        return "table"
    return None


def is_chunk_relevant_weak(chunk: RetrievedChunk, expected_tables: list[str]) -> bool:
    table_name = chunk.metadata.get("table_name")
    if table_name and table_name in expected_tables:
        return True
    for table in expected_tables:
        if chunk.content.startswith(f"Table: {table}"):
            return True
        prefix = f"Table: {table}\n"
        if chunk.content.startswith(prefix):
            return True
    return False


def is_chunk_relevant(
    chunk: RetrievedChunk,
    *,
    match_mode: str,
    gold_chunk_ids: set[str],
    expected_tables: list[str],
) -> bool:
    if match_mode == "chunk":
        return chunk.chunk_id in gold_chunk_ids
    return is_chunk_relevant_weak(chunk, expected_tables)


async def resolve_gold_chunk_ids(
    session: AsyncSession,
    case: RagEvalCase,
    match_mode: str,
) -> set[str]:
    if match_mode == "chunk":
        return {str(cid) for cid in (case.expected_chunk_ids or [])}

    tables = case.expected_tables or []
    if not tables:
        return set()

    q = (
        select(RagChunk.id)
        .join(RagDocument, RagChunk.document_id == RagDocument.id)
        .where(
            RagDocument.doc_type == "table_metadata",
            RagDocument.title.in_(tables),
        )
    )
    if case.datasource_id is not None:
        q = q.where(RagDocument.datasource_id == case.datasource_id)

    result = await session.execute(q)
    return {str(chunk_id) for chunk_id in result.scalars().all()}


def compute_metrics(
    retrieved: list[RetrievedChunk],
    *,
    match_mode: str,
    gold_chunk_ids: set[str],
    expected_tables: list[str],
) -> tuple[float, float, list[str], list[str]]:
    retrieved_ids: list[str] = []
    hit_ids: list[str] = []
    first_relevant_rank: Optional[int] = None

    for rank, chunk in enumerate(retrieved, start=1):
        retrieved_ids.append(chunk.chunk_id)
        relevant = is_chunk_relevant(
            chunk,
            match_mode=match_mode,
            gold_chunk_ids=gold_chunk_ids,
            expected_tables=expected_tables,
        )
        if not relevant:
            continue
        if chunk.chunk_id not in hit_ids:
            hit_ids.append(chunk.chunk_id)
        if first_relevant_rank is None:
            first_relevant_rank = rank

    if match_mode == "chunk":
        gold = gold_chunk_ids
    elif gold_chunk_ids:
        gold = gold_chunk_ids
    else:
        gold = set()

    if gold:
        recall = len(set(hit_ids) & gold) / len(gold)
    elif match_mode == "table" and expected_tables:
        matched_tables: set[str] = set()
        for chunk in retrieved:
            for table in expected_tables:
                if is_chunk_relevant_weak(chunk, [table]):
                    matched_tables.add(table)
        recall = len(matched_tables) / len(expected_tables)
    else:
        recall = 0.0

    mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    return recall, mrr, retrieved_ids, hit_ids


def evaluate_retrieved(
    retrieved: list[RetrievedChunk],
    *,
    match_mode: str,
    gold_chunk_ids: set[str],
    expected_tables: list[str],
) -> tuple[float, float, list[str], list[str]]:
    return compute_metrics(
        retrieved,
        match_mode=match_mode,
        gold_chunk_ids=gold_chunk_ids,
        expected_tables=expected_tables,
    )


async def evaluate_case(
    session: AsyncSession,
    case: RagEvalCase,
    retrieved: list[RetrievedChunk],
) -> CaseEvalResult:
    match_mode = resolve_match_mode(case)
    if match_mode is None:
        return CaseEvalResult(
            case_id=case.id,
            question=case.question,
            recall=0.0,
            mrr=0.0,
            match_mode="none",
            retrieved_chunk_ids=[],
            hit_chunk_ids=[],
            skipped=True,
            skip_reason="缺少 expected_chunk_ids 或 expected_tables",
        )

    gold = await resolve_gold_chunk_ids(session, case, match_mode)
    recall, mrr, retrieved_ids, hit_ids = compute_metrics(
        retrieved,
        match_mode=match_mode,
        gold_chunk_ids=gold,
        expected_tables=case.expected_tables or [],
    )
    return CaseEvalResult(
        case_id=case.id,
        question=case.question,
        recall=recall,
        mrr=mrr,
        match_mode=match_mode,
        retrieved_chunk_ids=retrieved_ids,
        hit_chunk_ids=hit_ids,
    )


async def run_rag_eval(
    session: AsyncSession,
    *,
    top_k: int,
    datasource_id: Optional[int] = None,
    case_ids: Optional[list[int]] = None,
    retriever_factory: Callable[[], HybridRetriever] | None = None,
) -> EvalSummary:
    factory = retriever_factory or HybridRetriever
    retriever = factory()

    q = select(RagEvalCase).where(RagEvalCase.enabled.is_(True))
    if case_ids:
        q = q.where(RagEvalCase.id.in_(case_ids))
    result = await session.execute(q.order_by(RagEvalCase.id))
    cases = list(result.scalars().all())

    run = RagEvalRun(
        top_k=top_k,
        datasource_id=datasource_id,
        case_count=len(cases),
        status="running",
    )
    session.add(run)
    await session.flush()

    evaluated: list[CaseEvalResult] = []
    try:
        for case in cases:
            ds_filter = case.datasource_id if case.datasource_id is not None else datasource_id
            retrieved = retriever.search(case.question, top_k=top_k, datasource_id=ds_filter)
            case_result = await evaluate_case(session, case, retrieved)
            evaluated.append(case_result)

            session.add(
                RagEvalRunItem(
                    run_id=run.id,
                    case_id=case.id,
                    recall=case_result.recall,
                    mrr=case_result.mrr,
                    match_mode=case_result.match_mode,
                    retrieved_chunk_ids=case_result.retrieved_chunk_ids,
                    hit_chunk_ids=case_result.hit_chunk_ids,
                    skipped=case_result.skipped,
                    skip_reason=case_result.skip_reason,
                )
            )

        scored = [r for r in evaluated if not r.skipped]
        run.recall_at_k = (
            sum(r.recall for r in scored) / len(scored) if scored else 0.0
        )
        run.mrr = sum(r.mrr for r in scored) / len(scored) if scored else 0.0
        run.status = "done"
        await session.commit()
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        await session.commit()
        raise

    skipped_count = sum(1 for r in evaluated if r.skipped)
    return EvalSummary(
        run_id=run.id,
        case_count=len(cases),
        evaluated_count=len(scored),
        skipped_count=skipped_count,
        recall_at_k=run.recall_at_k or 0.0,
        mrr=run.mrr or 0.0,
    )


async def import_cases_from_json(
    session: AsyncSession,
    path: Path | str = DEFAULT_BENCHMARK_PATH,
    *,
    skip_existing: bool = True,
) -> tuple[int, int]:
    """Import benchmark cases. Returns (imported_count, skipped_count)."""
    file_path = Path(path)
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("benchmark JSON must be a list of case objects")

    imported = 0
    skipped = 0
    for item in raw:
        question = item.get("question", "").strip()
        if not question:
            skipped += 1
            continue

        if skip_existing:
            existing = await session.execute(
                select(RagEvalCase).where(RagEvalCase.question == question)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

        session.add(
            RagEvalCase(
                question=question,
                datasource_id=item.get("datasource_id"),
                expected_chunk_ids=item.get("expected_chunk_ids") or None,
                expected_tables=item.get("expected_tables") or None,
                enabled=item.get("enabled", True),
                note=item.get("note"),
            )
        )
        imported += 1

    await session.commit()
    return imported, skipped
