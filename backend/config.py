from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+aiomysql://nl2sql:nl2sql@localhost:3306/nl2sql"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "nl2sql_rag"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    secret_key: str = "change-me-in-production"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    semantic_cache_threshold: float = 0.95
    default_sql_limit: int = 1000
    max_rag_loops: int = 2
    max_sql_retries: int = 2
    rag_top_k: int = 10
    rag_alert_threshold: float = 0.6


settings = Settings()
