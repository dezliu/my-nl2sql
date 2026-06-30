"""LLM invocation with hybrid caching."""

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache.llm_cache import LlmCache
from backend.config import settings


class LlmService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key or "sk-placeholder",
            streaming=True,
        )

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
