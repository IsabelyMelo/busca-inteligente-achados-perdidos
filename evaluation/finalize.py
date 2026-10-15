"""Divide a base aprovada e verifica o manifesto congelado, sem pontuar consultas."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.validate import validate_dataset


FINAL = Path(__file__).resolve().parent / "final"
SOURCE_SHA256 = {
    "items.jsonl": "2c1f7c92a12f9ed903ce7933b001690d6bf923ff3824865d8602f6931d722e8d",
    "queries.jsonl": "5818b5933d01cea07ea83cadd99d10f567b5a12dd9f90c93a1af5ba4250b55c3",
}
VERSION = "1.0.0"
SEED = "final-v1-reference-stratified"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def expected_splits(items: list[dict], queries: list[dict]) -> dict[str, str]:
    by_category: dict[str, list[str]] = defaultdict(list)
    for item in items:
        by_category[item["category"]].append(item["reference_id"])
    if len(items) != 1000 or len(by_category) != 10 or any(len(refs) != 100 for refs in by_category.values()):
        raise ValueError("Esperados 1.000 itens, 100 em cada uma das dez categorias")

    def ordered(refs: list[str]) -> list[str]:
        return sorted(refs, key=lambda ref: (hashlib.sha256(f"{SEED}:{ref}".encode()).hexdigest(), ref))

    result = {}
    for refs in by_category.values():
        for index, ref in enumerate(ordered(refs)):
            result[ref] = "development" if index < 70 else "test"
    negative_refs = {query["reference_id"] for query in queries if not query["has_match"]}
    if len(negative_refs) != 200:
        raise ValueError("Esperadas 200 referências negativas distintas")
    for index, ref in enumerate(ordered(list(negative_refs))):
        if ref in result:
            raise ValueError(f"Referência negativa coincide com item: {ref}")
        result[ref] = "development" if index < 140 else "test"
    return result


def manifest(dataset: Path) -> dict:
    items_path, queries_path = dataset / "items.jsonl", dataset / "queries.jsonl"
    validate_dataset(items_path, queries_path, enforce_pilot_profile=False)
    items, queries = read_jsonl(items_path), read_jsonl(queries_path)
    allocation = expected_splits(items, queries)
    if any(row["split"] != allocation[row["reference_id"]] for row in [*items, *queries]):
        raise ValueError("Split diverge da regra determinística por reference_id")
    if set(row["split"] for row in [*items, *queries]) != {"development", "test"}:
        raise ValueError("Os dois splits são obrigatórios")
    groups = {}
    for split in ("development", "test"):
        selected_items = [row for row in items if row["split"] == split]
        selected_queries = [row for row in queries if row["split"] == split]
        groups[split] = {
            "item_count": len(selected_items),
            "query_count": len(selected_queries),
            "positive_queries": sum(row["has_match"] for row in selected_queries),
            "negative_queries": sum(not row["has_match"] for row in selected_queries),
            "categories": dict(sorted(Counter(row["category"] for row in selected_items).items())),
            "difficulties": dict(sorted(Counter(row["difficulty"] for row in selected_queries).items())),
            "noise_types": dict(sorted(Counter(noise for row in selected_queries for noise in row["noise_types"]).items())),
            "item_ids": sorted(row["item_id"] for row in selected_items),
            "query_ids": sorted(row["query_id"] for row in selected_queries),
        }
    if (groups["development"]["item_count"], groups["test"]["item_count"]) != (700, 300):
        raise ValueError("Divisão dos itens deve ser 700/300")
    if (groups["development"]["query_count"], groups["test"]["query_count"]) != (840, 360):
        raise ValueError("Divisão das consultas deve ser 840/360")
    result = {
        "dataset_version": VERSION,
        "schema_version": "1.0",
        "human_approval": "2026-10-14; item_id 1001-2000, query_id q-000001-q-001200; sem correções ou descartes comunicados",
        "rule": f"SHA-256 de '{SEED}:<reference_id>'; 70 menores hashes por categoria de 100 itens e 140 menores hashes entre 200 referências negativas ficam em development; demais em test",
        "source_sha256_before_split": SOURCE_SHA256,
        "sha256": {name: sha256(dataset / name) for name in ("items.jsonl", "queries.jsonl")},
        "groups": groups,
    }
    sql_names = ("load.sql", "verify_load.sql")
    if all((dataset / name).is_file() for name in sql_names):
        sql_hashes = {name: sha256(dataset / name) for name in sql_names}
        result["sql"] = {
            "target_schema": "matching_development",
            "status": "generated_for_loaded_development_schema",
            "sha256": sql_hashes,
        }
    else:
        result["sql"] = {"status": "pending_generation"}
    return result


def write_split(dataset: Path) -> None:
    for name, expected in SOURCE_SHA256.items():
        if sha256(dataset / name) != expected:
            raise ValueError(f"{name}: SHA-256 difere do arquivo aprovado antes da divisão")
    items, queries = read_jsonl(dataset / "items.jsonl"), read_jsonl(dataset / "queries.jsonl")
    validate_dataset(dataset / "items.jsonl", dataset / "queries.jsonl", enforce_pilot_profile=False)
    if any(row["split"] != "development" for row in [*items, *queries]):
        raise ValueError("Os arquivos de entrada já possuem split não provisório")
    allocation = expected_splits(items, queries)
    for name, rows in (("items.jsonl", items), ("queries.jsonl", queries)):
        path = dataset / name
        raw = path.read_bytes()
        lines = raw.splitlines(keepends=True)
        if len(lines) != len(rows):
            raise ValueError(f"{name}: contagem de linhas inesperada")
        for index, row in enumerate(rows):
            if allocation[row["reference_id"]] == "test":
                if lines[index].count(b'"split":"development"') != 1:
                    raise ValueError(f"{name}: campo split inesperado na linha {index + 1}")
                lines[index] = lines[index].replace(b'"split":"development"', b'"split":"test"')
        path.write_bytes(b"".join(lines))
    result = manifest(dataset)
    (dataset / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_development(dataset: Path = FINAL) -> tuple[list[dict], list[dict]]:
    """Carrega apenas candidatos e consultas de desenvolvimento; teste fica fechado até E07."""
    expected = manifest(dataset)
    saved = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if expected != saved:
        raise ValueError("Manifesto diverge dos JSONL congelados")
    items = [row for row in read_jsonl(dataset / "items.jsonl") if row["split"] == "development"]
    queries = [row for row in read_jsonl(dataset / "queries.jsonl") if row["split"] == "development"]
    if sorted(row["item_id"] for row in items) != saved["groups"]["development"]["item_ids"]:
        raise ValueError("IDs de desenvolvimento divergem do manifesto")
    if sorted(row["query_id"] for row in queries) != saved["groups"]["development"]["query_ids"]:
        raise ValueError("Consultas de desenvolvimento divergem do manifesto")
    return items, queries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=FINAL)
    parser.add_argument("--write", action="store_true", help="Divide somente os dois arquivos aprovados originais")
    args = parser.parse_args()
    if args.write:
        write_split(args.dataset)
    expected = manifest(args.dataset)
    saved = json.loads((args.dataset / "manifest.json").read_text(encoding="utf-8"))
    if expected != saved:
        raise ValueError("Manifesto diverge dos JSONL congelados")
    print(f"Dataset {VERSION} verificado: 700/300 itens, 840/360 consultas; SHA-256 conferidos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
