from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/events"
    checkpoint_database_url: str = "postgresql://postgres:postgres@localhost:5432/events"

    chroma_persist_path: str = "./chroma_db"
    chroma_collection: str = "events"


@lru_cache
def get_settings() -> Settings:
    return Settings()
