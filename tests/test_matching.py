from datetime import datetime

import pytest

import app.matching as matching_module
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


def test_tfidf_is_fitted_only_on_items_and_reused_until_collection_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted_corpora: list[list[str]] = []
    real_vectorizer = matching_module.TfidfVectorizer

    class RecordingVectorizer(real_vectorizer):
        def fit_transform(self, raw_documents, y=None):
            documents = list(raw_documents)
            fitted_corpora.append(documents)
            return super().fit_transform(documents, y)

    monkeypatch.setattr(matching_module, "TfidfVectorizer", RecordingVectorizer)
    repository = FakeItemRepository(sample_items())
    service = MatchingService(repository)

    service.search("celular samsung azul", top_k=2)
    service.search("oculos pretos laboratorio", top_k=2)

    assert len(fitted_corpora) == 1
    assert fitted_corpora[0] == [
        matching_module.build_item_text(item) for item in sample_items()
    ]
    assert "celular samsung azul" not in fitted_corpora[0]

    repository.items.append(
        ItemCandidate(
            id=3,
            name="Chaveiro",
            description="Três chaves em argola prateada",
            location="Bloco 4",
            category_name="Chaves",
            found_on=datetime(2026, 8, 23, 9, 0),
        )
    )
    service.search("chaves bloco 4", top_k=3)

    assert len(fitted_corpora) == 2


@pytest.mark.parametrize(
    ("method", "alpha", "beta", "expected_component"),
    [
        ("cosine", 1.0, 0.0, "cosine_score"),
        ("levenshtein", 0.0, 1.0, "levenshtein_score"),
    ],
)
def test_method_matches_equivalent_extreme_hybrid_weight(
    method: str,
    alpha: float,
    beta: float,
    expected_component: str,
) -> None:
    repository = FakeItemRepository(sample_items())
    selected_results = MatchingService(repository, method=method).search(
        "celular samsung preto capa azul biblioteca",
        top_k=2,
    )
    hybrid_results = MatchingService(
        repository,
        method="hybrid",
        alpha=alpha,
        beta=beta,
    ).search("celular samsung preto capa azul biblioteca", top_k=2)

    assert [result.item.id for result in selected_results] == [
        result.item.id for result in hybrid_results
    ]
    for selected, hybrid in zip(selected_results, hybrid_results, strict=True):
        assert selected.final_score == pytest.approx(hybrid.final_score)
        assert selected.final_score == pytest.approx(
            getattr(selected, expected_component)
        )


def test_tied_results_are_ordered_by_item_id() -> None:
    items = sample_items()
    tied_items = [
        ItemCandidate(
            id=item_id,
            name=items[0].name,
            description=items[0].description,
            location=items[0].location,
            category_name=items[0].category_name,
            found_on=items[0].found_on,
        )
        for item_id in (2, 1)
    ]
    service = MatchingService(FakeItemRepository(tied_items), method="cosine")

    results = service.search("celular samsung preto", top_k=2)

    assert [result.item.id for result in results] == [1, 2]
    assert results[0].final_score == pytest.approx(results[1].final_score)


def test_all_scores_stay_in_unit_interval_for_every_method() -> None:
    for method in ("cosine", "levenshtein", "hybrid"):
        results = MatchingService(
            FakeItemRepository(sample_items()),
            method=method,
        ).search("celular samsung preto", top_k=2)

        assert all(
            0 <= score <= 1
            for result in results
            for score in (
                result.cosine_score,
                result.levenshtein_score,
                result.final_score,
            )
        )
