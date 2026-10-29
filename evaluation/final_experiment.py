"""Congela a calibração e executa o teste final uma única vez."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.preprocessing import DOMAIN_STOPWORDS
from evaluation.evaluate import (
    FixedRepository, file_sha256, git_revision, latency_stats, memory_bytes,
    metrics, score_pairs, select_records,
)
from evaluation.finalize import FINAL, VERSION


ROOT = Path(__file__).resolve().parent.parent
DEVELOPMENT = FINAL / "results"
LOCK = FINAL / "pretest_config.json"
TEST_OUTPUT = FINAL / "test_results"
CODE_FILES = (
    "evaluation/evaluate.py", "evaluation/final_experiment.py",
    "evaluation/finalize.py", "evaluation/validate.py", "app/matching.py",
    "app/preprocessing.py", "app/main.py", "app/config.py",
)
PACKAGES = ("fastapi", "httpx", "numpy", "rapidfuzz", "scikit-learn", "pydantic", "pydantic-settings")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def method_key(entry: dict) -> tuple:
    result = entry["metrics"]
    order = {"cosine": 2, "levenshtein": 1, "hybrid": 0}
    return (result["f1"], result["precision"], entry["threshold"],
            order[entry["method"]], entry["alpha"])


def freeze() -> dict:
    """Usa apenas resultados de desenvolvimento e cria o registro pré-teste."""
    if LOCK.exists() or TEST_OUTPUT.exists():
        raise FileExistsError("Configuração ou saída de teste já existe; audite antes de repetir")
    manifest = read_json(FINAL / "manifest.json")
    summary = read_json(DEVELOPMENT / "summary.json")
    if manifest["dataset_version"] != VERSION or summary["split"] != "development":
        raise ValueError("Versão ou split de desenvolvimento inesperado")
    if summary["input_sha256"] != manifest["sha256"]:
        raise ValueError("Checksums de desenvolvimento divergem do dataset E06")
    for name in ("items.jsonl", "queries.jsonl"):
        if file_sha256(FINAL / name) != manifest["sha256"][name]:
            raise ValueError(f"Checksum E06 divergente: {name}")
    for name, digest in manifest["sql"]["sha256"].items():
        if file_sha256(FINAL / name) != digest:
            raise ValueError(f"Checksum E06 divergente: {name}")
    for name, digest in summary["output_sha256"].items():
        if file_sha256(DEVELOPMENT / name) != digest:
            raise ValueError(f"Saída de desenvolvimento divergente: {name}")
    if summary["grid"]["selected"] != max(summary["grid"]["results"], key=method_key):
        raise ValueError("A escolha não segue a regra predefinida")
    if summary["field_ablation"]["selected"] not in ("with_category", "without_category"):
        raise ValueError("Composição de campos desconhecida")
    with (DEVELOPMENT / "pairs.csv").open(encoding="utf-8", newline="") as stream:
        rows = csv.DictReader(stream)
        pair_count = 0
        item_ids, query_ids = set(), set()
        for row in rows:
            pair_count += 1
            item_ids.add(int(row["item_id"]))
            query_ids.add(row["query_id"])
    if pair_count != 700 * 840 or summary["grid"]["selected"]["metrics"]["pairs"] != pair_count:
        raise ValueError("Desenvolvimento não pontuou exatamente 700 x 840 pares")
    if item_ids != set(manifest["groups"]["development"]["item_ids"]) or query_ids != set(manifest["groups"]["development"]["query_ids"]):
        raise ValueError("Pares de desenvolvimento contêm IDs fora do manifesto")
    with (DEVELOPMENT / "latency.csv").open(encoding="utf-8", newline="") as stream:
        if sum(1 for _ in csv.DictReader(stream)) != 840 * 3:
            raise ValueError("Latências de desenvolvimento incompletas")
    per_method = {
        method: {key: entry[key] for key in ("method", "alpha", "beta", "threshold")}
        for method in ("cosine", "levenshtein", "hybrid")
        for entry in [max((row for row in summary["grid"]["results"] if row["method"] == method), key=method_key)]
    }
    lock = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_version": VERSION,
        "dataset_sha256": manifest["sha256"],
        "dataset_manifest_sha256": file_sha256(FINAL / "manifest.json"),
        "sql_sha256": manifest["sql"]["sha256"],
        "development_sha256": {name: file_sha256(DEVELOPMENT / name)
                               for name in ("summary.json", "pairs.csv", "latency.csv")},
        "git": git_revision(),
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
        "environment": {
            "python": sys.version, "platform": platform.platform(),
            "processor": platform.processor(), "memory_bytes": memory_bytes(),
            "packages": {name: version(name) for name in PACKAGES},
        },
        "fields": ["name", "description", "location"] +
                  (["category"] if summary["field_ablation"]["selected"] == "with_category" else []),
        "stopwords": sorted(DOMAIN_STOPWORDS),
        "field_selection": summary["field_ablation"]["selected"],
        "field_rule": "Hit@1, MRR, F1; empate sem categoria; híbrido 0,5 e limiar 0,4",
        "grid": {"weights": summary["grid"]["weights"],
                 "thresholds": summary["grid"]["thresholds"],
                 "selection_rule": summary["grid"]["selection_rule"]},
        "per_method": per_method,
        "winner": {key: summary["grid"]["selected"][key]
                   for key in ("method", "alpha", "beta", "threshold")},
        "test_execution_count_before_freeze": 0,
    }
    with LOCK.open("x", encoding="utf-8") as stream:
        json.dump(lock, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return lock


def verify_lock() -> dict:
    lock = read_json(LOCK)
    if lock["dataset_version"] != VERSION or lock["dataset_manifest_sha256"] != file_sha256(FINAL / "manifest.json"):
        raise ValueError("Manifesto ou versão mudou após o congelamento")
    for name, digest in lock["dataset_sha256"].items():
        if digest != file_sha256(FINAL / name):
            raise ValueError(f"Dataset mudou após o congelamento: {name}")
    for name, digest in lock["sql_sha256"].items():
        if digest != file_sha256(FINAL / name):
            raise ValueError(f"SQL mudou após o congelamento: {name}")
    for name, digest in lock["development_sha256"].items():
        if digest != file_sha256(DEVELOPMENT / name):
            raise ValueError(f"Calibração mudou após o congelamento: {name}")
    for name, digest in lock["code_sha256"].items():
        if digest != file_sha256(ROOT / name):
            raise ValueError(f"Código mudou após o congelamento: {name}")
    if lock["stopwords"] != sorted(DOMAIN_STOPWORDS):
        raise ValueError("Stopwords mudaram após o congelamento")
    return lock


def run_test() -> dict:
    lock = verify_lock()
    # A criação exclusiva marca a única tentativa antes da leitura de teste
    TEST_OUTPUT.mkdir(exist_ok=False)
    (TEST_OUTPUT / "execution.json").write_text(json.dumps({
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pretest_config_sha256": file_sha256(LOCK), "attempt": 1,
    }, indent=2) + "\n", encoding="utf-8")
    items, queries, validation = select_records(FINAL, "test", allow_test=True)
    if (len(items), len(queries)) != (300, 360):
        raise ValueError("Teste não selecionou 300 candidatos e 360 consultas")
    rows = score_pairs(items, queries, include_category=lock["field_selection"] == "with_category")
    if len(rows) != 300 * 360:
        raise ValueError("Teste não pontuou exatamente 300 x 360 pares")
    latency_rows = []
    results = {}
    for method, setting in lock["per_method"].items():
        results[method] = metrics(rows, method, setting["alpha"], setting["threshold"])
        app = create_app(repository=FixedRepository(items), settings=Settings(
            match_method=method, match_alpha=setting["alpha"], match_beta=setting["beta"]),
            include_category=lock["field_selection"] == "with_category",
        )
        with TestClient(app) as client:
            for query in queries:
                response = client.post("/matches/search", json={
                    "description": query["description"], "top_k": 5,
                })
                response.raise_for_status()
                latency_rows.append({"query_id": query["query_id"], "method": method,
                                     "server_time_ms": float(response.headers["X-Server-Time-Ms"])})
    latency = {method: latency_stats([row["server_time_ms"] for row in latency_rows
                                      if row["method"] == method]) for method in lock["per_method"]}
    for name, data in (("pairs.csv", rows), ("latency.csv", latency_rows)):
        with (TEST_OUTPUT / name).open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    summary = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution": "single final test; no calibration on test",
        "split": "test", "dataset_version": VERSION,
        "candidate_count": len(items), "query_count": len(queries),
        "validation": {"items": validation.item_count, "queries": validation.query_count},
        "pretest_config_sha256": file_sha256(LOCK),
        "dataset_manifest_sha256": lock["dataset_manifest_sha256"],
        "git": git_revision(), "environment": lock["environment"],
        "config": {"fields": lock["fields"], "stopwords": lock["stopwords"],
                   "per_method": lock["per_method"], "winner": lock["winner"]},
        "metrics": results,
        "latency": {"measurement": "server-side HTTP middleware, request to response object; independent TestClient calls",
                    "top_k": 5, "statistics": latency},
        "output_sha256": {name: file_sha256(TEST_OUTPUT / name)
                          for name in ("execution.json", "pairs.csv", "latency.csv")},
    }
    with (TEST_OUTPUT / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "test"))
    command = parser.parse_args().command
    result = freeze() if command == "freeze" else run_test()
    print(json.dumps({"command": command, "winner": result.get("winner", result.get("config", {}).get("winner")),
                      "artifact": str(LOCK if command == "freeze" else TEST_OUTPUT / "summary.json")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
