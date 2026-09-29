from app.preprocessing import normalize_text


def test_normalize_text_removes_accents_punctuation_and_domain_stopwords() -> None:
    result = normalize_text(
        "Perdi um Celular SAMSUNG preto, com capa azul, na Biblioteca!!!"
    )

    assert result == "celular samsung preto com capa azul na biblioteca"


def test_normalize_text_accepts_empty_value() -> None:
    assert normalize_text(None) == ""
    assert normalize_text("!!!") == ""


def test_normalize_text_preserves_discriminative_attributes() -> None:
    result = normalize_text(
        "Celular Samsung Galaxy S23 azul, bloco 4, Biblioteca Central"
    )

    assert result == "celular samsung galaxy s23 azul bloco 4 biblioteca central"
