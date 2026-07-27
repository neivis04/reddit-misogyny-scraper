from julgame_scraper.scraper import contains_keyword


def test_contains_keyword_is_reexported_from_keywords():
    """Garante que `contains_keyword` continua acessivel via scraper."""
    assert contains_keyword("Ela e uma VADIA", ["vadia"])
