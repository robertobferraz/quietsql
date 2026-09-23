from quietsql.core.masking import mask, unmask


def test_mask_protects_identifiers_strings_numbers_dates():
    masked, mapping = mask(
        "quantas vendas da cidade 'Recife' em 2026-03 acima de 150,50 por customer_id",
        ["sales", "customer_id", "vendas"],
    )
    assert masked == "quantas XQ1 da cidade XQ2 em XQ3 acima de XQ4 por XQ5"
    assert mapping == {
        "XQ1": "vendas",
        "XQ2": "'Recife'",
        "XQ3": "2026-03",
        "XQ4": "150,50",
        "XQ5": "customer_id",
    }


def test_unmask_restores_in_any_order():
    _, mapping = mask("vendas em 'Recife'", ["vendas"])
    assert unmask("sales in XQ2 for XQ1", mapping, "orig") == "sales in 'Recife' for vendas"


def test_unmask_falls_back_when_placeholder_lost():
    _, mapping = mask("vendas em 'Recife'", ["vendas"])
    assert unmask("sales in XQ2", mapping, "orig") == "orig"


def test_unmask_restores_every_occurrence_of_a_reused_placeholder():
    _, mapping = mask("vendas em 'Recife'", ["vendas"])
    assert unmask("XQ1 XQ1 XQ2", mapping, "orig") == "vendas vendas 'Recife'"


def test_mask_is_case_insensitive_and_whole_word():
    masked, mapping = mask("Vendas de vendasx", ["vendas"])
    assert masked == "XQ1 de vendasx" and mapping["XQ1"] == "Vendas"


def test_unmask_disambiguates_ten_or_more_placeholders():
    mapping = {f"XQ{i}": f"tok{i}" for i in range(1, 11)}
    translated = " ".join(f"XQ{i}" for i in range(10, 0, -1))
    expected = " ".join(f"tok{i}" for i in range(10, 0, -1))
    assert unmask(translated, mapping, "orig") == expected


def test_unmask_does_not_match_placeholder_prefix():
    mapping = {"XQ1": "tok0", "XQ2": "tok1", "XQ10": "tok9"}
    result = unmask("XQ10 comes before XQ1 and XQ2", mapping, "ORIGINAL")
    assert result == "tok9 comes before tok0 and tok1"


def test_short_protected_names_do_not_mask_function_words():
    masked, mapping = mask("quantas vendas de março por cliente no sul", ["de", "no", "vendas"])
    assert masked == "quantas XQ1 de março por cliente no sul"
    assert mapping == {"XQ1": "vendas"}


def test_function_word_names_do_not_mask_even_when_long_enough():
    masked, mapping = mask("vendas por cliente para cada mes", ["por", "para", "cada", "cliente"])
    assert masked == "vendas por XQ1 para cada mes"
    assert mapping == {"XQ1": "cliente"}


def test_snake_case_and_dotted_short_names_stay_protected():
    masked, mapping = mask("total de a_b e s.no", ["a_b", "s.no"])
    assert masked == "total de XQ1 e XQ2"
    assert mapping == {"XQ1": "a_b", "XQ2": "s.no"}


def test_repeated_span_reuses_one_placeholder():
    masked, mapping = mask("vendas de 2026 e vendas de 2027", ["vendas"])
    assert masked == "XQ1 de XQ2 e XQ1 de XQ3"
    assert mapping == {"XQ1": "vendas", "XQ2": "2026", "XQ3": "2027"}
    assert (
        unmask("XQ1 in XQ2 and XQ1 in XQ3", mapping, "orig") == "vendas in 2026 and vendas in 2027"
    )


def test_masking_already_masked_text_changes_nothing():
    masked, _ = mask("quantas vendas de 150,50 em 2026-03 por customer_id", ["vendas", "customer"])
    again, mapping = mask(masked, ["vendas", "customer"])
    assert again == masked and mapping == {}


def test_unmask_passes_unknown_placeholders_through():
    assert unmask("sales XQ1 by XQ2", {}, "orig") == "sales XQ1 by XQ2"


def test_unmask_falls_back_when_placeholder_invented():
    mapping = {"XQ1": "vendas"}
    assert unmask("how many XQ5 by XQ1", mapping, "orig") == "orig"
