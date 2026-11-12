"""Recalcula a sensibilidade dos pesos com os pares congelados do desenvolvimento v2."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from evaluation.evaluate import metrics


ROOT = Path(__file__).resolve().parent / "v2"
PAIRS = ROOT / "results" / "pairs.csv"
SUMMARY = ROOT / "results" / "summary.json"
OUTPUT = ROOT / "weight_sensitivity.json"
ORIGINAL_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
TENTHS = tuple(step / 10 for step in range(11))
WEIGHTS = tuple(sorted(set(ORIGINAL_WEIGHTS + TENTHS)))
RANKING_KEYS = ("hit_at_1", "hit_at_5", "mrr")


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    digest = hashlib.sha256(PAIRS.read_bytes()).hexdigest()
    if digest != summary["output_sha256"]["pairs.csv"]:
        raise ValueError("O arquivo de pares difere do desenvolvimento congelado")
    if summary["split"] != "development" or summary["field_ablation"]["selected"] != "without_category":
        raise ValueError("O resumo não corresponde à configuração de desenvolvimento usada no TCC")

    with PAIRS.open(encoding="utf-8", newline="") as stream:
        pairs = list(csv.DictReader(stream))

    archived = {
        entry["alpha"]: entry["metrics"]
        for entry in summary["grid"]["results"]
        if entry["threshold"] == 0.4
    }
    results = []
    for alpha in WEIGHTS:
        observed = metrics(pairs, "hybrid", alpha, 0.4)
        if alpha in archived:
            for key in RANKING_KEYS:
                if abs(observed[key] - archived[alpha][key]) > 1e-12:
                    raise ValueError(f"Resultado divergente para alpha={alpha}, métrica={key}")
        results.append({
            "alpha": alpha,
            "beta": 1 - alpha,
            **{key: observed[key] for key in RANKING_KEYS},
        })

    payload = {
        "source": "evaluation/v2/results/pairs.csv",
        "source_sha256": digest,
        "split": "development",
        "pairs": len(pairs),
        "positive_queries": observed["positive_queries"],
        "original_weights": ORIGINAL_WEIGHTS,
        "supplemental_tenths": TENTHS,
        "results": results,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(
            f"{row['alpha']:.2f}  {row['hit_at_1']:.4f}  "
            f"{row['hit_at_5']:.4f}  {row['mrr']:.4f}"
        )
    print(f"Fonte: {OUTPUT}")


if __name__ == "__main__":
    main()
