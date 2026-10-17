from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")
    environment: str = "development"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    bootstrap_secret: str = ""
    access_minutes: int = 15
    refresh_days: int = 7
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "backend"]
    cors_origins: list[str] = []
    max_request_bytes: int = 65536
    max_upload_bytes: int = 64 * 1024 * 1024
    upload_chunk_bytes: int = 1024 * 1024
    source_storage_path: str = "../.private-source-objects"
    source_s3_bucket: str = ""
    source_s3_region: str = "me-central-1"
    source_kms_key: str = ""
    connector_encryption_key: str = ""
    zoho_redirect_uris: list[str] = ["http://localhost:8000/oauth/zoho"]
    financial_ai_hourly_requests: int = 20
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: float = 20
    ai_max_tokens: int = 512

    @model_validator(mode="after")
    def secure_production(self):
        if self.environment == "production" and (
            self.bootstrap_secret or len(self.jwt_secret) < 48
        ):
            raise ValueError("Production requires a strong signing secret and disabled bootstrap")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
