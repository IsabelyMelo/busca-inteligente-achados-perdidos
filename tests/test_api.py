from datetime import datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import ItemCandidate
from app.main import create_app
from tests.fakes import FakeItemRepository


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
    application = create_app(repository=repository, settings=Settings())

    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={
                "description": "Celular Samsung preto com capa azul",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["returned_count"] == 1
    assert body["matches"][0]["item_id"] == 1


def test_search_endpoint_validates_short_description() -> None:
    application = create_app(repository=FakeItemRepository([]), settings=Settings())

    with TestClient(application) as client:
        response = client.post(
            "/matches/search",
            json={"description": "curta"},
        )

    assert response.status_code == 422

