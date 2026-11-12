"""Conta a presença das formas da lista de equivalências nas bases v1 e v2."""

from __future__ import annotations

import json
from pathlib import Path

from app.preprocessing import MATCHING_ALIASES, normalize_text


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "v2" / "alias_occurrences.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def contains_alias(text: str, alias: tuple[str, ...]) -> bool:
    tokens = normalize_text(text).split()
    return any(tuple(tokens[index : index + len(alias)]) == alias for index in range(len(tokens)))


def main() -> None:
    result = {}
    for version in ("v1", "v2"):
        folder = ROOT / version
        items = read_jsonl(folder / "items.jsonl")
        queries = read_jsonl(folder / "queries.jsonl")
        version_counts = {}
        for alias, replacement in MATCHING_ALIASES.items():
            version_counts[" ".join(alias)] = {
                "canonical": " ".join(replacement),
                "items": sum(
                    contains_alias(" ".join(str(item.get(field, "")) for field in ("name", "description", "location")), alias)
                    for item in items
                ),
                "queries": sum(contains_alias(query["description"], alias) for query in queries),
            }
        result[version] = version_counts
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
