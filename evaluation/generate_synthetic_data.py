"""Gera um conjunto sintético de itens encontrados e consultas de avaliação."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.validate import validate_dataset


ROOT = Path(__file__).resolve().parent / "final"
COLORS = (
    "preto", "azul-marinho", "vermelho", "verde-escuro", "cinza",
    "branco", "roxo", "amarelo", "marrom", "rosa",
)
FEMININE_COLORS = (
    "preta", "azul-marinho", "vermelha", "verde-escura", "cinza",
    "branca", "roxa", "amarela", "marrom", "rosa",
)
PLURAL_COLORS = (
    "pretos", "azul-marinho", "vermelhos", "verde-escuros", "cinza",
    "brancos", "roxos", "amarelos", "marrons", "rosa",
)
FEMININE_HEADS = {
    "Calculadora", "Caixa", "Carteira", "Pulseira", "Chave", "Mochila",
    "Bolsa", "Pochete", "Sacola", "Pasta", "Nécessaire", "Ecobag",
    "Lancheira", "Capa", "Caderneta", "Régua", "Lapiseira", "Caneta",
    "Agenda", "Prancheta", "Jaqueta", "Camiseta", "Luva", "Meia",
    "Garrafa", "Caneca", "Marmita", "Bola", "Raquete", "Corda",
    "Munhequeira", "Toalha", "Faixa", "Sombrinha",
}
MARKS = (
    "pequena marca azul", "detalhe branco na borda",
    "ponto de tinta vermelha", "mancha clara discreta",
    "marca circular amarela", "sinal de desgaste",
    "faixa diagonal estreita", "pequena marca verde",
    "ponto de tinta azul", "marca em forma de estrela",
)
PLACES = (
    "Biblioteca", "Restaurante universitário", "Bloco 1",
    "Bloco 2", "Bloco 4", "Bloco 5", "Bloco 10",
    "Laboratório de informática", "Auditório", "Quadra",
    "Secretaria", "Teatro de Arena", "Recanto",
)
PLACE_SHORT = (
    "bib.", "RU", "bl. 1", "bl. 2", "bl. 4", "bl. 5", "bl. 10",
    "lab. info", "aud.", "qdr.", "sec.", "teatro", "rec.",
)
FEMININE_PLACES = {"Biblioteca", "Quadra", "Secretaria"}
TYPOS = (
    "pretu", "asul-marinho", "vermelhu", "verde-escoru", "cinsa",
    "brancu", "roxa", "amarelu", "marom", "roza",
)
NEGATIVE_MARKS = (
    "lacre holográfico", "bordado triangular laranja", "desenho de lua prateada",
    "três listras turquesa", "etiqueta violeta com losango",
    "pintura em espiral dourada", "fecho com bolinhas brancas",
    "aplique em formato de nuvem", "faixa quadriculada lilás",
    "desenho de folha prateada",
)
CATEGORIES = (
    ("Eletrônicos", (
        ("Celular", "aparelho"), ("Fone de ouvido", "fone"),
        ("Carregador portátil", "bateria portátil"), ("Pen drive", "memória USB"),
        ("Mouse", "acessório de computador"), ("Calculadora", "calculadora"),
        ("Relógio digital", "relógio"), ("Cabo USB", "cabo de carregamento"),
        ("Controle remoto", "controle"), ("Caixa de som", "alto-falante"),
    )),
    ("Acessórios", (
        ("Óculos de grau", "armação"), ("Óculos de sol", "óculos escuros"),
        ("Boné", "boné"), ("Carteira", "porta-documentos"),
        ("Cinto", "cinto"), ("Pulseira", "pulseira"),
        ("Anel", "anel"), ("Estojo de óculos", "estojo"),
        ("Lenço", "lenço"), ("Relógio de pulso", "relógio"),
    )),
    ("Chaves", (
        ("Chaveiro de metal", "molho de chaves"), ("Chaveiro de tecido", "chaveiro"),
        ("Chave simples", "chave"), ("Chave de armário", "chave pequena"),
        ("Chave de cadeado", "chave curta"), ("Chaveiro com argola", "argola de chaves"),
        ("Chave com capa", "chave encapada"), ("Chaveiro de borracha", "chaveiro"),
        ("Conjunto de duas chaves", "duas chaves"), ("Conjunto de três chaves", "três chaves"),
    )),
    ("Bolsas e mochilas", (
        ("Mochila", "bolsa de costas"), ("Bolsa tiracolo", "bolsa"),
        ("Pochete", "bolsa de cintura"), ("Sacola de tecido", "sacola"),
        ("Bolsa esportiva", "bolsa de treino"), ("Pasta de mão", "pasta"),
        ("Nécessaire", "bolsinha"), ("Ecobag", "sacola reutilizável"),
        ("Lancheira", "bolsa térmica"), ("Capa para notebook", "capa de computador"),
    )),
    ("Documentos", (
        ("Crachá sem identificação", "crachá"), ("Porta-crachá", "suporte de crachá"),
        ("Pasta sanfonada", "pasta"), ("Envelope plástico", "envelope"),
        ("Pasta com elástico", "pasta"), ("Bloco de recibos fictícios", "bloco de papel"),
        ("Caderneta sem identificação", "caderneta"), ("Porta-cartões vazio", "porta-cartões"),
        ("Fichário", "fichário"), ("Pasta de documentos vazia", "pasta vazia"),
    )),
    ("Material de estudo", (
        ("Caderno", "caderno"), ("Livro sem dedicatória", "livro"),
        ("Estojo escolar", "estojo"), ("Régua", "régua"),
        ("Lapiseira", "lapiseira"), ("Caneta", "caneta"),
        ("Marca-texto", "caneta marcadora"), ("Apagador", "borracha"),
        ("Agenda", "agenda"), ("Prancheta", "prancheta"),
    )),
    ("Vestuário", (
        ("Casaco", "agasalho"), ("Jaqueta", "jaqueta"),
        ("Camiseta", "camisa"), ("Moletom", "blusa"),
        ("Cachecol", "cachecol"), ("Luva", "luva"),
        ("Chapéu", "chapéu"), ("Colete", "colete"),
        ("Meia esportiva", "meia"), ("Capa de chuva", "capa"),
    )),
    ("Garrafas e recipientes", (
        ("Garrafa de água", "squeeze"), ("Copo térmico", "copo"),
        ("Caneca", "caneca"), ("Pote de lanche", "recipiente"),
        ("Marmita", "pote de comida"), ("Garrafa térmica", "garrafa"),
        ("Copo plástico", "copo"), ("Porta-talheres", "estojo de talheres"),
        ("Pote hermético", "pote"), ("Squeeze esportivo", "garrafa esportiva"),
    )),
    ("Esportes", (
        ("Bola de futsal", "bola"), ("Raquete de tênis", "raquete"),
        ("Corda de pular", "corda"), ("Munhequeira", "faixa de pulso"),
        ("Toalha esportiva", "toalha"), ("Óculos de natação", "óculos"),
        ("Protetor de canela", "caneleira"), ("Luva de academia", "luva"),
        ("Tapete de exercício", "colchonete"), ("Faixa elástica", "faixa de treino"),
    )),
    ("Guarda-chuvas", (
        ("Guarda-chuva compacto", "sombrinha"), ("Guarda-chuva longo", "guarda-chuva"),
        ("Sombrinha dobrável", "sombrinha"), ("Guarda-chuva infantil", "guarda-chuva"),
        ("Guarda-chuva transparente", "guarda-chuva"), ("Capa de guarda-chuva", "capa"),
        ("Guarda-chuva automático", "guarda-chuva"), ("Sombrinha de bolso", "sombrinha"),
        ("Guarda-chuva de cabo curvo", "guarda-chuva"),
        ("Guarda-chuva de cabo reto", "guarda-chuva"),
    )),
)


def _jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _colored_name(name: str, variant: int) -> str:
    if name.startswith("Óculos "):
        color = PLURAL_COLORS[variant]
    elif name.split(" ", 1)[0] in FEMININE_HEADS:
        color = FEMININE_COLORS[variant]
    else:
        color = COLORS[variant]
    return f"{name} {color}"


def generate(root: Path = ROOT) -> None:
    if root.exists():
        raise FileExistsError(f"Destino já existe: {root}")
    if len(PLACES) != len(PLACE_SHORT):
        raise ValueError("Cada local precisa de uma forma curta")
    root.mkdir(parents=True)
    items: list[dict] = []
    queries: list[dict] = []
    for batch in range(20):
        for offset in range(50):
            n = batch * 50 + offset
            category, objects = CATEGORIES[n // 100]
            name, alias = objects[(n // 10) % 10]
            variant = n % 10
            color = COLORS[variant]
            mark = MARKS[(variant + n // 10) % 10]
            place_index = (n * 3 + n // 10) % len(PLACES)
            place = PLACES[place_index]
            article = "na" if place in FEMININE_PLACES else "no"
            place_phrase = f"{article} {place}"
            short_phrase = f"{article} {PLACE_SHORT[place_index]}"
            item_id = 1001 + n
            reference_id = f"ref-final-{n + 1:04d}"
            items.append({
                "schema_version": "1.0", "item_id": item_id,
                "reference_id": reference_id, "name": _colored_name(name, variant),
                "description": f"{name} em tom {color}, com {mark}.",
                "location": place, "category": category,
                "found_on": f"2026-08-{1 + n % 28:02d}T{8 + n % 10:02d}:{n % 6}0:00-03:00",
                "status": "ACTIVE", "split": "development",
            })
            pattern = n % 10
            descriptions = (
                (f"Perdi {name.lower()} em tom {color} com {mark} {place_phrase}.",
                 ["exact_attributes", "location_cue"], "easy"),
                (f"Procuro {alias} em tom {color}; tinha {mark}.",
                 ["synonym", "omission"], "hard"),
                (f"{place_phrase.capitalize()} ficou {name.lower()} em tom {color} com {mark}.",
                 ["reordered", "exact_attributes", "location_cue"], "easy"),
                (f"Sumiu {alias} em tom {TYPOS[variant]} com {mark}.",
                 ["synonym", "typo", "omission"], "hard"),
                (f"Perdi {name.lower()} em tom {color}, com {mark}, {short_phrase}.",
                 ["abbreviation", "exact_attributes", "location_cue"], "easy"),
                (f"Acho que era {alias} em tom {color}; tinha {mark}.",
                 ["generic", "synonym", "omission"], "hard"),
                (f"Procuro {name.lower()} em tom {color} com {mark} {place_phrase}.",
                 ["exact_attributes", "location_cue"], "easy"),
                (f"Era {alias} com {mark}; deixei {place_phrase}.",
                 ["synonym", "omission", "location_cue"], "hard"),
                (f"{mark.capitalize()} em {name.lower()} de tom {color}; procurei {place_phrase}.",
                 ["reordered", "exact_attributes", "location_cue"], "easy"),
                (f"{alias.capitalize()} em tom {TYPOS[variant]} com {mark}, talvez {short_phrase}.",
                 ["typo", "abbreviation", "synonym", "location_cue"], "hard"),
            )
            query_text, noise_types, difficulty = descriptions[pattern]
            queries.append({
                "schema_version": "1.0", "query_id": f"q-{n + 1:06d}",
                "reference_id": reference_id,
                "description": query_text,
                "has_match": True, "expected_item_id": item_id,
                "split": "development", "difficulty": difficulty,
                "noise_types": noise_types,
            })
        for offset in range(10):
            n = batch * 10 + offset
            category, objects = CATEGORIES[batch // 2]
            name, alias = objects[(offset + 5 * (batch % 2)) % 10]
            place = PLACES[(n + 2) % len(PLACES)]
            place_phrase = f"{'na' if place in FEMININE_PLACES else 'no'} {place}"
            queries.append({
                "schema_version": "1.0", "query_id": f"q-{1001 + n:06d}",
                "reference_id": f"ref-final-negative-{n + 1:04d}",
                "description": (
                    f"Perdi {alias} em tom {COLORS[batch % 10]}, acabamento "
                    f"{'fosco' if batch < 10 else 'brilhante'}, com {NEGATIVE_MARKS[offset]} "
                    f"{place_phrase}."
                ),
                "has_match": False, "expected_item_id": None,
                "split": "development", "difficulty": "no_match",
                "noise_types": ["exact_attributes", "location_cue"],
            })
    _jsonl(root / "items.jsonl", items)
    _jsonl(root / "queries.jsonl", queries)
    validate_dataset(root / "items.jsonl", root / "queries.jsonl",
                     enforce_pilot_profile=False)


if __name__ == "__main__":
    generate()
