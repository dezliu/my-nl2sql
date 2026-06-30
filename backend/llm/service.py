"""LLM invocation with hybrid caching and streaming."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm.client import create_chat_llm
from backend.cache.llm_cache import LlmCache
from backend.config import settings

TokenCallback = Callable[[str, str], Awaitable[None]]


class LlmService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.llm = create_chat_llm(streaming=True)

    async def invoke(
        self,
        role: str,
        prompt: str,
        session_id: str | None = None,
        cacheable: bool = True,
        params: dict | None = None,
    ) -> tuple[str, str]:
        """Returns (response_text, cache_hit_type)."""
        if self.session and cacheable:
            cache = LlmCache(self.session)
            result = await cache.get(
                role=role,
                model=settings.openai_model,
                prompt=prompt,
                params=params,
                session_id=session_id,
            )
            if result.hit and result.response:
                return result.response, result.hit_type

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        text = str(response.content)

        if self.session and cacheable:
            cache = LlmCache(self.session)
            await cache.set(
                role=role,
                model=settings.openai_model,
                prompt=prompt,
                response=text,
                token_saved=len(text.split()),
                params=params,
                cacheable=cacheable,
            )

        return text, "none"

    async def astream(
        self,
        role: str,
        prompt: str,
        on_token: TokenCallback | None = None,
        session_id: str | None = None,
        cacheable: bool = True,
        params: dict | None = None,
    ) -> tuple[str, str]:
        """Stream tokens via on_token; returns (full_text, cache_hit_type)."""
        if self.session and cacheable:
            cache = LlmCache(self.session)
            result = await cache.get(
                role=role,
                model=settings.openai_model,
                prompt=prompt,
                params=params,
                session_id=session_id,
            )
            if result.hit and result.response:
                if on_token:
                    for char in result.response:
                        await on_token(role, char)
                return result.response, result.hit_type

        parts: list[str] = []
        async for chunk in self.llm.astream([HumanMessage(content=prompt)]):
            delta = str(chunk.content) if chunk.content else ""
            if delta:
                parts.append(delta)
                if on_token:
                    await on_token(role, delta)

        text = "".join(parts)

        if self.session and cacheable:
            cache = LlmCache(self.session)
            await cache.set(
                role=role,
                model=settings.openai_model,
                prompt=prompt,
                response=text,
                token_saved=len(text.split()),
                params=params,
                cacheable=cacheable,
            )

        return text, "none"
