from julgame_scraper.keywords import OFFENSIVE_KEYWORDS, contains_keyword


def test_keywords_not_empty():
    """Garante que a lista semente nao esta vazia."""
    assert len(OFFENSIVE_KEYWORDS) > 0


def test_keywords_are_lowercase():
    """Garante que todos os termos estao em minusculas."""
    assert all(keyword == keyword.lower() for keyword in OFFENSIVE_KEYWORDS)


def test_contains_keyword_matches_case_insensitive():
    """Deve casar independente de maiusculas/minusculas."""
    assert contains_keyword("Ela e uma VADIA", ["vadia"])


def test_contains_keyword_no_match():
    """Nao deve casar quando nenhum termo aparece no texto."""
    assert not contains_keyword("comentario neutro sobre o dia", ["vadia"])


def test_contains_keyword_empty_body():
    """Nao deve casar em um texto vazio."""
    assert not contains_keyword("", ["vadia"])
