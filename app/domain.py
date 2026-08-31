from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ItemCandidate:
    id: int
    name: str
    description: str
    location: str
    category_name: str
    found_on: datetime


@dataclass(frozen=True, slots=True)
class RankedItem:
    item: ItemCandidate
    cosine_score: float
    levenshtein_score: float
    final_score: float

