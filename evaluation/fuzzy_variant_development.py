"""Compara alternativas ao Levenshtein no desenvolvimento congelado da v2."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from itertools import groupby
from pathlib import Path

from rapidfuzz import fuzz

from app.domain import ItemCandidate
from app.matching import build_item_text
from app.preprocessing import normalize_for_matching


DATASET = Path(__file__).resolve().parent / "v2"
RESULTS = DATASET / "results"
OUTPUT = DATASET / "fuzzy_variant_development.json"
VARIANTS = ("cosine", "levenshtein", "token_set_ratio", "partial_ratio",
            "hybrid_original", "hybrid_token_set", "hybrid_partial")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def summarize(ranks: list[int]) -> dict:
    return {
        "positive_queries": len(ranks),
        "hit_at_1_count": sum(rank == 1 for rank in ranks),
        "hit_at_1": sum(rank == 1 for rank in ranks) / len(ranks),
        "hit_at_5_count": sum(rank <= 5 for rank in ranks),
        "hit_at_5": sum(rank <= 5 for rank in ranks) / len(ranks),
        "mrr": sum(1 / rank for rank in ranks) / len(ranks),
    }


def main() -> None:
    summary_path = RESULTS / "summary.json"
    pairs_path = RESULTS / "pairs.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["split"] != "development" or summary["field_ablation"]["selected"] != "without_category":
        raise ValueError("Configuração de desenvolvimento inesperada")
    for name in ("items.jsonl", "queries.jsonl"):
        if sha256(DATASET / name) != summary["input_sha256"][name]:
            raise ValueError(f"Fonte alterada: {name}")
    if sha256(pairs_path) != summary["output_sha256"]["pairs.csv"]:
        raise ValueError("Pares de desenvolvimento alterados")

    items = {
        row["item_id"]: build_item_text(ItemCandidate(
            id=row["item_id"], name=row["name"], description=row["description"],
            location=row["location"], category_name=row["category"],
            found_on=datetime.fromisoformat(row["found_on"]),
        ))
        for row in read_jsonl(DATASET / "items.jsonl")
        if row["split"] == "development" and row["status"] == "ACTIVE"
    }
    queries = {
        row["query_id"]: row for row in read_jsonl(DATASET / "queries.jsonl")
        if row["split"] == "development"
    }
    if len(items) != 700 or len(queries) != 840:
        raise ValueError("Dimensão do desenvolvimento inesperada")

    ranks: dict[str, list[int]] = {variant: [] for variant in VARIANTS}
    seen_queries = set()
    with pairs_path.open(encoding="utf-8", newline="") as stream:
        for query_id, block in groupby(csv.DictReader(stream), key=lambda row: row["query_id"]):
            rows = list(block)
            query = queries.get(query_id)
            if query is None or query_id in seen_queries or len(rows) != 700:
                raise ValueError(f"Bloco de consulta inesperado: {query_id}")
            seen_queries.add(query_id)
            if {int(row["item_id"]) for row in rows} != set(items):
                raise ValueError(f"Candidatos inesperados: {query_id}")
            expected = query["expected_item_id"]
            if expected is None:
                continue
            normalized_query = normalize_for_matching(query["description"])
            scored: dict[str, list[tuple[float, int]]] = {variant: [] for variant in VARIANTS}
            for row in rows:
                item_id = int(row["item_id"])
                cosine = float(row["cosine_score"])
                levenshtein = float(row["levenshtein_score"])
                token_set = fuzz.token_set_ratio(normalized_query, items[item_id]) / 100
                partial = fuzz.partial_ratio(normalized_query, items[item_id]) / 100
                scores = (cosine, levenshtein, token_set, partial,
                          (cosine + levenshtein) / 2,
                          (cosine + token_set) / 2,
                          (cosine + partial) / 2)
                for variant, value in zip(VARIANTS, scores, strict=True):
                    scored[variant].append((value, item_id))
            for variant in VARIANTS:
                ordered = sorted(scored[variant], key=lambda entry: (-entry[0], entry[1]))
                ranks[variant].append(next(position for position, (_, item_id) in enumerate(ordered, 1)
                                           if item_id == expected))
    if seen_queries != set(queries):
        raise ValueError("Consultas incompletas")
    if any(len(values) != 630 for values in ranks.values()):
        raise ValueError("Consultas positivas incompletas")

    result = {
        "scope": "post-test exploratory analysis on development only; original test unchanged",
        "data_sha256": {"items.jsonl": sha256(DATASET / "items.jsonl"),
                        "queries.jsonl": sha256(DATASET / "queries.jsonl"),
                        "results/pairs.csv": sha256(pairs_path)},
        "method": "Normalized query and name+description+location candidate; RapidFuzz fuzz scores divided by 100; original cosine score; fixed 0.5/0.5 hybrids; descending score and ascending item ID ties",
        "metrics": {variant: summarize(values) for variant, values in ranks.items()},
        "rank_changes_vs_original": {
            variant: {
                "better": sum(a < b for a, b in zip(ranks[variant], ranks[original], strict=True)),
                "worse": sum(a > b for a, b in zip(ranks[variant], ranks[original], strict=True)),
                "same": sum(a == b for a, b in zip(ranks[variant], ranks[original], strict=True)),
            }
            for variant, original in (("token_set_ratio", "levenshtein"),
                                      ("partial_ratio", "levenshtein"),
                                      ("hybrid_token_set", "hybrid_original"),
                                      ("hybrid_partial", "hybrid_original"))
        },
    }
    original_results = {
        "cosine": next(entry["metrics"] for entry in summary["grid"]["results"]
                       if entry["method"] == "cosine" and entry["threshold"] == 0.4),
        "levenshtein": next(entry["metrics"] for entry in summary["grid"]["results"]
                            if entry["method"] == "levenshtein" and entry["threshold"] == 0.4),
        "hybrid_original": summary["field_ablation"]["metrics"]["without_category"],
    }
    for variant, expected in original_results.items():
        for metric in ("hit_at_1", "hit_at_5", "mrr"):
            if abs(result["metrics"][variant][metric] - expected[metric]) > 1e-12:
                raise ValueError(f"Linha de base não reproduzida: {variant}/{metric}")
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "metrics": result["metrics"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
