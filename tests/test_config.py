import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import MatchingMethod


def test_settings_reads_matching_method_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MATCH_METHOD", "cosine")

    settings = Settings(_env_file=None)

    assert settings.match_method is MatchingMethod.COSINE


def test_service_key_must_have_sufficient_length() -> None:
    with pytest.raises(ValidationError, match="pelo menos 32 caracteres"):
        Settings(_env_file=None, service_api_key="short")


def test_required_tls_needs_ca() -> None:
    with pytest.raises(ValidationError, match="DB_SSL_CA"):
        Settings(_env_file=None, db_require_tls=True)
