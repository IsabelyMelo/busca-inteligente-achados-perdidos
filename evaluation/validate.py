from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SPLITS = {"pilot_development", "development", "test"}
DIFFICULTIES = {"easy", "hard", "no_match"}
NOISE_TYPES = {
    "abbreviation",
    "brand_model",
    "exact_attributes",
    "generic",
    "location_cue",
    "omission",
    "reordered",
    "synonym",
    "typo",
}
ITEM_FIELDS = {
    "schema_version",
    "item_id",
    "reference_id",
    "name",
    "description",
    "location",
    "category",
    "found_on",
    "status",
    "split",
    "provenance_id",
}
QUERY_FIELDS = {
    "schema_version",
    "query_id",
    "reference_id",
    "description",
    "has_match",
    "expected_item_id",
    "split",
    "difficulty",
    "noise_types",
    "provenance_id",
}
REFERENCE_PATTERN = re.compile(r"^ref-[a-z0-9-]+$")
QUERY_PATTERN = re.compile(r"^q-[0-9]{3,}$")
PROVENANCE_PATTERN = re.compile(r"^prov-[a-z0-9-]+$")
PILOT_REQUIRED_NOISE = {
    "abbreviation",
    "brand_model",
    "exact_attributes",
    "generic",
    "location_cue",
    "omission",
    "synonym",
    "typo",
}


class DatasetValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True, slots=True)
class ValidationReport:
    item_count: int
    query_count: int
    positive_count: int
    negative_count: int
    difficulty_counts: dict[str, int]
    noise_counts: dict[str, int]
    splits: tuple[str, ...]
    human_review_statuses: tuple[str, ...]


def _load_jsonl(path: Path, label: str, errors: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        errors.append(f"{label}: não foi possível ler {path}: {error}")
        return records

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            errors.append(f"{label}:{line_number}: linha vazia não é permitida")
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"{label}:{line_number}: JSON inválido: {error.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{label}:{line_number}: o registro deve ser um objeto")
            continue
        records.append(value)
    return records


def _load_provenance(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        errors.append(f"proveniência: não foi possível ler {path}: {error}")
        return {}
    except json.JSONDecodeError as error:
        errors.append(f"proveniência: JSON inválido: {error.msg}")
        return {}
    if not isinstance(value, dict):
        errors.append("proveniência: o documento deve ser um objeto")
        return {}
    return value


def _validate_exact_fields(
    record: dict[str, Any], expected: set[str], context: str, errors: list[str]
) -> None:
    missing = sorted(expected - record.keys())
    extra = sorted(record.keys() - expected)
    if missing:
        errors.append(f"{context}: campos obrigatórios ausentes: {', '.join(missing)}")
    if extra:
        errors.append(f"{context}: campos desconhecidos: {', '.join(extra)}")


def _is_positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _validate_common(record: dict[str, Any], context: str, errors: list[str]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{context}: schema_version deve ser {SCHEMA_VERSION}")
    reference_id = record.get("reference_id")
    if not isinstance(reference_id, str) or not REFERENCE_PATTERN.fullmatch(reference_id):
        errors.append(f"{context}: reference_id inválido")
    if record.get("split") not in SPLITS:
        errors.append(f"{context}: split inválido")
    provenance_id = record.get("provenance_id")
    if not isinstance(provenance_id, str) or not PROVENANCE_PATTERN.fullmatch(
        provenance_id
    ):
        errors.append(f"{context}: provenance_id inválido")


def _validate_item(record: dict[str, Any], index: int, errors: list[str]) -> None:
    context = f"item[{index}]"
    _validate_exact_fields(record, ITEM_FIELDS, context, errors)
    _validate_common(record, context, errors)
    if not _is_positive_integer(record.get("item_id")):
        errors.append(f"{context}: item_id deve ser inteiro positivo")
    for field in ("name", "description", "location", "category"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{context}: {field} deve ser texto não vazio")
    found_on = record.get("found_on")
    if not isinstance(found_on, str):
        errors.append(f"{context}: found_on deve ser data-hora textual")
    else:
        try:
            parsed = datetime.fromisoformat(found_on)
            if parsed.tzinfo is None:
                errors.append(f"{context}: found_on deve incluir fuso horário")
        except ValueError:
            errors.append(f"{context}: found_on não é uma data-hora ISO 8601 válida")
    if record.get("status") != "ACTIVE":
        errors.append(f"{context}: somente status ACTIVE é permitido")


def _validate_query(record: dict[str, Any], index: int, errors: list[str]) -> None:
    context = f"consulta[{index}]"
    _validate_exact_fields(record, QUERY_FIELDS, context, errors)
    _validate_common(record, context, errors)
    query_id = record.get("query_id")
    if not isinstance(query_id, str) or not QUERY_PATTERN.fullmatch(query_id):
        errors.append(f"{context}: query_id inválido")
    description = record.get("description")
    if not isinstance(description, str) or not 10 <= len(description) <= 1000:
        errors.append(f"{context}: description deve ter entre 10 e 1000 caracteres")
    has_match = record.get("has_match")
    if not isinstance(has_match, bool):
        errors.append(f"{context}: has_match deve ser booleano")
    expected_item_id = record.get("expected_item_id")
    difficulty = record.get("difficulty")
    if difficulty not in DIFFICULTIES:
        errors.append(f"{context}: difficulty inválida")
    if has_match is True:
        if not _is_positive_integer(expected_item_id):
            errors.append(f"{context}: positivo exige expected_item_id inteiro")
        if difficulty not in {"easy", "hard"}:
            errors.append(f"{context}: positivo exige difficulty easy ou hard")
    elif has_match is False:
        if expected_item_id is not None:
            errors.append(f"{context}: negativo exige expected_item_id nulo")
        if difficulty != "no_match":
            errors.append(f"{context}: negativo exige difficulty no_match")
    noise_types = record.get("noise_types")
    if not isinstance(noise_types, list) or not noise_types:
        errors.append(f"{context}: noise_types deve ser lista não vazia")
    elif any(not isinstance(value, str) or value not in NOISE_TYPES for value in noise_types):
        errors.append(f"{context}: noise_types contém valor inválido")
    elif len(noise_types) != len(set(noise_types)):
        errors.append(f"{context}: noise_types não pode conter duplicatas")


def _duplicates(values: list[Any]) -> set[Any]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _validate_relationships(
    items: list[dict[str, Any]], queries: list[dict[str, Any]], errors: list[str]
) -> None:
    item_ids = [record.get("item_id") for record in items]
    query_ids = [record.get("query_id") for record in queries]
    item_references = [record.get("reference_id") for record in items]
    for label, values in (
        ("item_id", item_ids),
        ("query_id", query_ids),
        ("reference_id de item", item_references),
    ):
        duplicates = sorted(str(value) for value in _duplicates(values))
        if duplicates:
            errors.append(f"{label} duplicado: {', '.join(duplicates)}")

    duplicate_items = sorted(
        value
        for value in _duplicates(
            [_normalized_text(record.get("name")) + "|" + _normalized_text(record.get("description")) for record in items]
        )
        if value
    )
    if duplicate_items:
        errors.append("itens com nome e descrição duplicados")
    duplicate_queries = sorted(
        value
        for value in _duplicates(
            [_normalized_text(record.get("description")) for record in queries]
        )
        if value
    )
    if duplicate_queries:
        errors.append("consultas com descrição duplicada")

    items_by_id = {
        record["item_id"]: record
        for record in items
        if _is_positive_integer(record.get("item_id"))
    }
    item_reference_set = {
        value for value in item_references if isinstance(value, str)
    }
    for record in queries:
        query_id = record.get("query_id", "desconhecida")
        if record.get("has_match") is True:
            target = items_by_id.get(record.get("expected_item_id"))
            if target is None:
                errors.append(f"{query_id}: expected_item_id não existe nos itens")
            elif target.get("reference_id") != record.get("reference_id"):
                errors.append(f"{query_id}: reference_id difere do item esperado")
            elif target.get("split") != record.get("split"):
                errors.append(f"{query_id}: split difere do item esperado")
        elif record.get("has_match") is False and record.get("reference_id") in item_reference_set:
            errors.append(f"{query_id}: negativo referencia um item candidato existente")

    reference_splits: dict[Any, set[Any]] = defaultdict(set)
    for record in [*items, *queries]:
        reference_splits[record.get("reference_id")].add(record.get("split"))
    leaking = sorted(
        str(reference_id)
        for reference_id, splits in reference_splits.items()
        if len(splits) > 1
    )
    if leaking:
        errors.append(f"reference_id presente em mais de um split: {', '.join(leaking)}")


def _validate_provenance(
    provenance: dict[str, Any],
    records: list[dict[str, Any]],
    errors: list[str],
) -> tuple[str, ...]:
    entries = provenance.get("provenance_records")
    if not isinstance(entries, list) or not entries:
        errors.append("proveniência: provenance_records deve ser lista não vazia")
        return ()
    known_ids: set[str] = set()
    statuses: list[str] = []
    for index, entry in enumerate(entries, start=1):
        context = f"proveniência[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{context}: entrada deve ser objeto")
            continue
        provenance_id = entry.get("provenance_id")
        if not isinstance(provenance_id, str) or not PROVENANCE_PATTERN.fullmatch(
            provenance_id
        ):
            errors.append(f"{context}: provenance_id inválido")
        elif provenance_id in known_ids:
            errors.append(f"{context}: provenance_id duplicado")
        else:
            known_ids.add(provenance_id)
        for field in ("created_on", "method", "tool", "model", "prompt_summary", "source_data"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{context}: {field} deve ser texto não vazio")
        for field in ("corrections", "discarded_cases"):
            if not isinstance(entry.get(field), list):
                errors.append(f"{context}: {field} deve ser lista")
        human_review = entry.get("human_review")
        if not isinstance(human_review, dict):
            errors.append(f"{context}: human_review deve ser objeto")
            continue
        status = human_review.get("status")
        if status not in {"pending", "approved", "changes_requested"}:
            errors.append(f"{context}: status de revisão humana inválido")
        else:
            statuses.append(status)
        if not isinstance(human_review.get("scope"), str) or not human_review["scope"].strip():
            errors.append(f"{context}: escopo da revisão humana deve ser documentado")

    referenced_ids = {
        record.get("provenance_id")
        for record in records
        if isinstance(record.get("provenance_id"), str)
    }
    missing = sorted(referenced_ids - known_ids)
    if missing:
        errors.append(f"proveniência ausente para: {', '.join(missing)}")
    return tuple(sorted(set(statuses)))


def _validate_pilot_profile(
    items: list[dict[str, Any]], queries: list[dict[str, Any]], errors: list[str]
) -> None:
    if not 30 <= len(queries) <= 50:
        errors.append("piloto deve conter entre 30 e 50 consultas")
    if not items:
        errors.append("piloto deve conter itens candidatos")
    if any(record.get("split") != "pilot_development" for record in [*items, *queries]):
        errors.append("piloto só pode usar o split pilot_development")
    positive_count = sum(record.get("has_match") is True for record in queries)
    negative_count = sum(record.get("has_match") is False for record in queries)
    if positive_count == 0 or negative_count < 5:
        errors.append("piloto exige positivos e pelo menos cinco negativos")
    present_difficulties = {record.get("difficulty") for record in queries}
    missing_difficulties = {"easy", "hard", "no_match"} - present_difficulties
    if missing_difficulties:
        errors.append(
            "piloto sem dificuldades obrigatórias: " + ", ".join(sorted(missing_difficulties))
        )
    present_noise = {
        noise
        for record in queries
        if isinstance(record.get("noise_types"), list)
        for noise in record["noise_types"]
        if isinstance(noise, str)
    }
    missing_noise = PILOT_REQUIRED_NOISE - present_noise
    if missing_noise:
        errors.append("piloto sem ruídos obrigatórios: " + ", ".join(sorted(missing_noise)))


def validate_dataset(
    items_path: Path,
    queries_path: Path,
    provenance_path: Path,
    *,
    enforce_pilot_profile: bool = True,
) -> ValidationReport:
    errors: list[str] = []
    items = _load_jsonl(items_path, "itens", errors)
    queries = _load_jsonl(queries_path, "consultas", errors)
    provenance = _load_provenance(provenance_path, errors)

    for index, record in enumerate(items, start=1):
        _validate_item(record, index, errors)
    for index, record in enumerate(queries, start=1):
        _validate_query(record, index, errors)
    _validate_relationships(items, queries, errors)
    human_review_statuses = _validate_provenance(
        provenance, [*items, *queries], errors
    )
    if enforce_pilot_profile:
        _validate_pilot_profile(items, queries, errors)

    if errors:
        raise DatasetValidationError(errors)

    difficulty_counts = Counter(record["difficulty"] for record in queries)
    noise_counts = Counter(
        noise for record in queries for noise in record["noise_types"]
    )
    return ValidationReport(
        item_count=len(items),
        query_count=len(queries),
        positive_count=sum(record["has_match"] for record in queries),
        negative_count=sum(not record["has_match"] for record in queries),
        difficulty_counts=dict(sorted(difficulty_counts.items())),
        noise_counts=dict(sorted(noise_counts.items())),
        splits=tuple(sorted({record["split"] for record in [*items, *queries]})),
        human_review_statuses=human_review_statuses,
    )


def _default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parent / "pilot" / "v0.1.0"
    return root / "items.jsonl", root / "queries.jsonl", root / "provenance.json"


def main() -> int:
    default_items, default_queries, default_provenance = _default_paths()
    parser = argparse.ArgumentParser(description="Valida um dataset de avaliação.")
    parser.add_argument("--items", type=Path, default=default_items)
    parser.add_argument("--queries", type=Path, default=default_queries)
    parser.add_argument("--provenance", type=Path, default=default_provenance)
    parser.add_argument(
        "--no-pilot-profile",
        action="store_true",
        help="Valida o contrato geral sem exigir a distribuição do piloto.",
    )
    arguments = parser.parse_args()
    try:
        report = validate_dataset(
            arguments.items,
            arguments.queries,
            arguments.provenance,
            enforce_pilot_profile=not arguments.no_pilot_profile,
        )
    except DatasetValidationError as error:
        print("Dataset inválido:")
        for message in error.errors:
            print(f"- {message}")
        return 1

    print("Dataset válido")
    print(f"Itens: {report.item_count}")
    print(
        f"Consultas: {report.query_count} "
        f"({report.positive_count} positivas, {report.negative_count} negativas)"
    )
    print(f"Dificuldades: {report.difficulty_counts}")
    print(f"Ruídos: {report.noise_counts}")
    print(f"Splits: {', '.join(report.splits)}")
    print(f"Revisão humana: {', '.join(report.human_review_statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
