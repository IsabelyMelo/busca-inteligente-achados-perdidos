"""Confere a reexecução limpa da avaliação v2 sem duplicar os CSVs de pares."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from evaluation.evaluate import file_sha256
from evaluation.experiment import verify


DATASET = Path(__file__).resolve().parent / "v2"
REPRODUCTION = DATASET / "reproduction_20261112"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    historical_development = read_json(DATASET / "results" / "summary.json")
    historical_test = read_json(DATASET / "test_results" / "summary.json")
    development = read_json(REPRODUCTION / "development" / "summary.json")
    test = read_json(REPRODUCTION / "test" / "summary.json")
    execution = read_json(REPRODUCTION / "test" / "execution.json")

    if development["code"]["working_tree_dirty"] or execution["code"]["working_tree_dirty"]:
        raise ValueError("A reexecução não foi feita a partir de um commit limpo")
    if development["code"]["head"] != execution["code"]["head"]:
        raise ValueError("Desenvolvimento e teste usaram revisões diferentes")
    if development["input_sha256"] != historical_development["input_sha256"]:
        raise ValueError("Dados de desenvolvimento diferentes dos históricos")
    if development["grid"]["results"] != historical_development["grid"]["results"]:
        raise ValueError("Grade de desenvolvimento diferente da histórica")
    if development["field_ablation"] != historical_development["field_ablation"]:
        raise ValueError("Ablação de campos diferente da histórica")
    if test["metrics"] != historical_test["metrics"]:
        raise ValueError("Métricas de teste diferentes das históricas")
    if test["per_method"] != historical_test["per_method"]:
        raise ValueError("Configuração de teste diferente da histórica")

    for split, historical, repeated in (
        ("development", historical_development, development),
        ("test", historical_test, test),
    ):
        pairs = DATASET / ("results" if split == "development" else "test_results") / "pairs.csv"
        if repeated["output_sha256"]["pairs.csv"] != historical["output_sha256"]["pairs.csv"]:
            raise ValueError(f"Hash dos pares de {split} diferente do histórico")
        if file_sha256(pairs) != repeated["output_sha256"]["pairs.csv"]:
            raise ValueError(f"CSV de pares de {split} diferente da reexecução")
        latency = REPRODUCTION / split / "latency.csv"
        if file_sha256(latency) != repeated["output_sha256"]["latency.csv"]:
            raise ValueError(f"CSV de latência de {split} diferente do resumo")

    with tempfile.TemporaryDirectory(prefix="tcc-v2-verify-") as directory:
        output = Path(directory)
        for name in ("selection.json", "execution.json", "summary.json", "latency.csv"):
            shutil.copyfile(REPRODUCTION / "test" / name, output / name)
        shutil.copyfile(DATASET / "test_results" / "pairs.csv", output / "pairs.csv")
        verify(DATASET, output, "ranking")

    print(f"Reexecução conferida: {development['code']['head']}")
    print("Dados, pares e métricas iguais aos históricos. Latências conferidas separadamente.")


if __name__ == "__main__":
    main()
