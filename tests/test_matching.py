from datetime import datetime

from app.domain import ItemCandidate
from app.matching import MatchingService
from tests.fakes import FakeItemRepository


def sample_items() -> list[ItemCandidate]:
    return [
        ItemCandidate(
            id=1,
            name="Smartphone Samsung",
            description="Aparelho preto com capa azul e tela trincada",
            location="Biblioteca",
            category_name="Eletrônicos",
            found_on=datetime(2026, 8, 20, 14, 30),
        ),
        ItemCandidate(
            id=2,
            name="Óculos de grau",
            description="Armação preta retangular",
            location="Laboratório de informática",
            category_name="Acessórios",
            found_on=datetime(2026, 8, 22, 16, 0),
        ),
    ]


def test_search_ranks_expected_item_first() -> None:
    service = MatchingService(FakeItemRepository(sample_items()))

    results = service.search(
        "Perdi um celular Samsung preto com capa azul na biblioteca",
        top_k=2,
    )

    assert results[0].item.id == 1
    assert results[0].final_score >= results[1].final_score
    assert all(0 <= result.final_score <= 1 for result in results)


def test_search_returns_empty_list_when_there_are_no_items() -> None:
    service = MatchingService(FakeItemRepository([]))

    assert service.search("celular samsung preto") == []

