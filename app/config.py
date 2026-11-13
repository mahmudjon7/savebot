"""Application settings loaded from environment variables."""

from typing import List, Optional
from pydantic import Field
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
    admin_ids_raw: str = Field(default="", validation_alias="admin_ids")
    max_file_mb: int = 50
    max_duration_sec: int = 600
    max_concurrent_downloads: int = 3
    download_timeout_sec: int = 120
    allowed_domains_raw: str = Field(default="", validation_alias="allowed_domains")
    cookies_file: Optional[str] = "cookies/cookies.txt"
    db_path: str = "data/bot.db"
    log_level: str = "INFO"
    content_filter_enabled: bool = True
    media_cache_enabled: bool = False
    content_filter_categories_raw: str = Field(default="", validation_alias="content_filter_categories")
    blocked_terms_file: Optional[str] = "data/blocked_terms.txt"
    proxy: Optional[str] = None
    custom_bot_api_url: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def admin_ids(self) -> List[int]:
        """Parse comma-separated admin IDs from admin_ids_raw."""
        if not self.admin_ids_raw:
            return []
        res: List[int] = []
        for x in str(self.admin_ids_raw).split(","):
            val = x.strip()
            if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
                res.append(int(val))
        return res

    @property
    def content_filter_categories(self) -> List[str]:
        """Parse comma-separated categories; empty means all of them."""
        from app.services.content_filter import ALL_CATEGORIES

        res = [x.strip().lower() for x in str(self.content_filter_categories_raw).split(",") if x.strip()]
        return [c for c in res if c in ALL_CATEGORIES] or list(ALL_CATEGORIES)

    @property
    def allowed_domains(self) -> List[str]:
        """Parse comma-separated allowed domains from allowed_domains_raw."""
        if not self.allowed_domains_raw:
            return DEFAULT_ALLOWED_DOMAINS
        res = [x.strip().lower() for x in str(self.allowed_domains_raw).split(",") if x.strip()]
        return res if res else DEFAULT_ALLOWED_DOMAINS


settings = Settings()
