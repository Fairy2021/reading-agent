from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StoryVerse Agent"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+psycopg://storyverse:storyverse@postgres:5432/storyverse"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_timeout_seconds: int = 30

    rag_embedding_dim: int = 1536
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 120
    rag_top_k: int = 6

    skill_character_min_mentions: int = 3
    skill_character_max_count: int = 80
    skill_evidence_per_character: int = 5
    skill_character_llm_segment_len: int = 4500
    skill_character_llm_max_segments: int = 1
    skill_character_fallback_enabled: bool = True
    skill_character_alias_merge_enabled: bool = True
    skill_default_incremental: bool = True
    skill_state_recent_evidence: int = 3
    skill_card_llm_enabled: bool = True
    skill_card_llm_max_characters_per_run: int = 40
    skill_card_evidence_chars: int = 1400
    skill_relationship_min_cooccurrence: int = 2
    skill_relationship_llm_segment_len: int = 3200
    skill_relationship_llm_max_segments: int = 1
    skill_relationship_fallback_enabled: bool = True
    skill_refine_llm_enabled: bool = True
    skill_refine_llm_max_candidates: int = 40
    skill_refine_merge_ratio: float = 1.0

    chat_session_memory_max_chars: int = 900
    chat_guard_enabled: bool = True

    portrait_generation_enabled: bool = True
    portrait_api_url: str = ""
    portrait_api_token: str = ""
    portrait_api_timeout_seconds: int = 45
    portrait_api_seed_field: str = "seed"
    portrait_api_prompt_field: str = "prompt"
    portrait_api_response_url_field: str = "image_url"
    portrait_generator_name: str = "external_image_api"
    portrait_cache_enabled: bool = True
    portrait_cache_dir: str = "/app/data/uploads/portraits"

    next_public_api_base_url: str = "http://localhost:8000"
    upload_dir: str = "/app/data/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
