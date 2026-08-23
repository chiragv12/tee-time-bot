from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    teeitup_username: str
    teeitup_password: str
    teeitup_site_alias: str = "fairfax-county-mco"
    teeitup_api_base: str = "https://phx-api-be-east-1b.kenna.io"
    log_level: str = "INFO"


settings = Settings()
