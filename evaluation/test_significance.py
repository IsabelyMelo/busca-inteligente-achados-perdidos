"""Incerteza das métricas e comparação pareada no teste congelado da v2."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from itertools import groupby
from math import comb
from pathlib import Path

import numpy as np

from evaluation.evaluate import score


DATASET = Path(__file__).resolve().parent / "v2"
PAIRS = DATASET / "test_results" / "pairs.csv"
SUMMARY = DATASET / "test_results" / "summary.json"
OUTPUT = DATASET / "test_significance.json"
METHODS = ("cosine", "levenshtein", "hybrid")
METRICS = ("precision", "recall", "f1", "hit_at_1", "hit_at_3", "hit_at_5", "mrr")
SAMPLES = 20_000
SEED = 20261109


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def metric_arrays(totals: np.ndarray) -> dict[str, np.ndarray]:
    tp, fp, fn, h1, h3, h5, rr, positives = totals.T
    precision = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) != 0)
    recall = np.divide(tp, tp + fn, out=np.zeros_like(tp), where=(tp + fn) != 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros_like(tp), where=(precision + recall) != 0)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hit_at_1": h1 / positives,
        "hit_at_3": h3 / positives,
        "hit_at_5": h5 / positives,
        "mrr": rr / positives,
    }


def mcnemar(left: list[bool], right: list[bool]) -> dict:
    left_only = sum(a and not b for a, b in zip(left, right, strict=True))
    right_only = sum(b and not a for a, b in zip(left, right, strict=True))
    discordant = left_only + right_only
    p = min(1.0, 2 * sum(comb(discordant, k) for k in range(min(left_only, right_only) + 1))
            / (2 ** discordant)) if discordant else 1.0
    return {
        "hybrid_only_correct": left_only,
        "cosine_only_correct": right_only,
        "discordant": discordant,
        "exact_two_sided_p": p,
    }


def main() -> None:
    frozen = json.loads(SUMMARY.read_text(encoding="utf-8"))
    paths = {name: DATASET / name for name in ("items.jsonl", "queries.jsonl")}
    for name, path in paths.items():
        if sha256(path) != frozen["input_sha256"][name]:
            raise ValueError(f"Fonte do teste alterada: {name}")
    if sha256(PAIRS) != frozen["output_sha256"]["pairs.csv"]:
        raise ValueError("Pares do teste alterados")
    if frozen["winner"] != {"method": "hybrid", "alpha": 0.5, "beta": 0.5}:
        raise ValueError("Configuração final inesperada")

    queries = {row["query_id"]: row for row in read_jsonl(paths["queries.jsonl"])
               if row["split"] == "test"}
    groups: dict[str, dict[str, np.ndarray]] = {method: defaultdict(lambda: np.zeros(8))
                                               for method in METHODS}
    ranks: dict[str, dict[str, int]] = {method: {} for method in METHODS}
    seen_queries = set()
    with PAIRS.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for query_id, block in groupby(reader, key=lambda row: row["query_id"]):
            rows = list(block)
            query = queries.get(query_id)
            if query is None or query_id in seen_queries or len(rows) != 300:
                raise ValueError(f"Bloco de consulta inesperado: {query_id}")
            seen_queries.add(query_id)
            expected = query["expected_item_id"]
            relevant = [row for row in rows if int(row["is_relevant"])]
            if len(relevant) != int(expected is not None):
                raise ValueError(f"Rótulo inconsistente: {query_id}")
            for method in METHODS:
                values = [(score(row, method, 0.5), int(row["item_id"]), int(row["is_relevant"]))
                          for row in rows]
                tp = sum(value >= 0.4 and is_relevant for value, _, is_relevant in values)
                fp = sum(value >= 0.4 and not is_relevant for value, _, is_relevant in values)
                fn = int(expected is not None) - tp
                rank = 0
                if expected is not None:
                    ordered = sorted(values, key=lambda entry: (-entry[0], entry[1]))
                    rank = next(index for index, (_, _, is_relevant) in enumerate(ordered, 1)
                                if is_relevant)
                    ranks[method][query_id] = rank
                groups[method][query["reference_id"]] += np.array([
                    tp, fp, fn, int(0 < rank <= 1), int(0 < rank <= 3),
                    int(0 < rank <= 5), 1 / rank if rank else 0, int(rank > 0)
                ], dtype=float)

    if seen_queries != set(queries) or len(seen_queries) != 360:
        raise ValueError("Consultas do teste incompletas")
    positive_ids = sorted(query_id for query_id, query in queries.items() if query["has_match"])
    if len(positive_ids) != 270:
        raise ValueError("Número de consultas positivas inesperado")
    positive_refs = sorted({queries[q]["reference_id"] for q in positive_ids})
    negative_refs = sorted({q["reference_id"] for q in queries.values() if not q["has_match"]})

    points = {}
    matrices = {}
    for method in METHODS:
        pos = np.stack([groups[method][ref] for ref in positive_refs])
        neg = np.stack([groups[method][ref] for ref in negative_refs])
        matrices[method] = (pos, neg)
        points[method] = {name: float(values[0]) for name, values in
                          metric_arrays((pos.sum(axis=0) + neg.sum(axis=0))[None, :]).items()}
        for name in METRICS:
            if abs(points[method][name] - frozen["metrics"][method][name]) > 1e-12:
                raise ValueError(f"Métrica congelada não reproduzida: {method}/{name}")

    rng = np.random.default_rng(SEED)
    replicates = {method: {name: np.empty(SAMPLES) for name in METRICS} for method in METHODS}
    for start in range(0, SAMPLES, 500):
        end = min(start + 500, SAMPLES)
        positive_indices = rng.integers(0, len(positive_refs), size=(end - start, len(positive_refs)))
        negative_indices = rng.integers(0, len(negative_refs), size=(end - start, len(negative_refs)))
        # Reutiliza os mesmos grupos sorteados nos três métodos para preservar o pareamento.
        for method in METHODS:
            pos, neg = matrices[method]
            totals = pos[positive_indices].sum(axis=1) + neg[negative_indices].sum(axis=1)
            for name, values in metric_arrays(totals).items():
                replicates[method][name][start:end] = values

    intervals = {
        method: {name: [float(value) for value in np.quantile(replicates[method][name], [0.025, 0.975])]
                 for name in METRICS}
        for method in METHODS
    }
    comparison = {}
    for k in (1, 5):
        comparison[f"hit_at_{k}"] = mcnemar(
            [ranks["hybrid"][q] <= k for q in positive_ids],
            [ranks["cosine"][q] <= k for q in positive_ids],
        )
    for name in ("hit_at_1", "hit_at_5"):
        diff = replicates["hybrid"][name] - replicates["cosine"][name]
        comparison[name]["difference"] = points["hybrid"][name] - points["cosine"][name]
        comparison[name]["paired_cluster_bootstrap_95_interval"] = [
            float(value) for value in np.quantile(diff, [0.025, 0.975])]
    comparison["mrr"] = {
        "difference": points["hybrid"]["mrr"] - points["cosine"]["mrr"],
        "paired_cluster_bootstrap_95_interval": [
            float(value) for value in np.quantile(
                replicates["hybrid"]["mrr"] - replicates["cosine"]["mrr"], [0.025, 0.975])]
    }
    comparison["mrr"]["rank_changes"] = {
        "hybrid_better": sum(ranks["hybrid"][q] < ranks["cosine"][q] for q in positive_ids),
        "cosine_better": sum(ranks["cosine"][q] < ranks["hybrid"][q] for q in positive_ids),
        "same_rank": sum(ranks["cosine"][q] == ranks["hybrid"][q] for q in positive_ids),
    }

    result = {
        "source_sha256": {"pairs.csv": sha256(PAIRS), **{name: sha256(path) for name, path in paths.items()}},
        "positive_queries": len(positive_ids),
        "all_queries": len(queries),
        "positive_reference_groups": len(positive_refs),
        "negative_reference_groups": len(negative_refs),
        "bootstrap": {"samples": SAMPLES, "seed": SEED, "confidence_level": 0.95,
                      "method": "stratified cluster percentile; resample positive and negative reference groups separately"},
        "metrics": points,
        "metric_95_intervals": intervals,
        "hybrid_minus_cosine": comparison,
        "mcnemar_note": "Exact query-level McNemar treats repeated formulations of one item as independent; cluster intervals address this dependence.",
        "interpretation_scope": "frozen synthetic test, no parameter selection from this analysis",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "groups": [len(positive_refs), len(negative_refs)],
                      "comparison": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
