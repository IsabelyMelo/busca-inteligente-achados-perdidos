import re
import unicodedata


# Lista conservadora: preserva marcas, cores, locais, materiais e números.
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


def normalize_text(text: str | None) -> str:
    """Normaliza texto em português sem destruir atributos do objeto."""

    if not text:
        return ""

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

