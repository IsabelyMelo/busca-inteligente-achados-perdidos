"""Ablação retrospectiva da lista de equivalências no teste congelado da v2."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from app.preprocessing import MATCHING_ALIASES
from evaluation.evaluate import metrics, score_pairs, select_records


DATASET = Path(__file__).resolve().parent / "v2"
TEST = DATASET / "test_results"
OUTPUT = DATASET / "synonym_ablation.json"
FIELDS = ("hit_at_1", "hit_at_5", "mrr", "precision", "recall", "f1")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary = json.loads((TEST / "summary.json").read_text(encoding="utf-8"))
    if summary["winner"] != {"method": "hybrid", "alpha": 0.5, "beta": 0.5}:
        raise ValueError("A configuração congelada do teste não é a esperada")
    if summary["selection"]["field_selection"] != "without_category":
        raise ValueError("A ablação pressupõe o texto sem categoria")
    for name, digest in summary["input_sha256"].items():
        if sha256(DATASET / name) != digest:
            raise ValueError(f"{name} mudou após o teste")
    pairs_path = TEST / "pairs.csv"
    if sha256(pairs_path) != summary["output_sha256"]["pairs.csv"]:
        raise ValueError("Os pares originais do teste foram alterados")

    with pairs_path.open(encoding="utf-8", newline="") as stream:
        baseline_rows = list(csv.DictReader(stream))
    with_aliases = metrics(baseline_rows, "hybrid", 0.5, 0.4)
    for field in FIELDS:
        if abs(with_aliases[field] - summary["metrics"]["hybrid"][field]) > 1e-12:
            raise ValueError(f"A métrica original não foi reproduzida: {field}")

    items, queries, _validation = select_records(DATASET, "test", allow_test=True)
    if len(items) != 300 or len(queries) != 360:
        raise ValueError("O split de teste não corresponde ao original")
    alias_count = len(MATCHING_ALIASES)
    if alias_count != 10:
        raise ValueError("A lista de equivalências foi alterada")
    with patch.dict(MATCHING_ALIASES, clear=True):
        without_rows = score_pairs(items, queries, include_category=False)
    if len(without_rows) != len(baseline_rows):
        raise ValueError("A ablação não pontuou todos os pares do teste")
    without_aliases = metrics(without_rows, "hybrid", 0.5, 0.4)

    result = {
        "analysis": "retrospective sensitivity analysis on frozen test set; no reselection",
        "test_queries": len(queries),
        "positive_queries": with_aliases["positive_queries"],
        "test_candidates": len(items),
        "method": "hybrid",
        "alpha": 0.5,
        "beta": 0.5,
        "fields": "name, description, location",
        "alias_count": alias_count,
        "source_sha256": {
            "items.jsonl": sha256(DATASET / "items.jsonl"),
            "queries.jsonl": sha256(DATASET / "queries.jsonl"),
            "test_results/pairs.csv": sha256(pairs_path),
            "app/preprocessing.py": sha256(DATASET.parent.parent / "app" / "preprocessing.py"),
            "app/matching.py": sha256(DATASET.parent.parent / "app" / "matching.py"),
        },
        "with_aliases": {field: with_aliases[field] for field in FIELDS},
        "without_aliases": {field: without_aliases[field] for field in FIELDS},
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
