from typing import Protocol

from sqlalchemy import Engine, text

from app.domain import ItemCandidate


class ItemRepository(Protocol):
    def find_active_items(self) -> list[ItemCandidate]: ...


class MySQLItemRepository:
    """Consulta somente itens ativos; não executa operações de escrita."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_active_items(self) -> list[ItemCandidate]:
        statement = text(
            """
            SELECT
                i.id,
                i.name,
                i.description,
                i.location,
                i.foundOn,
                c.name AS category_name
            FROM item AS i
            INNER JOIN category AS c ON c.id = i.category_id
            WHERE i.status = :status
            ORDER BY i.id
            """
        )

        with self._engine.connect() as connection:
            rows = connection.execute(statement, {"status": "ACTIVE"}).mappings()
            return [
                ItemCandidate(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"] or "",
                    location=row["location"] or "",
                    category_name=row["category_name"],
                    found_on=row["foundOn"],
                )
                for row in rows
            ]

