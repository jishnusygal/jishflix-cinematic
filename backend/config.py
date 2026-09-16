from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    jellyfin_url: str = 'http://jellyfin:8096'
    redis_url: str = 'redis://redis:6379/0'
    secret_key: SecretStr = Field(min_length=32)
    public_url: str = 'http://localhost:8000'
    cookie_secure: bool = True
    session_ttl: int = Field(default=604800, ge=300, le=2592000)
    cache_ttl: int = Field(default=20, ge=0, le=300)
    frontend_dist: str = 'frontend/dist'
    iptv_m3u_url: str | None = None
    iptv_xmltv_url: str | None = None

    @field_validator('jellyfin_url', 'public_url')
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('Expected an HTTP(S) URL without credentials, query, or fragment')
        return value.rstrip('/')


@lru_cache
def get_settings() -> Settings:
    return Settings()
