from app.domain import ItemCandidate


class FakeItemRepository:
    def __init__(self, items: list[ItemCandidate]) -> None:
        self._items = items

    def find_active_items(self) -> list[ItemCandidate]:
        return self._items

