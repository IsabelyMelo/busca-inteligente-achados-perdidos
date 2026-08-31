from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações carregadas do ambiente ou de um arquivo .env local."""

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "matching_development"
    db_user: str = "matching_reader"
    db_password: str = ""
    match_alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    match_beta: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_weights(self) -> "Settings":
        if abs((self.match_alpha + self.match_beta) - 1.0) > 1e-9:
            raise ValueError("MATCH_ALPHA + MATCH_BETA deve ser igual a 1")
        return self

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        user = quote_plus(self.db_user)
        return (
            f"mysql+pymysql://{user}:{password}@{self.db_host}:"
            f"{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

