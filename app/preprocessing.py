import re
import unicodedata


# Lista conservadora: preserva marcas, cores, locais, materiais e números
DOMAIN_STOPWORDS = {
    "a",
    "as",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "eu",
    "meu",
    "minha",
    "o",
    "os",
    "perdi",
    "perdida",
    "perdido",
    "um",
    "uma",
}

# Formas equivalentes usadas somente na comparação. As chaves e os valores já estão normalizados, expressões com mais de uma palavra vêm primeiro
MATCHING_ALIASES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("power", "bank"): ("carregador", "portatil"),
    ("telefone",): ("celular",),
    ("smartphone",): ("celular",),
    ("capinha",): ("capa",),
    ("pendrive",): ("pen", "drive"),
    ("powerbank",): ("carregador", "portatil"),
    ("headphone",): ("fone",),
    ("headphones",): ("fone",),
    ("headset",): ("fone",),
}


def normalize_text(text: str | None) -> str:
    """Normaliza texto em português sem destruir atributos do objeto."""

    if not text:
        return ""

    # Uniformiza caixa, acentos e pontuação antes de retirar palavras comuns
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    alphanumeric = re.sub(r"[^a-z0-9]+", " ", without_accents)
    tokens = (
        token
        for token in alphanumeric.split()
        if token not in DOMAIN_STOPWORDS
    )
    return " ".join(tokens)


def normalize_for_matching(text: str | None) -> str:
    """Normaliza e substitui sinônimos completos por uma forma canônica"""

    tokens = normalize_text(text).split()
    canonical: list[str] = []
    position = 0
    while position < len(tokens):
        for alias, replacement in MATCHING_ALIASES.items():
            if tuple(tokens[position : position + len(alias)]) == alias:
                canonical.extend(replacement)
                position += len(alias)
                break
        else:
            canonical.append(tokens[position])
            position += 1
    return " ".join(canonical)

