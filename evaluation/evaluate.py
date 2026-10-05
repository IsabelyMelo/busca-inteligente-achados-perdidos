"""Avaliação simples por par consulta--candidato, sem acesso ao banco original."""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import ItemCandidate
from app.main import create_app
from app.matching import MatchingService
from evaluation.validate import validate_dataset


PILOT = Path(__file__).resolve().parent / "pilot" / "v0.1.0"
WEIGHTS = (0.25, 0.5, 0.75)
THRESHOLDS = (0.2, 0.4, 0.6)


class FixedRepository:
    def __init__(self, items: list[ItemCandidate]) -> None:
        self.items = items

    def find_active_items(self) -> list[ItemCandidate]:
        return self.items


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def score_pairs(
    items: list[ItemCandidate], queries: list[dict], *, include_category: bool
) -> list[dict]:
    service = MatchingService(
        FixedRepository(items), include_category=include_category
    )
    rows = []
    for query in queries:
        # search ajusta o TF-IDF só aos candidatos e calcula ambos os escores uma vez.
        for result in service.search(query["description"], top_k=len(items)):
            rows.append(
                {
                    "query_id": query["query_id"],
                    "item_id": result.item.id,
                    "expected_item_id": query["expected_item_id"] or "",
                    "is_relevant": int(result.item.id == query["expected_item_id"]),
                    "cosine_score": result.cosine_score,
                    "levenshtein_score": result.levenshtein_score,
                }
            )
    return rows


def score(row: dict, method: str, alpha: float = 0.5) -> float:
    cosine = float(row["cosine_score"])
    levenshtein = float(row["levenshtein_score"])
    if method == "cosine":
        return cosine
    if method == "levenshtein":
        return levenshtein
    return alpha * cosine + (1 - alpha) * levenshtein


def metrics(rows: list[dict], method: str, alpha: float, threshold: float) -> dict:
    tp = fp = tn = fn = 0
    ranks: dict[str, list[tuple[float, int, int]]] = {}
    for row in rows:
        value = score(row, method, alpha)
        relevant = bool(int(row["is_relevant"]))
        predicted = value >= threshold
        if relevant and predicted:
            tp += 1
        elif relevant:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
        ranks.setdefault(str(row["query_id"]), []).append(
            (value, int(row["item_id"]), int(relevant))
        )
    positive_ranks = []
    for candidates in ranks.values():
        ordered = sorted(candidates, key=lambda entry: (-entry[0], entry[1]))
        for position, (_, _, relevant) in enumerate(ordered, start=1):
            if relevant:
                positive_ranks.append(position)
                break
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "pairs": len(rows),
        "positive_pairs": tp + fn,
        "negative_pairs": tn + fp,
        "queries": len(ranks),
        "positive_queries": len(positive_ranks),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "hit_at_1": sum(rank <= 1 for rank in positive_ranks) / len(positive_ranks) if positive_ranks else 0.0,
        "hit_at_3": sum(rank <= 3 for rank in positive_ranks) / len(positive_ranks) if positive_ranks else 0.0,
        "hit_at_5": sum(rank <= 5 for rank in positive_ranks) / len(positive_ranks) if positive_ranks else 0.0,
        "mrr": sum(1 / rank for rank in positive_ranks) / len(positive_ranks) if positive_ranks else 0.0,
    }


def latency_stats(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean_ms": statistics.mean(values),
        "median_ms": statistics.median(values),
        "stddev_ms": statistics.pstdev(values),
        "p95_ms": float(np.percentile(values, 95)),
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def memory_bytes() -> int | None:
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                        ("total_physical", ctypes.c_ulonglong),
                        ("available_physical", ctypes.c_ulonglong),
                        ("total_page_file", ctypes.c_ulonglong),
                        ("available_page_file", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong),
                        ("available_virtual", ctypes.c_ulonglong),
                        ("available_extended_virtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        return status.total_physical if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
    if hasattr(os, "sysconf"):
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    return None


def git_revision() -> dict:
    root = Path(__file__).resolve().parent.parent
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    return {"head": head, "working_tree_dirty": bool(status)}


def run(dataset: Path, output: Path, split: str) -> dict:
    started_at = perf_counter()
    if split == "test":
        raise ValueError("O conjunto de teste está reservado para E07")
    paths = [dataset / name for name in ("items.jsonl", "queries.jsonl", "provenance.json")]
    validation = validate_dataset(*paths, enforce_pilot_profile=(split == "pilot_development"))
    all_items = load_jsonl(paths[0])
    all_queries = load_jsonl(paths[1])
    items = [
        ItemCandidate(
            id=row["item_id"], name=row["name"], description=row["description"],
            location=row["location"], category_name=row["category"],
            found_on=datetime.fromisoformat(row["found_on"]),
        )
        for row in all_items if row["split"] == split and row["status"] == "ACTIVE"
    ]
    queries = [row for row in all_queries if row["split"] == split]
    if not items or not queries:
        raise ValueError(f"Split {split} sem candidatos ou consultas")
    items.sort(key=lambda item: item.id)
    queries.sort(key=lambda query: query["query_id"])

    # Comparação D03 pré-definida, sem grade: híbrido 0,5 e limiar 0,4.
    with_category = score_pairs(items, queries, include_category=True)
    without_category = score_pairs(items, queries, include_category=False)
    ablation = {
        "with_category": metrics(with_category, "hybrid", 0.5, 0.4),
        "without_category": metrics(without_category, "hybrid", 0.5, 0.4),
    }
    # Hit@1, MRR e F1; empate favorece texto menor, sem categoria.
    def field_key(result: dict) -> tuple:
        return result["hit_at_1"], result["mrr"], result["f1"]

    include_category = field_key(ablation["with_category"]) > field_key(ablation["without_category"])
    rows = with_category if include_category else without_category
    field_choice = "with_category" if include_category else "without_category"
    alternative = without_category if include_category else with_category
    alternative_by_pair = {
        (row["query_id"], row["item_id"]): row for row in alternative
    }
    for row in rows:
        other = alternative_by_pair[(row["query_id"], row["item_id"])]
        row["alternative_cosine_score"] = other["cosine_score"]
        row["alternative_levenshtein_score"] = other["levenshtein_score"]

    grid = []
    for method in ("cosine", "levenshtein", "hybrid"):
        for alpha in (WEIGHTS if method == "hybrid" else (1.0 if method == "cosine" else 0.0,)):
            for threshold in THRESHOLDS:
                grid.append({
                    "method": method, "alpha": alpha, "beta": 1 - alpha,
                    "threshold": threshold,
                    "metrics": metrics(rows, method, alpha, threshold),
                })
    # Regra da metodologia: F1, precisão e maior limiar; pesos e método fixam último empate.
    method_order = {"cosine": 2, "levenshtein": 1, "hybrid": 0}
    def grid_key(entry: dict) -> tuple:
        result = entry["metrics"]
        return (result["f1"], result["precision"], entry["threshold"],
                method_order[entry["method"]], entry["alpha"])

    selected = max(grid, key=grid_key)
    # Passagem independente pela rota HTTP real, com o mesmo catálogo do split.
    latency_rows = []
    for method in ("cosine", "levenshtein", "hybrid"):
        best = max((entry for entry in grid if entry["method"] == method), key=grid_key)
        app = create_app(
            repository=FixedRepository(items),
            settings=Settings(match_method=method, match_alpha=best["alpha"], match_beta=best["beta"]),
        )
        with TestClient(app) as client:
            for query in queries:
                response = client.post(
                    "/matches/search", json={"description": query["description"], "top_k": 5}
                )
                response.raise_for_status()
                latency_rows.append({
                    "query_id": query["query_id"], "method": method,
                    "server_time_ms": float(response.headers["X-Server-Time-Ms"]),
                })
    latency = {
        method: latency_stats([row["server_time_ms"] for row in latency_rows if row["method"] == method])
        for method in ("cosine", "levenshtein", "hybrid")
    }
    output.mkdir(parents=True, exist_ok=True)
    with (output / "pairs.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output / "latency.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(latency_rows[0]))
        writer.writeheader()
        writer.writerows(latency_rows)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_duration_seconds": perf_counter() - started_at,
        "dataset": str(dataset.resolve()), "split": split,
        "input_sha256": {path.name: file_sha256(path) for path in paths},
        "code": {**git_revision(), "sha256": {
            str(path): file_sha256(Path(__file__).resolve().parent.parent / path)
            for path in ("evaluation/evaluate.py", "app/matching.py", "app/main.py")
        }},
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "processor": platform.processor(), "memory_bytes": memory_bytes()},
        "validation": {"items": validation.item_count, "queries": validation.query_count},
        "field_ablation": {"fixed_alpha": 0.5, "fixed_threshold": 0.4, "metrics": ablation, "selected": field_choice},
        "grid": {"weights": WEIGHTS, "thresholds": THRESHOLDS, "selection_rule": "max F1, precision, threshold, method order cosine/levenshtein/hybrid, alpha", "results": grid, "selected": selected},
        "latency": {"measurement": "server-side HTTP middleware, request to response object; independent calls through TestClient, no grid reuse", "top_k": 5, "statistics": latency},
        "output_sha256": {name: file_sha256(output / name) for name in ("pairs.csv", "latency.csv")},
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia o piloto de desenvolvimento.")
    parser.add_argument("--dataset", type=Path, default=PILOT)
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/pilot-v0.1.0"))
    parser.add_argument("--split", choices=("pilot_development", "development"), default="pilot_development")
    arguments = parser.parse_args()
    result = run(arguments.dataset, arguments.output, arguments.split)
    print(json.dumps({"field_choice": result["field_ablation"]["selected"],
                      "selected": result["grid"]["selected"], "output": str(arguments.output)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
