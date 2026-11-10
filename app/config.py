"""Application settings loaded from environment variables."""

from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ALLOWED_DOMAINS: List[str] = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "vm.tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com",
    "pinterest.com",
]


class Settings(BaseSettings):
    """Configuration settings for ClipGrab Bot."""

    bot_token: str = ""
    admin_ids: List[int] = []
    max_file_mb: int = 50
    max_duration_sec: int = 600
    max_concurrent_downloads: int = 3
    download_timeout_sec: int = 120
    allowed_domains: List[str] = DEFAULT_ALLOWED_DOMAINS
    cookies_file: Optional[str] = None
    db_path: str = "data/bot.db"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> List[int]:
        """Parse comma-separated admin IDs into list of ints."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def parse_allowed_domains(cls, v: object) -> List[str]:
        """Parse comma-separated allowed domains."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return DEFAULT_ALLOWED_DOMAINS
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [str(x).strip().lower() for x in v]
        return DEFAULT_ALLOWED_DOMAINS


settings = Settings()
