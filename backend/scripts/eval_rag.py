"""CLI entry for offline RAG evaluation."""

import argparse
import asyncio

from backend.db.session import async_session_factory, engine
from backend.eval.rag_eval import DEFAULT_BENCHMARK_PATH, import_cases_from_json, run_rag_eval


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline RAG evaluation")
    parser.add_argument("--top-k", type=int, default=5, help="Top K for retrieval")
    parser.add_argument("--datasource-id", type=int, default=None, help="Filter datasource")
    parser.add_argument("--import-benchmark", action="store_true", help="Import benchmark JSON first")
    parser.add_argument(
        "--benchmark-path",
        type=str,
        default=str(DEFAULT_BENCHMARK_PATH),
        help="Path to benchmark JSON",
    )
    args = parser.parse_args()

    async with async_session_factory() as session:
        if args.import_benchmark:
            imported, skipped = await import_cases_from_json(session, args.benchmark_path)
            print(f"Imported {imported} cases, skipped {skipped}")

        summary = await run_rag_eval(
            session,
            top_k=args.top_k,
            datasource_id=args.datasource_id,
        )
        print(f"Run #{summary.run_id}")
        print(f"Cases: {summary.case_count} (evaluated {summary.evaluated_count}, skipped {summary.skipped_count})")
        print(f"Recall@{args.top_k}: {summary.recall_at_k:.4f}")
        print(f"MRR: {summary.mrr:.4f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
