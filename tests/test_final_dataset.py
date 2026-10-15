"""Conferências do conjunto sintético ainda em revisão."""

import json
from collections import Counter
from pathlib import Path

from evaluation.generate_synthetic_data import (
    COLORS, FEMININE_COLORS, PLACES, PLACE_SHORT, PLURAL_COLORS,
)
from evaluation.validate import validate_dataset


DATASET = Path(__file__).parents[1] / "evaluation" / "final"


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_dataset_is_structurally_valid():
    assert {path.name for path in DATASET.iterdir()} == {
        "README.md", "items.jsonl", "queries.jsonl",
    }
    report = validate_dataset(
        DATASET / "items.jsonl", DATASET / "queries.jsonl",
        enforce_pilot_profile=False,
    )
    assert (report.item_count, report.query_count) == (1000, 1200)
    assert (report.positive_count, report.negative_count) == (1000, 200)

    items = _read_jsonl(DATASET / "items.jsonl")
    queries = _read_jsonl(DATASET / "queries.jsonl")
    assert Counter(item["category"] for item in items) == {
        category: 100 for category in {item["category"] for item in items}
    }
    assert len(PLACES) == len(PLACE_SHORT) == 13
    assert {item["location"] for item in items} == set(PLACES)
    locations_by_id = {item["item_id"]: item["location"] for item in items}
    for place, short in zip(PLACES, PLACE_SHORT):
        assert any(
            query["has_match"]
            and "abbreviation" in query["noise_types"]
            and locations_by_id[query["expected_item_id"]] == place
            and short in query["description"]
            for query in queries
        )
    assert len({item["item_id"] for item in items}) == len(items)
    assert len({item["name"] for item in items}) == len(items)
    valid_colors = set(COLORS + FEMININE_COLORS + PLURAL_COLORS)
    assert all(
        any(item["name"].endswith(f" {color}") for color in valid_colors)
        for item in items
    )
    names_by_id = {item["item_id"]: item["name"] for item in items}
    assert names_by_id[1001] == "Celular preto"
    assert names_by_id[1094] == "Caixa de som verde-escura"
    assert names_by_id[1101] == "Óculos de grau pretos"
    assert names_by_id[1109] == "Óculos de grau marrons"
    assert names_by_id[1498] == "Pasta de documentos vazia amarela"
    assert len({query["query_id"] for query in queries}) == len(queries)
    assert "provenance_id" not in items[0]
    assert "provenance_id" not in queries[0]
