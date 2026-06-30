"""Shared OpenAI-compatible LLM client factory."""

from langchain_openai import ChatOpenAI

from backend.config import settings


def create_chat_llm(*, streaming: bool = True) -> ChatOpenAI:
    raw_key = settings.openai_api_key
    key = raw_key.strip() if raw_key else ""
    if not key:
        raise ValueError(
            "OPENAI_API_KEY 未配置。请在 .env 中设置有效的 API Key。"
        )

    kwargs: dict = {
        "model": settings.openai_model,
        "api_key": key,
        "streaming": streaming,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url.strip()

    return ChatOpenAI(**kwargs)
