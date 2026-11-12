"""Extrai casos de erro do ranking híbrido no teste congelado da v2."""

from __future__ import annotations

import csv
import hashlib
import json
from itertools import groupby
from pathlib import Path

from evaluation.evaluate import score


DATASET = Path(__file__).resolve().parent / "v2"
PAIRS = DATASET / "test_results" / "pairs.csv"
SUMMARY = DATASET / "test_results" / "summary.json"
OUTPUT = DATASET / "error_cases.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def item_view(item: dict) -> dict:
    return {key: item[key] for key in ("item_id", "name", "description", "location", "category")}


def main() -> None:
    frozen = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if sha256(PAIRS) != frozen["output_sha256"]["pairs.csv"]:
        raise ValueError("Pares do teste foram alterados")
    for name, digest in frozen["input_sha256"].items():
        if sha256(DATASET / name) != digest:
            raise ValueError(f"Fonte do teste alterada: {name}")
    items = {row["item_id"]: row for row in jsonl(DATASET / "items.jsonl")}
    queries = {row["query_id"]: row for row in jsonl(DATASET / "queries.jsonl")}
    cases = []
    with PAIRS.open(encoding="utf-8", newline="") as stream:
        for query_id, group in groupby(csv.DictReader(stream), key=lambda row: row["query_id"]):
            query = queries[query_id]
            if not query["has_match"]:
                continue
            ordered = sorted(
                group,
                key=lambda row: (-score(row, "hybrid", 0.5), int(row["item_id"])),
            )
            expected_id = query["expected_item_id"]
            rank = next(index for index, row in enumerate(ordered, 1)
                        if int(row["item_id"]) == expected_id)
            if rank == 1:
                continue
            cases.append({
                "query_id": query_id,
                "query_text": query["description"],
                "reference_id": query["reference_id"],
                "noise_types": query["noise_types"],
                "expected_rank": rank,
                "expected_item": item_view(items[expected_id]),
                "top_5": [
                    {"item": item_view(items[int(row["item_id"])]),
                     "score": score(row, "hybrid", 0.5)}
                    for row in ordered[:5]
                ],
            })
    if len(cases) != 39 or sum(case["expected_rank"] > 5 for case in cases) != 14:
        raise ValueError("Contagem de erros diverge do resumo do teste")
    result = {
        "source_sha256": {"pairs.csv": sha256(PAIRS),
                          "items.jsonl": sha256(DATASET / "items.jsonl"),
                          "queries.jsonl": sha256(DATASET / "queries.jsonl")},
        "hit_at_1_errors": len(cases),
        "outside_top_5": sum(case["expected_rank"] > 5 for case in cases),
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cases)} erros de Hit@1, {result['outside_top_5']} fora do top 5: {OUTPUT}")


if __name__ == "__main__":
    main()
