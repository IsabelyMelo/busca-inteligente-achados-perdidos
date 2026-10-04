import json
from copy import deepcopy
from pathlib import Path

import pytest

import evaluation.validate as validator_module
from evaluation.validate import (
    ITEM_FIELDS,
    QUERY_FIELDS,
    DatasetValidationError,
    validate_dataset,
)


PILOT_ROOT = Path(__file__).parents[1] / "evaluation" / "pilot" / "v0.1.0"
SCHEMA_ROOT = Path(__file__).parents[1] / "evaluation" / "schemas" / "v1"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _patch_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[dict], list[dict], dict]:
    items = deepcopy(_read_jsonl(PILOT_ROOT / "items.jsonl"))
    queries = deepcopy(_read_jsonl(PILOT_ROOT / "queries.jsonl"))
    provenance = json.loads(
        (PILOT_ROOT / "provenance.json").read_text(encoding="utf-8")
    )

    def load_jsonl(path: Path, label: str, errors: list[str]) -> list[dict]:
        del path, errors
        return items if label == "itens" else queries

    monkeypatch.setattr(validator_module, "_load_jsonl", load_jsonl)
    monkeypatch.setattr(
        validator_module,
        "_load_provenance",
        lambda path, errors: provenance,
    )
    return items, queries, provenance


def _validate_patched_dataset() -> None:
    validate_dataset(Path("items.jsonl"), Path("queries.jsonl"), Path("provenance.json"))


def test_pilot_dataset_is_valid_and_has_expected_distribution() -> None:
    report = validate_dataset(
        PILOT_ROOT / "items.jsonl",
        PILOT_ROOT / "queries.jsonl",
        PILOT_ROOT / "provenance.json",
    )

    assert report.item_count == 20
    assert report.query_count == 40
    assert report.positive_count == 30
    assert report.negative_count == 10
    assert report.difficulty_counts == {"easy": 20, "hard": 10, "no_match": 10}
    assert report.splits == ("pilot_development",)
    assert report.human_review_statuses == ("approved",)


@pytest.mark.parametrize(
    ("filename", "expected_fields"),
    [
        ("item.schema.json", ITEM_FIELDS),
        ("query.schema.json", QUERY_FIELDS),
    ],
)
def test_versioned_schema_is_parseable_and_matches_validator_fields(
    filename: str, expected_fields: set[str]
) -> None:
    schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == expected_fields
    assert set(schema["properties"]) == expected_fields


def test_validator_rejects_positive_with_unknown_expected_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queries, _ = _patch_dataset(monkeypatch)
    queries[0]["expected_item_id"] = 999

    with pytest.raises(DatasetValidationError, match="expected_item_id não existe"):
        _validate_patched_dataset()


def test_validator_rejects_negative_pointing_to_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queries, _ = _patch_dataset(monkeypatch)
    negative = queries[-1]
    negative["reference_id"] = "ref-phone-samsung-a32"
    negative["expected_item_id"] = 1

    with pytest.raises(DatasetValidationError) as captured:
        _validate_patched_dataset()

    assert any("negativo exige expected_item_id nulo" in error for error in captured.value.errors)
    assert any("negativo referencia um item candidato" in error for error in captured.value.errors)


def test_validator_rejects_duplicate_query_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queries, _ = _patch_dataset(monkeypatch)
    queries[1]["query_id"] = queries[0]["query_id"]

    with pytest.raises(DatasetValidationError, match="query_id duplicado"):
        _validate_patched_dataset()


def test_validator_rejects_reference_leakage_between_splits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queries, _ = _patch_dataset(monkeypatch)
    queries[1]["split"] = "development"

    with pytest.raises(DatasetValidationError) as captured:
        _validate_patched_dataset()

    assert any("split difere do item esperado" in error for error in captured.value.errors)
    assert any("reference_id presente em mais de um split" in error for error in captured.value.errors)


def test_validator_rejects_undocumented_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items, _, _ = _patch_dataset(monkeypatch)
    items[0]["provenance_id"] = "prov-unknown"

    with pytest.raises(DatasetValidationError, match="proveniência ausente"):
        _validate_patched_dataset()


def test_validator_rejects_unknown_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queries, _ = _patch_dataset(monkeypatch)
    queries[0]["score"] = 1.0

    with pytest.raises(DatasetValidationError, match="campos desconhecidos: score"):
        _validate_patched_dataset()
