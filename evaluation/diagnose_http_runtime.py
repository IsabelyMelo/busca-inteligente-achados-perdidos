"""Diagnostica o tempo de resposta HTTP com dados de desenvolvimento."""

from __future__ import annotations

import faulthandler
from time import perf_counter

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from evaluation.evaluate import (
    EVALUATION_HEADERS, EVALUATION_KEY, FixedRepository, metrics, score_pairs,
    select_records,
)
from evaluation.finalize import FINAL


def main() -> None:
    faulthandler.enable()
    faulthandler.dump_traceback_later(10, repeat=True)
    started = perf_counter()
    items, queries, _ = select_records(FINAL, "development")
    items, queries = items[:300], queries[:360]
    print(
        f"Seleção: {len(items)} candidatos, {len(queries)} consultas "
        f"de desenvolvimento; {perf_counter() - started:.2f}s",
        flush=True,
    )
    rows = score_pairs(items, queries, include_category=False)
    print(f"Pontuação: {len(rows)} pares; {perf_counter() - started:.2f}s", flush=True)
    settings = {
        "cosine": (1.0, 0.0, 0.6),
        "levenshtein": (0.0, 1.0, 0.6),
        "hybrid": (0.5, 0.5, 0.6),
    }
    for method, (alpha, beta, threshold) in settings.items():
        metrics(rows, method, alpha, threshold)
        print(f"Métricas {method}; {perf_counter() - started:.2f}s", flush=True)
        app = create_app(
            repository=FixedRepository(items),
            settings=Settings(_env_file=None, service_api_key=EVALUATION_KEY,
                              rate_limit_per_minute=1000, match_method=method,
                              match_alpha=alpha, match_beta=beta),
        )
        print(f"Abrindo TestClient {method}; {perf_counter() - started:.2f}s", flush=True)
        with TestClient(app) as client:
            print(f"TestClient aberto {method}; {perf_counter() - started:.2f}s", flush=True)
            for index, query in enumerate(queries, start=1):
                if index <= 3:
                    print(f"Enviando {method} {index}; {perf_counter() - started:.2f}s", flush=True)
                response = client.post(
                    "/matches/search",
                    json={"description": query["description"], "top_k": 5},
                    headers=EVALUATION_HEADERS,
                )
                response.raise_for_status()
                if index <= 3:
                    print(f"Resposta {method} {index}; {perf_counter() - started:.2f}s", flush=True)
                if index % 60 == 0:
                    print(
                        f"HTTP {method}: {index}/{len(queries)}; "
                        f"{perf_counter() - started:.2f}s",
                        flush=True,
                    )
    print(f"Diagnóstico concluído em {perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
