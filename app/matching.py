from threading import Lock

import numpy as np
from rapidfuzz.distance import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.domain import ItemCandidate, MatchingMethod, RankedItem
from app.preprocessing import normalize_text
from app.repository import ItemRepository


def build_item_text(item: ItemCandidate, *, include_category: bool = False) -> str:
    return normalize_text(
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
    ) -> np.ndarray:
        with self._index_lock:
            if signature != self._collection_signature:
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

            vectorizer = self._vectorizer
            item_matrix = self._item_matrix

        if vectorizer is None or item_matrix is None:
            return np.zeros(len(signature), dtype=float)

        query_vector = vectorizer.transform([query])
        return cosine_similarity(query_vector, item_matrix).ravel()

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

    def search(self, description: str, top_k: int = 5) -> list[RankedItem]:
        query = normalize_text(description)
        if not query:
            raise ValueError("A descrição não contém termos úteis para a busca")

        items = sorted(self._repository.find_active_items(), key=lambda item: item.id)
        if not items:
            return []

        item_texts = [
            build_item_text(item, include_category=self._include_category) for item in items
        ]
        signature = tuple(
            (item.id, item_text) for item, item_text in zip(items, item_texts, strict=True)
        )
        cosine_scores = self._cosine_scores(query, signature)

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

        ranked.sort(key=lambda result: (-result.final_score, result.item.id))
        return ranked[:top_k]
