from app.config import Settings
from app.domain import MatchingMethod


def test_settings_reads_matching_method_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MATCH_METHOD", "cosine")

    settings = Settings(_env_file=None)

    assert settings.match_method is MatchingMethod.COSINE
