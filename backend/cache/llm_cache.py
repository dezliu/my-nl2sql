"""Hybrid LLM cache: exact hash + semantic similarity."""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import LlmCacheEntry, LlmCacheHitLog
from backend.rag.retriever import HybridRetriever

CacheHitType = Literal["none", "exact", "semantic"]


@dataclass
class CacheResult:
    hit: bool
    hit_type: CacheHitType
    response: str | None = None
    saved_tokens: int = 0
    similarity: float | None = None
    cache_entry_id: int | None = None


class LlmCache:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._retriever = HybridRetriever()

    @staticmethod
    def _hash_key(role: str, model: str, prompt: str, params: dict | None = None) -> str:
        normalized = json.dumps(
            {"role": role, "model": model, "prompt": prompt.strip(), "params": params or {}},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def _semantic_text(role: str, semantic_key: str | None, prompt: str) -> str:
        if semantic_key:
            return semantic_key.strip()
        return prompt

    async def get(
        self,
        role: str,
        model: str,
        prompt: str,
        params: dict | None = None,
        session_id: str | None = None,
        semantic_key: str | None = None,
    ) -> CacheResult:
        start = time.monotonic()
        cache_key = self._hash_key(role, model, prompt, params)

        result = await self.session.execute(
            select(LlmCacheEntry).where(LlmCacheEntry.cache_key_hash == cache_key)
        )
        entry = result.scalar_one_or_none()
        if entry:
            latency = int((time.monotonic() - start) * 1000)
            await self._log_hit(session_id, entry.id, "exact", entry.token_saved, None, latency)
            return CacheResult(
                hit=True,
                hit_type="exact",
                response=entry.response,
                saved_tokens=entry.token_saved,
                cache_entry_id=entry.id,
            )

        semantic = await self._semantic_lookup(
            role, model, self._semantic_text(role, semantic_key, prompt)
        )
        if semantic.hit:
            latency = int((time.monotonic() - start) * 1000)
            await self._log_hit(
                session_id,
                semantic.cache_entry_id,
                "semantic",
                semantic.saved_tokens,
                semantic.similarity,
                latency,
            )
        return semantic

    async def _semantic_lookup(self, role: str, model: str, semantic_text: str) -> CacheResult:
        query_vec = self._retriever._embed_dense(semantic_text)
        result = await self.session.execute(
            select(LlmCacheEntry).where(
                LlmCacheEntry.role == role,
                LlmCacheEntry.model == model,
                LlmCacheEntry.embedding.isnot(None),
            )
        )
        best_score = 0.0
        best_entry: LlmCacheEntry | None = None
        for entry in result.scalars().all():
            if not entry.embedding:
                continue
            score = _cosine_similarity(query_vec, entry.embedding)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= settings.semantic_cache_threshold:
            return CacheResult(
                hit=True,
                hit_type="semantic",
                response=best_entry.response,
                saved_tokens=best_entry.token_saved,
                similarity=best_score,
                cache_entry_id=best_entry.id,
            )
        return CacheResult(hit=False, hit_type="none")

    async def set(
        self,
        role: str,
        model: str,
        prompt: str,
        response: str,
        token_saved: int = 0,
        params: dict | None = None,
        prompt_version: int | None = None,
        cacheable: bool = True,
        semantic_key: str | None = None,
    ) -> None:
        if not cacheable:
            return
        cache_key = self._hash_key(role, model, prompt, params)
        embedding = self._retriever._embed_dense(
            self._semantic_text(role, semantic_key, prompt)
        )
        entry = LlmCacheEntry(
            cache_key_hash=cache_key,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest(),
            role=role,
            model=model,
            response=response,
            token_saved=token_saved,
            embedding=embedding,
            prompt_version=prompt_version,
        )
        self.session.add(entry)
        await self.session.commit()

    async def _log_hit(
        self,
        session_id: str | None,
        entry_id: int | None,
        hit_type: str,
        saved_tokens: int,
        similarity: float | None,
        latency_ms: int,
    ) -> None:
        log = LlmCacheHitLog(
            session_id=session_id,
            cache_entry_id=entry_id,
            hit_type=hit_type,
            saved_tokens=saved_tokens,
            similarity=similarity,
            latency_ms=latency_ms,
        )
        self.session.add(log)
        await self.session.commit()

    async def get_stats(self) -> dict:
        from sqlalchemy import func

        total_hits = await self.session.execute(select(func.count(LlmCacheHitLog.id)))
        exact_hits = await self.session.execute(
            select(func.count(LlmCacheHitLog.id)).where(LlmCacheHitLog.hit_type == "exact")
        )
        semantic_hits = await self.session.execute(
            select(func.count(LlmCacheHitLog.id)).where(LlmCacheHitLog.hit_type == "semantic")
        )
        saved = await self.session.execute(select(func.sum(LlmCacheHitLog.saved_tokens)))
        return {
            "total_hits": total_hits.scalar() or 0,
            "exact_hits": exact_hits.scalar() or 0,
            "semantic_hits": semantic_hits.scalar() or 0,
            "total_tokens_saved": saved.scalar() or 0,
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
