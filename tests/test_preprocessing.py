from app.preprocessing import normalize_for_matching, normalize_text


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


def test_matching_aliases_use_complete_words_and_keep_attributes() -> None:
    assert normalize_for_matching("Telefone preto com capinha amarela") == (
        "celular preto com capa amarela"
    )
    assert normalize_for_matching("Smartphone e telemóvel") == "celular celular"
    assert normalize_for_matching("telefonema preto") == "telefonema preto"


def test_matching_aliases_cover_other_catalog_item_names() -> None:
    assert normalize_for_matching("Pendrive e pen-drive") == "pen drive pen drive"
    assert normalize_for_matching("Power bank e powerbank") == (
        "carregador portatil carregador portatil"
    )
    assert normalize_for_matching("Headset e fone") == "fone fone"
