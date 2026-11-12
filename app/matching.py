from threading import Lock
from time import perf_counter

import numpy as np
from rapidfuzz.distance import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.domain import ItemCandidate, MatchingMethod, RankedItem
from app.preprocessing import normalize_for_matching
from app.repository import ItemRepository


class InvalidSearchDescription(ValueError):
    """A descrição não contém termos para a busca após a normalização."""


def build_item_text(item: ItemCandidate, *, include_category: bool = False) -> str:
    # Combina apenas os campos escolhidos para a comparação textual
    return normalize_for_matching(
        " ".join(
            (item.name, item.description, item.location)
            + ((item.category_name,) if include_category else ())
        )
    )


class MatchingService:
    def __init__(
        self,
        repository: ItemRepository,
        method: MatchingMethod | str = MatchingMethod.HYBRID,
        alpha: float = 0.5,
        beta: float = 0.5,
        include_category: bool = False,
    ) -> None:
        if alpha < 0 or beta < 0 or abs((alpha + beta) - 1.0) > 1e-9:
            raise ValueError("alpha e beta devem ser não negativos e somar 1")
        self._repository = repository
        self._method = MatchingMethod(method)
        self._alpha = alpha
        self._beta = beta
        self._include_category = include_category
        self._index_lock = Lock()
        self._collection_signature: tuple[tuple[int, str], ...] | None = None
        self._vectorizer: TfidfVectorizer | None = None
        self._item_matrix = None

    def _cosine_scores(
        self,
        query: str,
        signature: tuple[tuple[int, str], ...],
        timings: dict[str, float | int] | None = None,
    ) -> np.ndarray:
        with self._index_lock:
            # Reajusta o TF-IDF somente quando IDs ou textos dos candidatos mudam
            if signature != self._collection_signature:
                fit_started = perf_counter() if timings is not None else None
                item_texts = [item_text for _, item_text in signature]
                vectorizer = TfidfVectorizer()
                try:
                    item_matrix = vectorizer.fit_transform(item_texts)
                except ValueError as error:
                    if "empty vocabulary" not in str(error):
                        raise
                    vectorizer = None
                    item_matrix = None

                self._collection_signature = signature
                self._vectorizer = vectorizer
                self._item_matrix = item_matrix
                if timings is not None and fit_started is not None:
                    timings["tfidf_fit_ms"] = (perf_counter() - fit_started) * 1000
                    timings["tfidf_refit"] = 1

            vectorizer = self._vectorizer
            item_matrix = self._item_matrix

        if vectorizer is None or item_matrix is None:
            return np.zeros(len(signature), dtype=float)

        # Compara a consulta com a matriz já ajustada aos itens ativos
        cosine_started = perf_counter() if timings is not None else None
        query_vector = vectorizer.transform([query])
        result = cosine_similarity(query_vector, item_matrix).ravel()
        if timings is not None and cosine_started is not None:
            timings["cosine_ms"] = (perf_counter() - cosine_started) * 1000
        return result

    def _final_score(
        self,
        cosine_score: float,
        levenshtein_score: float,
    ) -> float:
        if self._method is MatchingMethod.COSINE:
            return cosine_score
        if self._method is MatchingMethod.LEVENSHTEIN:
            return levenshtein_score
        return self._alpha * cosine_score + self._beta * levenshtein_score

    def search(
        self,
        description: str,
        top_k: int = 5,
        *,
        timings: dict[str, float | int] | None = None,
    ) -> list[RankedItem]:
        started = perf_counter() if timings is not None else None
        if timings is not None:
            timings.update(tfidf_fit_ms=0.0, tfidf_refit=0)
        query = normalize_for_matching(description)
        if not query:
            raise InvalidSearchDescription("A descrição não contém termos úteis para a busca")

        # Ordena por ID para manter o índice e os desempates reproduzíveis
        repository_started = perf_counter() if timings is not None else None
        items = sorted(self._repository.find_active_items(), key=lambda item: item.id)
        if timings is not None and repository_started is not None:
            timings["repository_ms"] = (perf_counter() - repository_started) * 1000
            timings["item_count"] = len(items)
        if not items:
            return []

        prepare_started = perf_counter() if timings is not None else None
        item_texts = [
            build_item_text(item, include_category=self._include_category) for item in items
        ]
        signature = tuple(
            (item.id, item_text) for item, item_text in zip(items, item_texts, strict=True)
        )
        if timings is not None and prepare_started is not None:
            timings["prepare_items_ms"] = (perf_counter() - prepare_started) * 1000
        cosine_scores = self._cosine_scores(query, signature, timings)

        ranking_started = perf_counter() if timings is not None else None
        ranked = []
        for item, item_text, cosine_score in zip(
            items, item_texts, cosine_scores, strict=True
        ):
            levenshtein_score = Levenshtein.normalized_similarity(query, item_text)
            final_score = self._final_score(
                float(cosine_score),
                float(levenshtein_score),
            )
            ranked.append(
                RankedItem(
                    item=item,
                    cosine_score=float(cosine_score),
                    levenshtein_score=float(levenshtein_score),
                    final_score=min(1.0, max(0.0, final_score)),
                )
            )

        # Prioriza maior escore e usa o ID como desempate estável
        ranked.sort(key=lambda result: (-result.final_score, result.item.id))
        if timings is not None and ranking_started is not None and started is not None:
            timings["ranking_ms"] = (perf_counter() - ranking_started) * 1000
            timings["total_ms"] = (perf_counter() - started) * 1000
        return ranked[:top_k]
