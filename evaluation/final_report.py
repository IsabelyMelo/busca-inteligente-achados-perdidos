"""Deriva tabelas e exemplos de erro das saídas brutas congeladas do teste."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from evaluation.evaluate import file_sha256, metrics, score
from evaluation.final_experiment import LOCK
from evaluation.finalize import FINAL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FINAL / "test_results_retry_2")
    output = parser.parse_args().output
    # Lê a configuração histórica sem exigir que o código atual tenha o mesmo hash
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if summary["pretest_config_sha256"] != file_sha256(LOCK):
        raise ValueError("Configuração pré-teste divergente")
    for name, digest in summary["output_sha256"].items():
        if file_sha256(output / name) != digest:
            raise ValueError(f"Saída bruta divergente: {name}")
    with (output / "pairs.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (output / "latency.csv").open(encoding="utf-8", newline="") as stream:
        latency_rows = list(csv.DictReader(stream))
    if len(rows) != 108000 or len(latency_rows) != 1080:
        raise ValueError("Contagem de pares ou latências inesperada")
    manifest = json.loads((FINAL / "manifest.json").read_text(encoding="utf-8"))
    if {int(row["item_id"]) for row in rows} != set(manifest["groups"]["test"]["item_ids"]):
        raise ValueError("Pares contêm itens fora do split de teste")
    if {row["query_id"] for row in rows} != set(manifest["groups"]["test"]["query_ids"]):
        raise ValueError("Pares contêm consultas fora do split de teste")
    lines = ["# Resultados derivados do teste final", "",
             f"Fonte: `pairs.csv` ({summary['output_sha256']['pairs.csv']}) e `latency.csv` ({summary['output_sha256']['latency.csv']}).",
             f"Configuração pré-teste: `{summary['pretest_config_sha256']}`.", "",
             "## Qualidade", "",
             "| Método | α | Limiar | Precisão | Revocação | F1 | Hit@1 | Hit@3 | Hit@5 | MRR | TP | FP | TN | FN |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    by_query = defaultdict(list)
    for row in rows:
        by_query[row["query_id"]].append(row)
    for method, setting in lock["per_method"].items():
        result = metrics(rows, method, setting["alpha"], setting["threshold"])
        if result != summary["metrics"][method]:
            raise ValueError(f"Métricas de {method} não reproduzem o resumo")
        cm = result["confusion_matrix"]
        values = [method, str(setting["alpha"]), str(setting["threshold"])]
        values += [f"{result[key]:.4f}" for key in
                   ("precision", "recall", "f1", "hit_at_1", "hit_at_3", "hit_at_5", "mrr")]
        values += [str(cm[key]) for key in ("tp", "fp", "tn", "fn")]
        lines.append("| " + " | ".join(values) + " |")
    lines += ["", "## Latência do servidor via HTTP", "",
              "| Método | N | Média (ms) | Mediana (ms) | Desvio padrão (ms) | P95 (ms) |",
              "|---|---:|---:|---:|---:|---:|"]
    for method in lock["per_method"]:
        result = summary["latency"]["statistics"][method]
        values = [method, str(result["count"])] + [f"{result[key]:.3f}" for key in
            ("mean_ms", "median_ms", "stddev_ms", "p95_ms")]
        lines.append("| " + " | ".join(values) + " |")
    winner = lock["winner"]
    method, alpha = winner["method"], winner["alpha"]
    query_data = {row["query_id"]: row for row in
                  (json.loads(line) for line in (FINAL / "queries.jsonl").read_text(encoding="utf-8").splitlines())
                  if row["split"] == "test"}
    misses = []
    false_positive_queries = []
    for query_id, candidates in by_query.items():
        ordered = sorted(candidates, key=lambda row: (-score(row, method, alpha), int(row["item_id"])))
        query = query_data[query_id]
        if query["has_match"]:
            rank = next(index for index, row in enumerate(ordered, 1) if int(row["is_relevant"]))
            if rank > 1:
                misses.append((rank, query_id, query, ordered[0], ordered[rank - 1]))
        elif score(ordered[0], method, alpha) >= winner["threshold"]:
            false_positive_queries.append((score(ordered[0], method, alpha), query_id, query, ordered[0]))
    misses.sort(key=lambda entry: (-entry[0], entry[1]))
    false_positive_queries.sort(key=lambda entry: (-entry[0], entry[1]))
    lines += ["", "## Exemplos de erro do método escolhido no desenvolvimento", "",
              f"Método: {method}; pesos α={alpha}, β={winner['beta']}; limiar={winner['threshold']}. "
              "Os exemplos abaixo foram selecionados depois da execução, sem ajuste do método.", "",
              "### Correspondência fora do primeiro resultado", ""]
    for rank, query_id, query, top, relevant in misses[:5]:
        lines.append(f"- `{query_id}` ({query['difficulty']}): posição esperada {rank}, item esperado "
                     f"`{relevant['item_id']}`, primeiro item `{top['item_id']}`; descrição: “{query['description']}”.")
    if not misses:
        lines.append("- Nenhum caso no teste.")
    lines += ["", "### Consulta sem correspondência acima do limiar", ""]
    for value, query_id, query, top in false_positive_queries[:5]:
        lines.append(f"- `{query_id}`: primeiro item `{top['item_id']}`, escore {value:.4f}; "
                     f"descrição: “{query['description']}”.")
    if not false_positive_queries:
        lines.append("- Nenhum caso no teste.")
    lines += ["", "## Limites de interpretação", "",
              "A base é sintética e curada, com uma correspondência principal por consulta positiva. "
              "A classificação usa todos os pares e, por isso, é fortemente desbalanceada. "
              "A latência foi medida com TestClient local e catálogo em memória; não representa implantação remota ou consulta MySQL.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Relatório derivado: {output / 'report.md'}; exemplos: {len(misses)} erros de topo, "
          f"{len(false_positive_queries)} consultas negativas acima do limiar")


if __name__ == "__main__":
    main()
