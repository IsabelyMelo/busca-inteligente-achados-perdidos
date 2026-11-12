"""Compara Hit@1 das duas composições da ablação de campos na v2."""

from __future__ import annotations

import csv
import hashlib
import json
from itertools import groupby
from pathlib import Path

import numpy as np


DATASET = Path(__file__).resolve().parent / "v2"
PAIRS = DATASET / "results" / "pairs.csv"
SUMMARY = DATASET / "results" / "summary.json"
OUTPUT = DATASET / "field_ablation_uncertainty.json"
BOOTSTRAP_SAMPLES = 20_000
SEED = 20261109


def hit_at_one(rows: list[dict[str, str]], prefix: str, expected: int) -> int:
    winner = max(
        rows,
        key=lambda row: (
            (float(row[f"{prefix}cosine_score"]) + float(row[f"{prefix}levenshtein_score"])) / 2,
            -int(row["item_id"]),
        ),
    )
    return int(int(winner["item_id"]) == expected)


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    pairs_hash = hashlib.sha256(PAIRS.read_bytes()).hexdigest()
    if pairs_hash != summary["output_sha256"]["pairs.csv"]:
        raise ValueError("pairs.csv não corresponde ao arquivo da avaliação congelada")
    if summary["field_ablation"]["fixed_alpha"] != 0.5:
        raise ValueError("A análise pressupõe pesos iguais no híbrido")

    without_hits = []
    with_hits = []
    expected_items = []
    with PAIRS.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for _query_id, group in groupby(reader, key=lambda row: row["query_id"]):
            rows = list(group)
            if not rows[0]["expected_item_id"]:
                continue
            expected = int(rows[0]["expected_item_id"])
            expected_items.append(expected)
            without_hits.append(hit_at_one(rows, "", expected))
            with_hits.append(hit_at_one(rows, "alternative_", expected))

    without = np.asarray(without_hits, dtype=np.int8)
    with_category = np.asarray(with_hits, dtype=np.int8)
    n = len(without)
    recorded = summary["field_ablation"]["metrics"]
    if n != 630 or not np.isclose(without.mean(), recorded["without_category"]["hit_at_1"]):
        raise ValueError("Hit@1 sem categoria não reproduz o resumo da avaliação")
    if not np.isclose(with_category.mean(), recorded["with_category"]["hit_at_1"]):
        raise ValueError("Hit@1 com categoria não reproduz o resumo da avaliação")

    difference = without.astype(np.int8) - with_category.astype(np.int8)
    clusters: dict[int, list[int]] = {}
    for expected, value in zip(expected_items, difference, strict=True):
        clusters.setdefault(expected, []).append(int(value))
    cluster_sums = np.asarray([sum(values) for values in clusters.values()], dtype=np.int16)
    cluster_sizes = np.asarray([len(values) for values in clusters.values()], dtype=np.int8)
    cluster_count = len(clusters)
    rng = np.random.default_rng(SEED)
    bootstrap = np.empty(BOOTSTRAP_SAMPLES)
    for start in range(0, BOOTSTRAP_SAMPLES, 1000):
        end = min(start + 1000, BOOTSTRAP_SAMPLES)
        indices = rng.integers(0, cluster_count, size=(end - start, cluster_count))
        bootstrap[start:end] = cluster_sums[indices].sum(axis=1) / cluster_sizes[indices].sum(axis=1)
    lower, upper = np.quantile(bootstrap, [0.025, 0.975])

    favors_without = int(np.count_nonzero(difference == 1))
    favors_with = int(np.count_nonzero(difference == -1))
    result = {
        "source_sha256": {"pairs.csv": pairs_hash},
        "positive_queries": n,
        "hybrid_alpha": 0.5,
        "without_category": {"hit_at_1_count": int(without.sum()), "hit_at_1": float(without.mean())},
        "with_category": {"hit_at_1_count": int(with_category.sum()), "hit_at_1": float(with_category.mean())},
        "paired_difference_without_minus_with": float(difference.mean()),
        "discordant_queries": {
            "favors_without_category": favors_without,
            "favors_with_category": favors_with,
        },
        "paired_bootstrap": {
            "confidence_level": 0.95,
            "method": "percentile, resampling expected-item clusters with replacement",
            "clusters": cluster_count,
            "samples": BOOTSTRAP_SAMPLES,
            "seed": SEED,
            "difference_interval": [float(lower), float(upper)],
        },
        "interpretation_scope": "exploratory development-set field selection, not an independent test",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
