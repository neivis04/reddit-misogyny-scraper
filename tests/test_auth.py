from reddit_scraper.auth import cookie_header_to_playwright_cookies


def test_cookie_header_to_playwright_cookies_parses_pairs():
    """Deve converter cada par nome=valor num dicionario de cookie."""
    cookies = cookie_header_to_playwright_cookies(
        "session=abc123; csrf_token=xyz789"
    )

    assert cookies == [
        {
            "name": "session",
            "value": "abc123",
            "domain": ".reddit.com",
            "path": "/",
        },
        {
            "name": "csrf_token",
            "value": "xyz789",
            "domain": ".reddit.com",
            "path": "/",
        },
    ]


def test_cookie_header_to_playwright_cookies_ignores_empty_parts():
    """Deve ignorar partes vazias ou sem "=" (ponto e virgula sobrando)."""
    cookies = cookie_header_to_playwright_cookies("session=abc123; ; ok")

    assert cookies == [
        {
            "name": "session",
            "value": "abc123",
            "domain": ".reddit.com",
            "path": "/",
        }
    ]
