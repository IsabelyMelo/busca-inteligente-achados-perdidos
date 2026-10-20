"""Conferências do conjunto sintético final congelado."""

import json
from collections import Counter
from pathlib import Path

import pytest

from evaluation.evaluate import select_records
from evaluation.generate_synthetic_data import (
    COLORS, FEMININE_COLORS, PLACES, PLACE_SHORT, PLURAL_COLORS,
)
from evaluation.validate import validate_dataset
from evaluation.finalize import load_development, manifest
from evaluation.generate_load_sql import render


DATASET = Path(__file__).parents[1] / "evaluation" / "final"


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_dataset_is_structurally_valid():
    assert {path.name for path in DATASET.iterdir()} >= {
        "README.md", "items.jsonl", "queries.jsonl", "manifest.json", "load.sql", "verify_load.sql",
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


def test_manifest_and_development_selection():
    saved = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    assert manifest(DATASET) == saved
    assert saved["sql"]["target_schema"] == "matching_development"
    assert saved["sql"]["status"] == "generated_for_loaded_development_schema"
    items, queries = load_development(DATASET)
    assert (len(items), len(queries)) == (700, 840)
    assert {row["reference_id"] for row in items}.isdisjoint(
        {row["reference_id"] for row in _read_jsonl(DATASET / "items.jsonl") if row["split"] == "test"}
    )
    assert all(row["split"] == "development" for row in [*items, *queries])


def test_evaluator_selects_only_development_and_blocks_test():
    items, queries, _ = select_records(DATASET, "development")
    assert (len(items), len(queries)) == (700, 840)
    assert {item.id for item in items} == set(manifest(DATASET)["groups"]["development"]["item_ids"])
    assert {query["query_id"] for query in queries} == set(manifest(DATASET)["groups"]["development"]["query_ids"])
    with pytest.raises(ValueError, match="teste não está disponível"):
        select_records(DATASET, "test")


def test_sql_matches_frozen_dataset():
    load_sql, verify_sql = render(DATASET)
    assert (DATASET / "load.sql").read_text(encoding="utf-8") == load_sql
    assert (DATASET / "verify_load.sql").read_text(encoding="utf-8") == verify_sql
    assert "`matching_development`.`item`" in load_sql
    assert "`matching_development`.`category`" in load_sql
    assert "`matching_development`.`item`" in verify_sql
    assert "queries" not in load_sql.lower()
