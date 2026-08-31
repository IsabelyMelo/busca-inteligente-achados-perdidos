from rapidfuzz.distance import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.domain import ItemCandidate, RankedItem
from app.preprocessing import normalize_text
from app.repository import ItemRepository


def build_item_text(item: ItemCandidate) -> str:
    return normalize_text(
        " ".join((item.name, item.description, item.location, item.category_name))
    )


class MatchingService:
    def __init__(
        self,
        repository: ItemRepository,
        alpha: float = 0.5,
        beta: float = 0.5,
    ) -> None:
        if alpha < 0 or beta < 0 or abs((alpha + beta) - 1.0) > 1e-9:
            raise ValueError("alpha e beta devem ser não negativos e somar 1")
        self._repository = repository
        self._alpha = alpha
        self._beta = beta

    def search(self, description: str, top_k: int = 5) -> list[RankedItem]:
        query = normalize_text(description)
        if not query:
            raise ValueError("A descrição não contém termos úteis para a busca")

        items = self._repository.find_active_items()
        if not items:
            return []

        item_texts = [build_item_text(item) for item in items]
        corpus = [query, *item_texts]
        matrix = TfidfVectorizer().fit_transform(corpus)
        cosine_scores = cosine_similarity(matrix[0:1], matrix[1:]).ravel()

        ranked = []
        for item, item_text, cosine_score in zip(
            items, item_texts, cosine_scores, strict=True
        ):
            levenshtein_score = Levenshtein.normalized_similarity(query, item_text)
            final_score = (
                self._alpha * float(cosine_score)
                + self._beta * float(levenshtein_score)
            )
            ranked.append(
                RankedItem(
                    item=item,
                    cosine_score=float(cosine_score),
                    levenshtein_score=float(levenshtein_score),
                    final_score=final_score,
                )
            )

        ranked.sort(key=lambda result: (-result.final_score, result.item.id))
        return ranked[:top_k]

