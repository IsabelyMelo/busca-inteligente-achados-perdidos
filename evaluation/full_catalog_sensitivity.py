"""Compara o ranking do teste v2 com 300 e 1.000 candidatos, sem recalibrar."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from math import isclose
from pathlib import Path

from app.domain import ItemCandidate
from app.matching import MatchingService
from evaluation.evaluate import FixedRepository, file_sha256, load_jsonl, score
from evaluation.validate import validate_dataset


DATASET = Path(__file__).resolve().parent / "v2"
METHODS = ("cosine", "levenshtein", "hybrid")


def rank(rows: list[dict], expected_id: int, method: str, alpha: float) -> int:
    ordered = sorted(rows, key=lambda row: (-score(row, method, alpha), int(row["item_id"])))
    return next(position for position, row in enumerate(ordered, 1) if int(row["item_id"]) == expected_id)


def summarize(ranks: list[int]) -> dict:
    count = len(ranks)
    return {
        "positive_queries": count,
        "hit_at_1_count": sum(value == 1 for value in ranks),
        "hit_at_1": sum(value == 1 for value in ranks) / count,
        "hit_at_5_count": sum(value <= 5 for value in ranks),
        "hit_at_5": sum(value <= 5 for value in ranks) / count,
        "mrr": sum(1 / value for value in ranks) / count,
    }


def run() -> dict:
    paths = {name: DATASET / name for name in ("items.jsonl", "queries.jsonl")}
    validate_dataset(paths["items.jsonl"], paths["queries.jsonl"], enforce_pilot_profile=False)
    frozen_path = DATASET / "test_results" / "summary.json"
    pairs_path = DATASET / "test_results" / "pairs.csv"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if {name: file_sha256(path) for name, path in paths.items()} != frozen["input_sha256"]:
        raise ValueError("Os dados diferem dos arquivos do teste congelado")
    if file_sha256(pairs_path) != frozen["output_sha256"]["pairs.csv"]:
        raise ValueError("Os pares do teste congelado foram alterados")
    if frozen["selection"]["field_selection"] != "without_category":
        raise ValueError("A configuração congelada usa outra composição de campos")
    if frozen["winner"]["method"] != "hybrid" or frozen["winner"]["alpha"] != 0.5:
        raise ValueError("A configuração híbrida congelada mudou")

    raw_items = load_jsonl(paths["items.jsonl"])
    raw_queries = load_jsonl(paths["queries.jsonl"])
    items = sorted(
        (
            ItemCandidate(
                id=row["item_id"], name=row["name"], description=row["description"],
                location=row["location"], category_name=row["category"],
                found_on=datetime.fromisoformat(row["found_on"]),
            )
            for row in raw_items if row["status"] == "ACTIVE"
        ),
        key=lambda item: item.id,
    )
    test_items = {item["item_id"] for item in raw_items if item["split"] == "test"}
    queries = sorted(
        (row for row in raw_queries if row["split"] == "test" and row["has_match"]),
        key=lambda row: row["query_id"],
    )
    if len(items) != 1000 or len(test_items) != 300 or len(queries) != 270:
        raise ValueError("Contagens de candidatos ou consultas inesperadas")
    if any(row["expected_item_id"] not in test_items for row in queries):
        raise ValueError("Item esperado fora do conjunto de teste")

    original: dict[str, list[dict]] = defaultdict(list)
    with pairs_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["expected_item_id"]:
                original[row["query_id"]].append(row)
    if set(original) != {query["query_id"] for query in queries}:
        raise ValueError("Consultas positivas diferem dos pares originais")
    if any(len(rows) != 300 for rows in original.values()):
        raise ValueError("O teste original não contém 300 candidatos por consulta")

    service = MatchingService(FixedRepository(items), include_category=False)
    rank_rows = []
    for query in queries:
        full_results = service.search(query["description"], top_k=len(items))
        full_rows = [
            {
                "item_id": result.item.id,
                "cosine_score": result.cosine_score,
                "levenshtein_score": result.levenshtein_score,
            }
            for result in full_results
        ]
        if len(full_rows) != len(items):
            raise ValueError("Busca não retornou todos os candidatos")
        for method in METHODS:
            alpha = frozen["per_method"][method]["alpha"]
            rank_rows.append({
                "query_id": query["query_id"],
                "expected_item_id": query["expected_item_id"],
                "method": method,
                "rank_300": rank(original[query["query_id"]], query["expected_item_id"], method, alpha),
                "rank_1000": rank(full_rows, query["expected_item_id"], method, alpha),
            })

    results = {}
    for method in METHODS:
        method_rows = [row for row in rank_rows if row["method"] == method]
        baseline = summarize([row["rank_300"] for row in method_rows])
        for metric in ("hit_at_1", "hit_at_5", "mrr"):
            if not isclose(baseline[metric], frozen["metrics"][method][metric], abs_tol=1e-12):
                raise ValueError(f"{method}: {metric} não reproduz o teste original")
        results[method] = {
            "300_candidates": baseline,
            "1000_candidates": summarize([row["rank_1000"] for row in method_rows]),
            "rank_worsened": sum(row["rank_1000"] > row["rank_300"] for row in method_rows),
            "rank_unchanged": sum(row["rank_1000"] == row["rank_300"] for row in method_rows),
            "rank_improved": sum(row["rank_1000"] < row["rank_300"] for row in method_rows),
        }

    ranks_path = DATASET / "full_catalog_ranks.csv"
    with ranks_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rank_rows[0]))
        writer.writeheader()
        writer.writerows(rank_rows)
    summary = {
        "kind": "post_test_full_catalog_sensitivity",
        "test_queries": 360,
        "positive_queries_ranked": len(queries),
        "catalogs": {"original_test": 300, "full_active": len(items)},
        "fields": frozen["selection"]["field_selection"],
        "per_method": frozen["per_method"],
        "source_sha256": {
            **{name: file_sha256(path) for name, path in paths.items()},
            "test_results/summary.json": file_sha256(frozen_path),
            "test_results/pairs.csv": file_sha256(pairs_path),
        },
        "ranks_sha256": file_sha256(ranks_path),
        "results": results,
    }
    (DATASET / "full_catalog_sensitivity.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    result = run()
    for method, values in result["results"].items():
        print(method, values["300_candidates"], values["1000_candidates"])
