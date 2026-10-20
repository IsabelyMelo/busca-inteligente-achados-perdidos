"""Confere pares, IDs e métricas finais diretamente do CSV bruto."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict

import numpy as np

from evaluation.finalize import FINAL


def main() -> None:
    output = FINAL / "test_results_retry_2"
    lock = json.loads((FINAL / "pretest_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((FINAL / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    item_ids = set(manifest["groups"]["test"]["item_ids"])
    query_ids = set(manifest["groups"]["test"]["query_ids"])
    per_query: dict[str, set[int]] = defaultdict(set)
    matrix = {method: Counter() for method in lock["per_method"]}
    ranks = {method: defaultdict(list) for method in lock["per_method"]}
    with (output / "pairs.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            query_id, item_id = row["query_id"], int(row["item_id"])
            if query_id not in query_ids or item_id not in item_ids or item_id in per_query[query_id]:
                raise ValueError("Par ausente, repetido ou fora do teste")
            per_query[query_id].add(item_id)
            relevant = int(row["is_relevant"])
            cosine, edit = float(row["cosine_score"]), float(row["levenshtein_score"])
            for method, setting in lock["per_method"].items():
                value = cosine if method == "cosine" else edit if method == "levenshtein" else setting["alpha"] * cosine + setting["beta"] * edit
                predicted = value >= setting["threshold"]
                matrix[method]["tp" if relevant and predicted else "fn" if relevant else "fp" if predicted else "tn"] += 1
                ranks[method][query_id].append((value, item_id, relevant))
    if set(per_query) != query_ids or any(items != item_ids for items in per_query.values()):
        raise ValueError("CSV não contém o produto cartesiano completo de 360 x 300")
    for method in lock["per_method"]:
        counts = matrix[method]
        reference = summary["metrics"][method]
        if dict(counts) != reference["confusion_matrix"]:
            raise ValueError(f"Matriz de confusão diverge para {method}")
        precision = counts["tp"] / (counts["tp"] + counts["fp"])
        recall = counts["tp"] / (counts["tp"] + counts["fn"])
        f1 = 2 * precision * recall / (precision + recall)
        if any(abs(value - reference[key]) > 1e-12 for key, value in
               (("precision", precision), ("recall", recall), ("f1", f1))):
            raise ValueError(f"Classificação diverge para {method}")
        positions = []
        for candidates in ranks[method].values():
            ordered = sorted(candidates, key=lambda pair: (-pair[0], pair[1]))
            positions.extend(index for index, (_, _, relevant) in enumerate(ordered, 1) if relevant)
        if len(positions) != 300:
            raise ValueError(f"Positivos inesperados para {method}")
        observed = {
            "hit_at_1": sum(rank <= 1 for rank in positions) / 300,
            "hit_at_3": sum(rank <= 3 for rank in positions) / 300,
            "hit_at_5": sum(rank <= 5 for rank in positions) / 300,
            "mrr": sum(1 / rank for rank in positions) / 300,
        }
        if any(abs(value - reference[key]) > 1e-12 for key, value in observed.items()):
            raise ValueError(f"Ranking diverge para {method}")
        print(f"{method}: 108000 pares, TP={counts['tp']} FP={counts['fp']} TN={counts['tn']} FN={counts['fn']}; métricas conferidas")
    latency = defaultdict(list)
    with (output / "latency.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["query_id"] not in query_ids or row["method"] not in lock["per_method"]:
                raise ValueError("Latência fora do split ou método desconhecido")
            latency[row["method"]].append(float(row["server_time_ms"]))
    for method, values in latency.items():
        if len(values) != 360:
            raise ValueError(f"Latências incompletas para {method}")
        reference = summary["latency"]["statistics"][method]
        observed = {"mean_ms": statistics.mean(values),
                    "median_ms": statistics.median(values),
                    "stddev_ms": statistics.pstdev(values),
                    "p95_ms": float(np.percentile(values, 95))}
        if any(abs(value - reference[key]) > 1e-9 for key, value in observed.items()):
            raise ValueError(f"Latências divergem para {method}")
    print("Latências: 360 por método, estatísticas conferidas")


if __name__ == "__main__":
    main()
