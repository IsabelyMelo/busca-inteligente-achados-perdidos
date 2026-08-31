from datetime import datetime

from pydantic import BaseModel, Field

from app.domain import RankedItem


class SearchRequest(BaseModel):
    description: str = Field(min_length=10, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class MatchItem(BaseModel):
    item_id: int
    name: str
    description: str
    location: str
    category: str
    found_on: datetime
    cosine_score: float
    levenshtein_score: float
    final_score: float

    @classmethod
    def from_ranked_item(cls, result: RankedItem) -> "MatchItem":
        return cls(
            item_id=result.item.id,
            name=result.item.name,
            description=result.item.description,
            location=result.item.location,
            category=result.item.category_name,
            found_on=result.item.found_on,
            cosine_score=round(result.cosine_score, 6),
            levenshtein_score=round(result.levenshtein_score, 6),
            final_score=round(result.final_score, 6),
        )


class SearchResponse(BaseModel):
    returned_count: int
    processing_time_ms: float
    matches: list[MatchItem]
