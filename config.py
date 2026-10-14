"""Configuration for Reflect and its optional infrastructure clients."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: float = Field(default=180, gt=0)
    OLLAMA_NUM_CTX: int = Field(default=8192, gt=0)
    OLLAMA_KEEP_ALIVE: str = "5m"

    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_API_VERSION: str = ""

    # Optional infrastructure; the chat flow stores data in SQLite.
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = Field(default=6379, gt=0, le=65535)
    REDIS_USERNAME: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False
    REDIS_TIMEOUT: float = Field(default=5, gt=0)
    REDIS_KEY_PREFIX: str = "reflect"
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_TIMEOUT: float = Field(default=5, gt=0)

    # Preserve the existing path so saved profiles and conversations remain available.
    DB_SQLITE_PATH: str = "data/sync_data.db"
    API_KEY: str = "default-insecure-key"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
