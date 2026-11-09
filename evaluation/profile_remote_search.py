"""Registra as etapas de buscas autenticadas sem armazenar a credencial."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

import httpx


OUTPUT = Path(__file__).resolve().parent / "v2" / "latency_profile_remote.json"
DEFAULT_URL = "https://busca-inteligente-achados-perdidos.onrender.com/matches/search"
QUERY = "carregador de celular branco com cabo meio descascado, acho que deixei no laboratório de informática"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--repeats", type=int, default=6)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 20:
        parser.error("--repeats deve estar entre 1 e 20")
    key = os.environ.get("SERVICE_API_KEY")
    if not key:
        parser.error("Defina SERVICE_API_KEY somente no ambiente antes de executar")

    samples = []
    with httpx.Client(timeout=120.0) as client:
        for number in range(args.repeats + 1):
            started = perf_counter()
            response = client.post(
                args.url,
                json={"description": QUERY, "top_k": 5},
                headers={"X-Service-Key": key, "X-Profile-Timings": "1"},
            )
            client_ms = (perf_counter() - started) * 1000
            if response.status_code != 200:
                raise RuntimeError(f"Busca {number + 1}: HTTP {response.status_code}")
            profile_header = response.headers.get("X-Search-Profile")
            if not profile_header:
                raise RuntimeError("A revisão publicada não devolveu X-Search-Profile")
            profile = json.loads(profile_header)
            sample = {
                "call": number + 1,
                "client_ms": round(client_ms, 3),
                "server_ms": float(response.headers["X-Server-Time-Ms"]),
                "processing_ms": float(response.json()["processing_time_ms"]),
                "profile": profile,
            }
            samples.append(sample)
            print(
                f"Chamada {number + 1}: processamento={sample['processing_ms']:.1f} ms, "
                f"banco={profile['repository_ms']:.1f} ms, "
                f"preparação={profile['prepare_items_ms']:.1f} ms, "
                f"TF-IDF={profile['tfidf_fit_ms']:.1f} ms, "
                f"cosseno={profile['cosine_ms']:.1f} ms, "
                f"ranking={profile['ranking_ms']:.1f} ms",
            )

    warm = samples[1:]
    fields = (
        "repository_ms", "prepare_items_ms", "tfidf_fit_ms", "cosine_ms",
        "ranking_ms", "total_ms",
    )
    result = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "query_id": "q-000002",
        "query_text_stored": False,
        "credential_stored": False,
        "first_call": samples[0],
        "warm_calls": len(warm),
        "warm_median_ms": {
            "client_ms": round(median(row["client_ms"] for row in warm), 3),
            "server_ms": round(median(row["server_ms"] for row in warm), 3),
            "processing_ms": round(median(row["processing_ms"] for row in warm), 3),
            **{key: round(median(row["profile"][key] for row in warm), 3)
               for key in fields},
        },
        "warm_samples": warm,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
