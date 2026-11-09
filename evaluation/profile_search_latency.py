"""Mede as etapas da busca local sem modificar o endpoint ou os dados."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

from sqlalchemy import create_engine

import app.matching as matching
from app.config import Settings
from app.domain import ItemCandidate
from app.repository import MySQLItemRepository


ROOT = Path(__file__).resolve().parent / "v2"
OUTPUT = ROOT / "latency_profile_local.json"
ACTIVE: dict[str, float] | None = None
ORIGINAL_NORMALIZE = matching.normalize_for_matching
ORIGINAL_COSINE = matching.cosine_similarity
ORIGINAL_LEVENSHTEIN = matching.Levenshtein
ORIGINAL_VECTORIZER = matching.TfidfVectorizer


def add_time(key: str, started: float) -> None:
    if ACTIVE is not None:
        ACTIVE[key] = ACTIVE.get(key, 0.0) + (perf_counter() - started) * 1000


def timed_normalize(*args, **kwargs):
    started = perf_counter()
    try:
        return ORIGINAL_NORMALIZE(*args, **kwargs)
    finally:
        add_time("normalization_ms", started)


def timed_cosine(*args, **kwargs):
    started = perf_counter()
    try:
        return ORIGINAL_COSINE(*args, **kwargs)
    finally:
        add_time("cosine_ms", started)


class TimedLevenshtein:
    @staticmethod
    def normalized_similarity(*args, **kwargs):
        started = perf_counter()
        try:
            return ORIGINAL_LEVENSHTEIN.normalized_similarity(*args, **kwargs)
        finally:
            add_time("levenshtein_ms", started)


class TimedVectorizer(ORIGINAL_VECTORIZER):
    def fit_transform(self, *args, **kwargs):
        started = perf_counter()
        try:
            return super().fit_transform(*args, **kwargs)
        finally:
            add_time("tfidf_fit_ms", started)
            if ACTIVE is not None:
                ACTIVE["tfidf_fit_calls"] = ACTIVE.get("tfidf_fit_calls", 0) + 1

    def transform(self, *args, **kwargs):
        started = perf_counter()
        try:
            return super().transform(*args, **kwargs)
        finally:
            add_time("tfidf_query_ms", started)


class MemoryRepository:
    def __init__(self, items: list[ItemCandidate]) -> None:
        self.items = items

    def find_active_items(self) -> list[ItemCandidate]:
        return self.items


class TimedRepository:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def find_active_items(self) -> list[ItemCandidate]:
        started = perf_counter()
        try:
            result = self.delegate.find_active_items()
            if ACTIVE is not None:
                ACTIVE["item_count"] = len(result)
            return result
        finally:
            add_time("repository_ms", started)


def read_items() -> tuple[list[ItemCandidate], list[ItemCandidate]]:
    all_items = []
    test_items = []
    with (ROOT / "items.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            item = ItemCandidate(
                id=row["item_id"],
                name=row["name"],
                description=row["description"],
                location=row["location"],
                category_name=row["category"],
                found_on=datetime.fromisoformat(row["found_on"]),
            )
            all_items.append(item)
            if row["split"] == "test":
                test_items.append(item)
    if len(all_items) != 1000 or len(test_items) != 300:
        raise ValueError("Contagem de candidatos da v2 inesperada")
    return all_items, test_items


def summarize(samples: list[dict]) -> dict:
    fields = (
        "total_ms", "repository_ms", "normalization_ms", "tfidf_fit_ms",
        "tfidf_query_ms", "cosine_ms", "levenshtein_ms", "similarity_ms",
        "remaining_ms",
    )
    return {
        "calls": len(samples),
        "item_count": samples[0]["item_count"],
        "tfidf_fit_calls": sum(row.get("tfidf_fit_calls", 0) for row in samples),
        "median_ms": {key: round(median(row.get(key, 0.0) for row in samples), 3)
                      for key in fields},
        "min_total_ms": round(min(row["total_ms"] for row in samples), 3),
        "max_total_ms": round(max(row["total_ms"] for row in samples), 3),
    }


def run_scenario(name: str, repository, query: str, repeats: int) -> dict:
    global ACTIVE
    service = matching.MatchingService(TimedRepository(repository))
    samples = []
    for _ in range(repeats + 1):
        ACTIVE = {}
        started = perf_counter()
        try:
            service.search(query, top_k=5)
        finally:
            elapsed = (perf_counter() - started) * 1000
            sample = ACTIVE
            ACTIVE = None
        sample["total_ms"] = elapsed
        sample["similarity_ms"] = sum(sample.get(key, 0.0) for key in (
            "tfidf_query_ms", "cosine_ms", "levenshtein_ms",
        ))
        tracked = sum(sample.get(key, 0.0) for key in (
            "repository_ms", "normalization_ms", "tfidf_fit_ms",
            "tfidf_query_ms", "cosine_ms", "levenshtein_ms",
        ))
        sample["remaining_ms"] = max(0.0, elapsed - tracked)
        samples.append(sample)
    return {"scenario": name, "first_call": samples[0],
            "warm": summarize(samples[1:])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-db", action="store_true",
                        help="Inclui leitura do MySQL local configurado no ambiente")
    parser.add_argument("--repeats", type=int, default=12)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats deve ser positivo")

    matching.normalize_for_matching = timed_normalize
    matching.cosine_similarity = timed_cosine
    matching.Levenshtein = TimedLevenshtein
    matching.TfidfVectorizer = TimedVectorizer

    all_items, test_items = read_items()
    query = "carregador de celular branco com cabo meio descascado, acho que deixei no laboratório de informática"
    scenarios = [
        run_scenario("300 itens em memória", MemoryRepository(test_items), query, args.repeats),
        run_scenario("1000 itens em memória", MemoryRepository(all_items), query, args.repeats),
    ]
    if args.with_db:
        settings = Settings()
        engine = create_engine(settings.database_url, pool_pre_ping=True,
                               pool_recycle=1800,
                               connect_args=settings.database_connect_args)
        try:
            scenarios.append(run_scenario("1000 itens no MySQL local",
                                          MySQLItemRepository(engine), query,
                                          args.repeats))
        finally:
            engine.dispose()

    result = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "local; direct MatchingService.search call; no HTTP, Render or Aiven",
        "python": platform.python_version(),
        "items_sha256": hashlib.sha256((ROOT / "items.jsonl").read_bytes()).hexdigest(),
        "query": query,
        "repeats": args.repeats,
        "scenarios": scenarios,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    for scenario in scenarios:
        print(scenario["scenario"])
        print("  primeira chamada:", round(scenario["first_call"]["total_ms"], 3),
              "ms; ajuste TF-IDF:",
              round(scenario["first_call"].get("tfidf_fit_ms", 0), 3), "ms")
        print("  mediana aquecida:", scenario["warm"]["median_ms"],
              "ajustes:", scenario["warm"]["tfidf_fit_calls"])
    print(OUTPUT)


if __name__ == "__main__":
    main()
