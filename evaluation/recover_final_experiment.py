"""Repetição técnica autorizada após falha de socket do primeiro teste."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from evaluation import final_experiment as experiment
from evaluation.evaluate import file_sha256


FIRST = experiment.TEST_OUTPUT
RETRY = experiment.FINAL / "test_results_retry_2"


def audit() -> dict:
    lock = experiment.verify_lock()
    files = {path.name for path in FIRST.iterdir()}
    if files != {"execution.json"}:
        raise ValueError(f"Primeira tentativa possui arquivos inesperados: {sorted(files)}")
    first = experiment.read_json(FIRST / "execution.json")
    lock_sha = file_sha256(experiment.LOCK)
    if first != {
        "started_at_utc": first["started_at_utc"],
        "pretest_config_sha256": lock_sha,
        "attempt": 1,
    }:
        raise ValueError("Marcador da primeira tentativa diverge da configuração congelada")
    if RETRY.exists():
        raise FileExistsError("Diretório da segunda tentativa já existe")
    return {"first_execution_sha256": file_sha256(FIRST / "execution.json"),
            "pretest_config_sha256": lock_sha,
            "original_runner_sha256": file_sha256(experiment.ROOT / "evaluation/final_experiment.py"),
            "recovery_runner_sha256": file_sha256(__file__),
            "winner": lock["winner"]}


def run() -> dict:
    context = audit()
    experiment.TEST_OUTPUT = RETRY
    try:
        result = experiment.run_test()
    finally:
        if RETRY.exists():
            (RETRY / "retry_context.json").write_text(json.dumps({
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "global_attempt": 2,
                "reason": "Primeira tentativa interrompida antes da primeira medição HTTP: "
                          "TestClient bloqueado por restrição de sockets locais do sandbox Windows",
                "method_changes": False,
                "dataset_changes": False,
                "configuration_changes": False,
                "user_authorized_controlled_retry": True,
                **context,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "run"))
    command = parser.parse_args().command
    result = audit() if command == "audit" else run()
    print(json.dumps({"command": command, "result": result if command == "audit" else {
        "candidate_count": result["candidate_count"],
        "query_count": result["query_count"],
        "output": str(RETRY),
    }}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
