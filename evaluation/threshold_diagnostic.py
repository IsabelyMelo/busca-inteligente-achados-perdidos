"""Curva precisão–revocação no desenvolvimento v2, sem usar o teste final."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent / "v2"
PAIRS = ROOT / "results" / "pairs.csv"
SUMMARY = ROOT / "results" / "summary.json"
OUTPUT = ROOT / "threshold_curve.csv"


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    digest = hashlib.sha256(PAIRS.read_bytes()).hexdigest()
    if summary["split"] != "development" or digest != summary["output_sha256"]["pairs.csv"]:
        raise ValueError("O arquivo de pares não corresponde ao desenvolvimento v2 congelado")

    cosine = []
    levenshtein = []
    relevant = []
    with PAIRS.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            cosine.append(float(row["cosine_score"]))
            levenshtein.append(float(row["levenshtein_score"]))
            relevant.append(int(row["is_relevant"]))
    scores = 0.5 * np.asarray(cosine) + 0.5 * np.asarray(levenshtein)
    labels = np.asarray(relevant)
    order = np.argsort(-scores, kind="stable")
    descending_scores = scores[order]
    cumulative_positives = np.cumsum(labels[order])
    total_positives = int(labels.sum())

    rows = []
    for step in range(101):
        threshold = step / 100
        selected_count = int(np.searchsorted(-descending_scores, -threshold, side="right"))
        tp = int(cumulative_positives[selected_count - 1]) if selected_count else 0
        fp = selected_count - tp
        rows.append({
            "threshold": threshold,
            "precision": tp / selected_count if selected_count else 1.0,
            "recall": tp / total_positives,
            "tp": tp,
            "fp": fp,
        })

    archived = next(
        entry["metrics"] for entry in summary["grid"]["results"]
        if entry["method"] == "hybrid" and entry["alpha"] == 0.5 and entry["threshold"] == 0.4
    )
    for key in ("precision", "recall"):
        if abs(rows[40][key] - archived[key]) > 1e-12:
            raise ValueError(f"Valor de {key} no limiar 0,4 difere do resultado congelado")

    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"pares={len(scores)} positivos={total_positives} sha256={digest}")
    for index in (20, 40, 60):
        row = rows[index]
        print(
            f"limiar={row['threshold']:.1f} precisão={row['precision']:.4f} "
            f"revocação={row['recall']:.4f} VP={row['tp']} FP={row['fp']}"
        )


if __name__ == "__main__":
    main()
