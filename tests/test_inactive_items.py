"""Verifica o filtro de status contra a carga v2 no MySQL sintético."""

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from app.config import Settings
from app.main import create_app
from app.repository import MySQLItemRepository


TEST_KEY = "t" * 32


@pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="Ative com RUN_DB_INTEGRATION=1 e configure o MySQL sintético local",
)
def test_v2_inactive_items_are_excluded_from_search() -> None:
    settings = Settings()
    assert settings.db_name == "matching_development"

    engine = create_engine(
        settings.database_url,
        connect_args=settings.database_connect_args,
    )
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT DATABASE()")) == "matching_development"
            status_counts = dict(
                connection.execute(
                    text("SELECT status, COUNT(*) FROM item GROUP BY status")
                ).all()
            )
            inactive_rows = connection.execute(
                text("""
                    SELECT id, name, description, status
                    FROM item
                    WHERE status IN ('RETURNED', 'ARCHIVED')
                    ORDER BY id
                """)
            ).mappings().all()

        assert status_counts == {"ACTIVE": 1000, "RETURNED": 6, "ARCHIVED": 4}
        inactive_ids = {row["id"] for row in inactive_rows}
        assert inactive_ids == set(range(1001, 1011))

        repository = MySQLItemRepository(engine)
        active_ids = {item.id for item in repository.find_active_items()}
        assert active_ids == set(range(1, 1001))
        assert active_ids.isdisjoint(inactive_ids)

        local_settings = settings.model_copy(
            update={"service_api_key": SecretStr(TEST_KEY), "rate_limit_per_minute": 60}
        )
        application = create_app(repository=repository, settings=local_settings)
        with TestClient(application) as client:
            for row in inactive_rows:
                response = client.post(
                    "/matches/search",
                    json={
                        "description": f"{row['name']} {row['description']}",
                        "top_k": 20,
                    },
                    headers={"X-Service-Key": TEST_KEY},
                )
                assert response.status_code == 200, row["id"]
                returned_ids = {
                    match["item_id"] for match in response.json()["matches"]
                }
                assert returned_ids.isdisjoint(inactive_ids), row["id"]
    finally:
        engine.dispose()
