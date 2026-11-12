"""Seleciona, executa e confere avaliações por conjunto e critério."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from math import isclose
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import audit_logger, create_app
from evaluation.evaluate import (
    EVALUATION_HEADERS,
    EVALUATION_KEY,
    FixedRepository,
    file_sha256,
    git_revision,
    latency_stats,
    metrics,
    score_pairs,
    select_grid_configuration,
    select_records,
)


METHODS = ("cosine", "levenshtein", "hybrid")
INPUTS = ("items.jsonl", "queries.jsonl")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def hashes(directory: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: file_sha256(directory / name) for name in names}


def settings_only(entry: dict) -> dict:
    return {key: entry[key] for key in ("method", "alpha", "beta", "threshold")}


def development_selection(dataset: Path, criterion: str) -> dict:
    development_path = dataset / "results" / "summary.json"
    development = read_json(development_path)
    if development["split"] != "development":
        raise ValueError("O resumo não pertence ao desenvolvimento")
    recorded_dataset = Path(development["dataset"]).resolve()
    legacy_v1_path = (
        dataset.name == "v1"
        and recorded_dataset.name == "final"
        and recorded_dataset.parent == dataset.parent
    )
    if recorded_dataset != dataset.resolve() and not legacy_v1_path:
        raise ValueError("O resumo pertence a outro conjunto de dados")
    input_hashes = hashes(dataset, INPUTS)
    if development["input_sha256"] != input_hashes:
        raise ValueError("Os dados mudaram após a avaliação de desenvolvimento")
    for name, digest in development["output_sha256"].items():
        if file_sha256(dataset / "results" / name) != digest:
            raise ValueError(f"Resultado de desenvolvimento alterado: {name}")
    winner, per_method, rule = select_grid_configuration(
        development["grid"]["results"], criterion
    )
    field_selection = development["field_ablation"]["selected"]
    if field_selection not in ("with_category", "without_category"):
        raise ValueError("Composição de campos desconhecida")
    return {
        "dataset": str(dataset.resolve()),
        "criterion": criterion,
        "rule": rule,
        "field_selection": field_selection,
        "winner": settings_only(winner),
        "per_method": {
            method: settings_only(per_method[method]) for method in METHODS
        },
        "input_sha256": input_hashes,
        "development_sha256": file_sha256(development_path),
    }


def freeze(dataset: Path, output: Path, criterion: str) -> dict:
    if output.exists():
        raise FileExistsError(f"A saída já existe: {output}")
    selection = development_selection(dataset, criterion)
    output.mkdir(parents=True, exist_ok=False)
    lock = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        **selection,
    }
    (output / "selection.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return lock


def selected_for_output(dataset: Path, output: Path, criterion: str) -> dict:
    current = development_selection(dataset, criterion)
    lock_path = output / "selection.json"
    if lock_path.exists():
        saved = read_json(lock_path)
        if any(saved.get(key) != value for key, value in current.items()):
            raise ValueError("A configuração congelada diverge do desenvolvimento")
    return current


def run_test(dataset: Path, output: Path, criterion: str) -> dict:
    if not (output / "selection.json").exists():
        raise FileNotFoundError("Execute freeze antes de abrir o teste")
    if any((output / name).exists() for name in ("execution.json", "pairs.csv", "latency.csv", "summary.json")):
        raise FileExistsError(f"O teste já possui resultados em {output}")
    revision = git_revision()
    if revision["working_tree_dirty"]:
        raise ValueError("A avaliação de teste exige um commit limpo")
    selection = selected_for_output(dataset, output, criterion)
    output.mkdir(parents=True, exist_ok=True)
    items, queries, validation = select_records(dataset, "test", allow_test=True)
    rows = score_pairs(
        items, queries,
        include_category=selection["field_selection"] == "with_category",
    )
    execution = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "code": revision,
        "dataset": str(dataset.resolve()),
        "criterion": criterion,
        "selection_sha256": (
            file_sha256(output / "selection.json")
            if (output / "selection.json").exists() else None
        ),
    }
    with (output / "execution.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(execution, ensure_ascii=False, indent=2) + "\n")
    with (output / "pairs.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset.name,
        "split": "test",
        "criterion": criterion,
        "candidate_count": len(items),
        "query_count": len(queries),
        "validation": {"items": validation.item_count, "queries": validation.query_count},
        "field_selection": selection["field_selection"],
        "winner": selection["winner"],
        "per_method": selection["per_method"],
        "input_sha256": selection["input_sha256"],
        "development_sha256": selection["development_sha256"],
        "metrics": {
            method: metrics(rows, method, setting["alpha"], setting["threshold"])
            for method, setting in selection["per_method"].items()
        },
        "output_sha256": hashes(output, ("execution.json", "pairs.csv")),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def measure_latency(dataset: Path, output: Path, criterion: str) -> dict:
    if not (output / "selection.json").exists():
        raise FileNotFoundError("A medição de uma nova execução exige selection.json")
    summary_path = output / "summary.json"
    summary = read_json(summary_path)
    if "latency" in summary or (output / "latency.csv").exists():
        raise FileExistsError("A latência já foi medida")
    selection = selected_for_output(dataset, output, criterion)
    if summary["per_method"] != selection["per_method"]:
        raise ValueError("Os parâmetros do teste diferem do desenvolvimento")
    items, queries, _ = select_records(dataset, "test", allow_test=True)
    if (len(items), len(queries)) != (summary["candidate_count"], summary["query_count"]):
        raise ValueError("O tamanho do teste mudou")
    latency_rows = []
    previous_level = audit_logger.level
    audit_logger.setLevel(logging.WARNING)
    try:
        for method in METHODS:
            setting = selection["per_method"][method]
            app = create_app(
                repository=FixedRepository(items),
                settings=Settings(
                    _env_file=None,
                    service_api_key=EVALUATION_KEY,
                    rate_limit_per_minute=1000,
                    match_method=method,
                    match_alpha=setting["alpha"],
                    match_beta=setting["beta"],
                ),
                include_category=selection["field_selection"] == "with_category",
            )
            with TestClient(app) as client:
                for query in queries:
                    response = client.post(
                        "/matches/search",
                        json={"description": query["description"], "top_k": 5},
                        headers=EVALUATION_HEADERS,
                    )
                    response.raise_for_status()
                    latency_rows.append({
                        "query_id": query["query_id"],
                        "method": method,
                        "server_time_ms": float(response.headers["X-Server-Time-Ms"]),
                    })
    finally:
        audit_logger.setLevel(previous_level)
    with (output / "latency.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(latency_rows[0]))
        writer.writeheader()
        writer.writerows(latency_rows)
    summary["latency"] = {
        "measurement": "tempo no servidor via TestClient, uma chamada por consulta e método",
        "top_k": 5,
        "statistics": {
            method: latency_stats([
                row["server_time_ms"] for row in latency_rows if row["method"] == method
            ])
            for method in METHODS
        },
    }
    summary["output_sha256"]["latency.csv"] = file_sha256(output / "latency.csv")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def recorded_settings(summary: dict) -> tuple[dict, dict, str | None]:
    config = summary.get("config", summary)
    return (
        config["winner"],
        config["per_method"],
        summary.get("field_selection", "with_category" if "category" in config.get("fields", []) else "without_category"),
    )


def verify(dataset: Path, output: Path, criterion: str) -> dict:
    summary = read_json(output / "summary.json")
    selection = selected_for_output(dataset, output, criterion)
    winner, per_method, field_selection = recorded_settings(summary)
    if any(per_method[method] != selection["per_method"][method] for method in METHODS):
        raise ValueError("Os parâmetros não correspondem ao desenvolvimento")
    if field_selection != selection["field_selection"]:
        raise ValueError("Os campos não correspondem ao desenvolvimento")
    if any(winner[key] != selection["winner"][key] for key in ("method", "alpha", "beta")):
        raise ValueError("O vencedor não corresponde ao desenvolvimento")
    if summary.get("input_sha256", selection["input_sha256"]) != selection["input_sha256"]:
        raise ValueError("Os dados foram alterados")
    if summary.get("development_sha256", selection["development_sha256"]) != selection["development_sha256"]:
        raise ValueError("O desenvolvimento foi alterado")
    for name, digest in summary["output_sha256"].items():
        if file_sha256(output / name) != digest:
            raise ValueError(f"Arquivo de saída alterado: {name}")

    items, queries, _ = select_records(dataset, "test", allow_test=True)
    item_ids = {item.id for item in items}
    expected = {query["query_id"]: query["expected_item_id"] for query in queries}
    per_query: dict[str, set[int]] = defaultdict(set)
    with (output / "pairs.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        query_id, item_id = row["query_id"], int(row["item_id"])
        if query_id not in expected or item_id not in item_ids or item_id in per_query[query_id]:
            raise ValueError("Par repetido ou fora do teste")
        if int(row["is_relevant"]) != int(item_id == expected[query_id]):
            raise ValueError("Rótulo de relevância divergente")
        per_query[query_id].add(item_id)
    if set(per_query) != set(expected) or any(ids != item_ids for ids in per_query.values()):
        raise ValueError("Produto cartesiano do teste incompleto")
    for method, setting in per_method.items():
        observed = metrics(rows, method, setting["alpha"], setting["threshold"])
        saved = summary["metrics"][method]
        for key, value in observed.items():
            if isinstance(value, dict):
                if value != saved[key]:
                    raise ValueError(f"{method}: {key} divergente")
            elif isinstance(value, float):
                if not isclose(value, saved[key], rel_tol=0, abs_tol=1e-12):
                    raise ValueError(f"{method}: {key} divergente")
            elif value != saved[key]:
                raise ValueError(f"{method}: {key} divergente")
    if "latency" in summary:
        with (output / "latency.csv").open(encoding="utf-8", newline="") as stream:
            latency_rows = list(csv.DictReader(stream))
        if len(latency_rows) != len(queries) * len(METHODS):
            raise ValueError("Quantidade de latências incorreta")
        for method in METHODS:
            selected = [row for row in latency_rows if row["method"] == method]
            if {row["query_id"] for row in selected} != set(expected) or len(selected) != len(expected):
                raise ValueError(f"{method}: latências ausentes ou repetidas")
            observed = latency_stats([float(row["server_time_ms"]) for row in selected])
            saved = summary["latency"]["statistics"][method]
            for key, value in observed.items():
                if isinstance(value, float):
                    if not isclose(value, saved[key], rel_tol=0, abs_tol=1e-9):
                        raise ValueError(f"{method}: {key} divergente")
                elif value != saved[key]:
                    raise ValueError(f"{method}: {key} divergente")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "latency", "verify"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--criterion", choices=("ranking", "pair_f1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset, output = args.dataset.resolve(), args.output.resolve()
    result = (
        freeze(dataset, output, args.criterion) if args.command == "freeze" else
        run_test(dataset, output, args.criterion) if args.command == "run" else
        measure_latency(dataset, output, args.criterion) if args.command == "latency" else
        verify(dataset, output, args.criterion)
    )
    print(json.dumps({
        "command": args.command,
        "dataset": str(dataset),
        "criterion": args.criterion,
        "output": str(output),
        "winner": result["winner"] if "winner" in result else result["config"]["winner"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
