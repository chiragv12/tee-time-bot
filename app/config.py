from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    teeitup_username: str
    teeitup_password: str
    teeitup_site_alias: str = "fairfax-county-mco"
    teeitup_api_base: str = "https://phx-api-be-east-1b.kenna.io"
    log_level: str = "INFO"
    # Short numeric facility IDs (the `course=` URL param on the site) for MVP scope.
    supported_facility_ids: str = "7743,7756"

    # Local dev uses SQLite; point at Neon Postgres when hosted, e.g.
    # postgresql+asyncpg://user:pass@host/db (needs the asyncpg package).
    database_url: str = "sqlite+aiosqlite:///./tee_time_bot.db"

    # Scheduler tuning: wake early, give up after the window.
    wake_lead_seconds: int = 30
    search_window_minutes: int = 10


settings = Settings()
