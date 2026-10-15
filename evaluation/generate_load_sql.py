"""Gera carga e conferência MySQL para a base final em schema sintético isolado."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from evaluation.finalize import FINAL, manifest, read_jsonl, sha256


TARGET = "matching_development"
DDL = f"""CREATE TABLE `{TARGET}`.`category` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `createdAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `{TARGET}`.`item` (
  `id` int NOT NULL AUTO_INCREMENT,
  `category_id` int NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `location` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('ACTIVE','RETURNED','ARCHIVED') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ACTIVE',
  `foundOn` datetime NOT NULL,
  `createdAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updatedAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_item_category` (`category_id`),
  CONSTRAINT `fk_item_category` FOREIGN KEY (`category_id`) REFERENCES `{TARGET}`.`category` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def sql_string(value: str) -> str:
    if any(character in value for character in ("\\", "\x00", "\x1a")):
        raise ValueError("Texto contém caractere que exige escape dependente de sql_mode")
    return "'" + value.replace("'", "''") + "'"


def render(dataset: Path = FINAL) -> tuple[str, str]:
    current = manifest(dataset)
    items = sorted(read_jsonl(dataset / "items.jsonl"), key=lambda row: row["item_id"])
    categories = {name: index for index, name in enumerate(sorted({row["category"] for row in items}), start=1)}
    if len(categories) != 10 or len(items) != 1000:
        raise ValueError("Base final exige dez categorias e 1.000 itens")
    rows = []
    for item in items:
        for field in ("name", "description", "location"):
            if len(item[field]) > 255:
                raise ValueError(f"item {item['item_id']}: {field} excede varchar(255)")
        found_on = datetime.fromisoformat(item["found_on"])
        if found_on.utcoffset() != timedelta(hours=-3) or found_on.microsecond:
            raise ValueError(f"item {item['item_id']}: found_on fora de -03:00 ou com microssegundos")
        values = (
            str(item["item_id"]), str(categories[item["category"]]),
            sql_string(item["name"]), sql_string(item["description"]),
            sql_string(item["location"]), "'ACTIVE'",
            sql_string(found_on.strftime("%Y-%m-%d %H:%M:%S")),
        )
        rows.append("  (" + ", ".join(values) + ")")

    category_rows = [f"  ({identifier}, {sql_string(name)})" for name, identifier in categories.items()]
    sections = [
        "-- Recriação em matching_development: executar apenas com o schema existente e sem tabelas.",
        "-- O schema da aplicação já contém os 1.000 itens; nele, execute somente verify_load.sql.",
        "-- DDL obtido por SHOW CREATE TABLE em matching_development em 15/10/2026.",
        "-- found_on é -03:00 nos JSONL; DATETIME conserva a hora civil, sem offset.",
        "-- CREATE TABLE sem IF NOT EXISTS interrompe uma segunda carga; PKs impedem duplicação.",
        "SET NAMES utf8mb4;",
        DDL.rstrip(),
        "START TRANSACTION;",
        f"INSERT INTO `{TARGET}`.`category` (`id`, `name`) VALUES\n" + ",\n".join(category_rows) + ";",
    ]
    for offset in range(0, len(rows), 100):
        sections.append(
            f"INSERT INTO `{TARGET}`.`item` (`id`, `category_id`, `name`, `description`, `location`, `status`, `foundOn`) VALUES\n"
            + ",\n".join(rows[offset:offset + 100]) + ";"
        )
    sections.append("COMMIT;")
    load_sql = "\n\n".join(sections) + "\n"

    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    pair_hash = digest(",".join(f"{row['item_id']}:{categories[row['category']]}" for row in items))
    name_hash = digest(",".join(f"{identifier}:{name.encode('utf-8').hex().upper()}" for name, identifier in categories.items()))
    dev_ids = current["groups"]["development"]["item_ids"]
    test_ids = current["groups"]["test"]["item_ids"]
    verify_sql = f"""-- Somente leitura; confere matching_development já carregado.
SET SESSION group_concat_max_len = 65535;

SELECT COUNT(*) AS total_items, COUNT(DISTINCT id) AS distinct_item_ids,
       SUM(status = 'ACTIVE') AS active_items,
       SUM(id IN ({','.join(map(str, dev_ids))})) AS development_items,
       SUM(id IN ({','.join(map(str, test_ids))})) AS test_items
FROM `{TARGET}`.`item`;
-- Esperado: 1000, 1000, 1000, 700, 300.

SELECT COUNT(*) AS total_categories,
       SHA2(GROUP_CONCAT(CONCAT(id, ':', HEX(name)) ORDER BY id SEPARATOR ','), 256) AS category_name_sha256
FROM `{TARGET}`.`category`;
-- Esperado: 10 e {name_hash}.

SELECT SHA2(GROUP_CONCAT(CONCAT(id, ':', category_id) ORDER BY id SEPARATOR ','), 256) AS item_id_category_id_sha256
FROM `{TARGET}`.`item`;
-- Esperado: {pair_hash}.

SELECT c.id AS category_id, c.name AS category_name, COUNT(*) AS item_count
FROM `{TARGET}`.`item` AS i
JOIN `{TARGET}`.`category` AS c ON c.id = i.category_id
GROUP BY c.id, c.name ORDER BY c.id;
-- Esperado: dez linhas, 100 itens por categoria.
"""
    return load_sql, verify_sql


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=FINAL)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    load_sql, verify_sql = render(args.dataset)
    for name, content in (("load.sql", load_sql), ("verify_load.sql", verify_sql)):
        path = args.dataset / name
        if args.write:
            path.write_text(content, encoding="utf-8", newline="\n")
        elif path.read_text(encoding="utf-8") != content:
            raise ValueError(f"{name} diverge da base congelada")
    if args.write:
        (args.dataset / "manifest.json").write_text(
            json.dumps(manifest(args.dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    elif json.loads((args.dataset / "manifest.json").read_text(encoding="utf-8")) != manifest(args.dataset):
        raise ValueError("Manifesto diverge do SQL ou dos JSONL")
    print("SQL de carga e verificação conferidos para matching_development")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
