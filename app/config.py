from functools import lru_cache
import ssl
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain import MatchingMethod


class Settings(BaseSettings):
    """Configurações carregadas do ambiente ou de um arquivo .env local."""

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "matching_development"
    db_user: str = "matching_reader"
    db_password: str = ""
    db_ssl_ca: str | None = None
    db_require_tls: bool = False
    service_api_key: SecretStr | None = None
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    match_method: MatchingMethod = MatchingMethod.HYBRID
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
        if self.service_api_key is not None and len(self.service_api_key.get_secret_value()) < 32:
            raise ValueError("SERVICE_API_KEY deve ter pelo menos 32 caracteres")
        if self.db_require_tls and not self.db_ssl_ca:
            raise ValueError("DB_SSL_CA deve ser configurado quando DB_REQUIRE_TLS=true")
        return self

    @property
    def database_connect_args(self) -> dict:
        if not self.db_ssl_ca:
            return {}
        # create_default_context confere o arquivo CA antes da primeira busca
        # PyMySQL usa este contexto para validar cadeia e identidade do host
        return {"ssl": ssl.create_default_context(cafile=self.db_ssl_ca)}

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
