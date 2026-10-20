"""Verificação manual local de segurança, sem conexão ao MySQL."""

import logging
from io import StringIO

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import audit_logger, create_app


class EmptyRepository:
    def find_active_items(self):
        return []


class FailingRepository:
    def find_active_items(self):
        raise RuntimeError("private-db-host password=hidden")


def main() -> None:
    key = "manual-check-key-" + "x" * 20
    headers = {"X-Service-Key": key}
    payload = {"description": "Perdi um caderno azul na biblioteca"}
    output = StringIO()
    handler = logging.StreamHandler(output)
    audit_logger.addHandler(handler)
    try:
        settings = Settings(_env_file=None, service_api_key=key, rate_limit_per_minute=2)
        with TestClient(create_app(repository=EmptyRepository(), settings=settings)) as client:
            missing = client.post("/matches/search", json=payload)
            invalid = client.post(
                "/matches/search", json=payload,
                headers={"X-Service-Key": "invalid"},
            )
            first = client.post("/matches/search", json=payload, headers=headers)
            second = client.post("/matches/search", json=payload, headers=headers)
            excess = client.post("/matches/search", json=payload, headers=headers)
            health = client.get("/health")

        with TestClient(
            create_app(repository=FailingRepository(), settings=settings)
        ) as client:
            database_failure = client.post(
                "/matches/search", json=payload, headers=headers
            )
            health_during_failure = client.get("/health")

        statuses = [
            missing.status_code, invalid.status_code, first.status_code,
            second.status_code, excess.status_code, database_failure.status_code,
        ]
        assert statuses == [401, 401, 200, 200, 429, 503], statuses
        assert health.status_code == health_during_failure.status_code == 200
        assert excess.headers.get("Retry-After")
        assert database_failure.json() == {
            "detail": "Não foi possível consultar os itens encontrados"
        }
        audit = output.getvalue()
        assert payload["description"] not in audit
        assert key not in audit
        assert "private-db-host" not in audit
        assert "status=429" in audit and "status=503" in audit
        print("Manual: 401/401/200/200/429/503; /health 200; logs sem dados sensíveis")
    finally:
        audit_logger.removeHandler(handler)


if __name__ == "__main__":
    main()
