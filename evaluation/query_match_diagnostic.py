"""Diagnostica presença de correspondência pelo escore do primeiro candidato."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from evaluation.evaluate import file_sha256, load_jsonl, score


DATASET = Path(__file__).resolve().parent / "v2"
METHOD = "hybrid"
PAIR_THRESHOLD = 0.4


def top_scores(split: str, labels: dict[str, bool]) -> tuple[list[dict], dict]:
    folder = "results" if split == "development" else "test_results"
    summary_path = DATASET / folder / "summary.json"
    pairs_path = DATASET / folder / "pairs.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if file_sha256(pairs_path) != summary["output_sha256"]["pairs.csv"]:
        raise ValueError(f"Pares alterados no conjunto {split}")
    if summary["input_sha256"] != {
        name: file_sha256(DATASET / name) for name in ("items.jsonl", "queries.jsonl")
    }:
        raise ValueError(f"Dados alterados após a avaliação de {split}")
    candidate_count = 700 if split == "development" else 300
    if split == "test" and summary["candidate_count"] != candidate_count:
        raise ValueError("Número inesperado de candidatos")
    if split == "test" and (
        summary["winner"]["method"] != METHOD
        or summary["winner"]["alpha"] != 0.5
        or summary["selection"]["field_selection"] != "without_category"
    ):
        raise ValueError("Configuração do teste diferente da configuração analisada")

    best: dict[str, tuple[float, int]] = {}
    counts: Counter[str] = Counter()
    with pairs_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            query_id = row["query_id"]
            value = score(row, METHOD, 0.5)
            item_id = int(row["item_id"])
            previous = best.get(query_id)
            if previous is None or (-value, item_id) < (-previous[0], previous[1]):
                best[query_id] = (value, item_id)
            counts[query_id] += 1
    if set(best) != set(labels) or any(value != candidate_count for value in counts.values()):
        raise ValueError(f"Pares incompletos no conjunto {split}")
    rows = [
        {
            "query_id": query_id,
            "has_match": labels[query_id],
            "top_item_id": best[query_id][1],
            "top_score": best[query_id][0],
        }
        for query_id in sorted(labels)
    ]
    return rows, {
        "summary.json": file_sha256(summary_path),
        "pairs.csv": file_sha256(pairs_path),
    }


def matrix(rows: list[dict], threshold: float) -> dict:
    tp = sum(row["has_match"] and row["top_score"] >= threshold for row in rows)
    fn = sum(row["has_match"] and row["top_score"] < threshold for row in rows)
    tn = sum(not row["has_match"] and row["top_score"] < threshold for row in rows)
    fp = sum(not row["has_match"] and row["top_score"] >= threshold for row in rows)
    return {
        "threshold": threshold,
        "positive_above": tp,
        "positive_below": fn,
        "no_match_below": tn,
        "no_match_above": fp,
        "positive_detection_rate": tp / (tp + fn),
        "no_match_detection_rate": tn / (tn + fp),
        "balanced_accuracy": ((tp / (tp + fn)) + (tn / (tn + fp))) / 2,
    }


def run() -> dict:
    queries = load_jsonl(DATASET / "queries.jsonl")
    labels = {
        split: {row["query_id"]: row["has_match"] for row in queries if row["split"] == split}
        for split in ("development", "test")
    }
    if [(len(labels[split]), sum(labels[split].values())) for split in labels] != [(840, 630), (360, 270)]:
        raise ValueError("Divisão das consultas diferente da avaliação congelada")
    development, development_hashes = top_scores("development", labels["development"])
    test, test_hashes = top_scores("test", labels["test"])

    grid = [matrix(development, step / 100) for step in range(101)]
    selected = max(
        grid,
        key=lambda entry: (
            entry["balanced_accuracy"], entry["positive_detection_rate"], -entry["threshold"]
        ),
    )
    test_rows_path = DATASET / "query_match_scores_test.csv"
    with test_rows_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(test[0]))
        writer.writeheader()
        writer.writerows(test)
    result = {
        "kind": "post_test_query_match_diagnostic",
        "method": METHOD,
        "score": "highest-ranked candidate hybrid score; ties by item ID",
        "decision": "top score >= threshold indicates possible match",
        "threshold_selection": "grid 0.00..1.00 step 0.01; maximum development balanced accuracy; tie: higher positive detection, then lower threshold",
        "source_sha256": {
            "items.jsonl": file_sha256(DATASET / "items.jsonl"),
            "queries.jsonl": file_sha256(DATASET / "queries.jsonl"),
            "results/summary.json": development_hashes["summary.json"],
            "results/pairs.csv": development_hashes["pairs.csv"],
            "test_results/summary.json": test_hashes["summary.json"],
            "test_results/pairs.csv": test_hashes["pairs.csv"],
        },
        "test_scores_sha256": file_sha256(test_rows_path),
        "development": {
            "queries": len(development),
            "positive_queries": 630,
            "no_match_queries": 210,
            "at_pair_threshold": matrix(development, PAIR_THRESHOLD),
            "selected_threshold": selected,
        },
        "test": {
            "queries": len(test),
            "positive_queries": 270,
            "no_match_queries": 90,
            "at_pair_threshold": matrix(test, PAIR_THRESHOLD),
            "at_development_selected_threshold": matrix(test, selected["threshold"]),
        },
    }
    (DATASET / "query_match_diagnostic.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run()
    print("development", result["development"])
    print("test", result["test"])
