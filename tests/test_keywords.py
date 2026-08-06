from reddit_scraper.keywords import (
    OFFENSIVE_KEYWORDS_BY_CATEGORY,
    format_matches,
    match_categories,
)

SAMPLE_CATEGORIES = {
    "Sexualidade": ["vadia", "piranha"],
    "Capacidade cognitiva": ["burra"],
}


def test_categories_not_empty():
    """Garante que a lista semente tem categorias e termos."""
    assert len(OFFENSIVE_KEYWORDS_BY_CATEGORY) > 0
    assert all(
        len(terms) > 0 for terms in OFFENSIVE_KEYWORDS_BY_CATEGORY.values()
    )


def test_match_categories_matches_case_insensitive():
    """Deve casar independente de maiusculas/minusculas."""
    matches = match_categories("Ela e uma VADIA", SAMPLE_CATEGORIES)
    assert matches == {"Sexualidade": ["vadia"]}


def test_match_categories_multiple_categories():
    """Deve retornar todas as categorias com termo encontrado."""
    matches = match_categories("burra e vadia", SAMPLE_CATEGORIES)
    assert matches == {
        "Sexualidade": ["vadia"],
        "Capacidade cognitiva": ["burra"],
    }


def test_match_categories_no_match():
    """Nao deve retornar categorias quando nenhum termo aparece."""
    text = "comentario neutro sobre o dia"
    matches = match_categories(text, SAMPLE_CATEGORIES)
    assert matches == {}


def test_match_categories_respects_word_boundary():
    """Nao deve casar um termo curto no meio de outra palavra."""
    matches = match_categories("vou andar ate a padaria", {"X": ["dar"]})
    assert matches == {}


def test_match_categories_matches_inflected_forms():
    """Deve casar variacoes com sufixo (plural, diminutivo etc.)."""
    matches = match_categories("que vadias", {"Sexualidade": ["vadia"]})
    assert matches == {"Sexualidade": ["vadia"]}


def test_format_matches_empty():
    """Deve formatar um dicionario vazio como duas strings vazias."""
    assert format_matches({}) == ("", "")


def test_format_matches_multiple_categories():
    """Deve formatar categorias e termos na mesma ordem, pareados."""
    matches = {
        "Sexualidade": ["vadia", "piranha"],
        "Capacidade cognitiva": ["burra"],
    }
    categories, keywords = format_matches(matches)
    assert categories == "Sexualidade; Capacidade cognitiva"
    assert keywords == "vadia, piranha; burra"
