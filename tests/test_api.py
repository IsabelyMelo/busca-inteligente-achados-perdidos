import logging
import ssl
from datetime import datetime

import certifi
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.domain import ItemCandidate
from app.main import create_app
from tests.fakes import FakeItemRepository

TEST_KEY = "t" * 32
AUTH_HEADERS = {"X-Service-Key": TEST_KEY}


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, service_api_key=SecretStr(TEST_KEY), **overrides)


def test_search_endpoint_returns_ranked_items() -> None:
    repository = FakeItemRepository(
        [
            ItemCandidate(
                id=1,
                name="Smartphone Samsung",
                description="Aparelho preto com capa azul",
                location="Biblioteca",
                category_name="Eletrônicos",
                found_on=datetime(2026, 8, 20, 14, 30),
            )
        ]
    )
    application = create_app(repository=repository, settings=make_settings())

    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={
                "description": "Celular Samsung preto com capa azul",
                "top_k": 5,
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["returned_count"] == 1
    assert body["matches"][0]["item_id"] == 1


def test_search_endpoint_validates_short_description() -> None:
    application = create_app(repository=FakeItemRepository([]), settings=make_settings())

    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={"description": "curta"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 422


def test_search_endpoint_uses_configured_matching_method() -> None:
    repository = FakeItemRepository(
        [
            ItemCandidate(
                id=1,
                name="Smartphone Samsung",
                description="Aparelho preto com capa azul",
                location="Biblioteca",
                category_name="Eletrônicos",
                found_on=datetime(2026, 8, 20, 14, 30),
            )
        ]
    )
    application = create_app(
        repository=repository,
        settings=make_settings(match_method="levenshtein"),
    )

    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={
                "description": "Celular Samsung preto com capa azul",
                "top_k": 1,
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert match["final_score"] == match["levenshtein_score"]


def test_search_denies_missing_and_invalid_credentials() -> None:
    application = create_app(repository=FakeItemRepository([]), settings=make_settings())
    payload = {"description": "Perdi uma carteira preta"}

    with TestClient(application) as client:
        missing = client.post("/matches/search", json=payload)
        invalid = client.post(
            "/matches/search", json=payload, headers={"X-Service-Key": "wrong"}
        )
        health = client.get("/health")

    assert missing.status_code == invalid.status_code == 401
    assert missing.json() == invalid.json() == {"detail": "Não autorizado"}
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_swagger_documents_service_key_without_exposing_its_value() -> None:
    application = create_app(repository=FakeItemRepository([]), settings=make_settings())

    with TestClient(application) as client:
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")

    assert docs.status_code == 200
    assert openapi.status_code == 200
    schema = openapi.json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Service-Key",
    }
    assert schema["paths"]["/matches/search"]["post"]["security"] == [
        {"APIKeyHeader": []}
    ]
    assert TEST_KEY not in openapi.text


def test_rate_limit_and_audit_omit_description_and_key(caplog) -> None:
    application = create_app(
        repository=FakeItemRepository([]),
        settings=make_settings(rate_limit_per_minute=2),
    )
    description = "Perdi um caderno confidencial na biblioteca"
    payload = {"description": description}

    with caplog.at_level(logging.INFO, logger="app.audit"):
        with TestClient(application) as client:
            responses = [
                client.post("/matches/search", json=payload, headers=AUTH_HEADERS)
                for _ in range(3)
            ]

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert 1 <= int(responses[2].headers["Retry-After"]) <= 60
    assert "timestamp=" in caplog.text
    assert "client=service route=/matches/search status=429" in caplog.text
    assert description not in caplog.text
    assert TEST_KEY not in caplog.text


def test_database_failure_has_safe_response_and_log(caplog) -> None:
    class FailingRepository:
        def find_active_items(self):
            raise RuntimeError("private-db-host password=do-not-log")

    application = create_app(repository=FailingRepository(), settings=make_settings())
    with caplog.at_level(logging.INFO, logger="app.audit"):
        with TestClient(application) as client:
            response = client.post(
                "/matches/search",
                json={"description": "Perdi uma carteira preta"},
                headers=AUTH_HEADERS,
            )
            health = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Não foi possível consultar os itens encontrados"}
    assert "private-db-host" not in caplog.text
    assert "do-not-log" not in caplog.text
    assert "status=503" in caplog.text
    assert health.status_code == 200


def test_invalid_request_does_not_echo_input() -> None:
    application = create_app(repository=FakeItemRepository([]), settings=make_settings())
    description = "sensitive-input"
    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={"description": description, "top_k": 999},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "Requisição inválida"}
    assert description not in response.text


def test_missing_service_key_prevents_startup() -> None:
    application = create_app(
        repository=FakeItemRepository([]),
        settings=Settings(_env_file=None, service_api_key=None),
    )
    with pytest.raises(RuntimeError, match="SERVICE_API_KEY"):
        with TestClient(application):
            pass


def test_aiven_ca_enables_certificate_and_hostname_verification(monkeypatch) -> None:
    captured = {}

    class FakeEngine:
        def dispose(self):
            pass

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return FakeEngine()

    monkeypatch.setattr("app.main.create_engine", fake_create_engine)
    application = create_app(
        settings=make_settings(db_ssl_ca=certifi.where(), db_require_tls=True)
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200

    context = captured["connect_args"]["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.get_ca_certs()


def test_invalid_ca_prevents_startup(monkeypatch, tmp_path) -> None:
    invalid_ca = tmp_path / "invalid-ca.pem"
    invalid_ca.write_text("invalid certificate", encoding="utf-8")
    application = create_app(
        settings=make_settings(db_ssl_ca=str(invalid_ca), db_require_tls=True)
    )

    with pytest.raises(ssl.SSLError):
        with TestClient(application):
            pass
