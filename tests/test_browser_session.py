from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from reddit_scraper.browser_session import BrowserSession, LoginRequiredError


class _FakePage:
    def __init__(self, url: str, content: str = "") -> None:
        self.url = url
        self._content = content
        self.closed = False

    def goto(self, _url, wait_until=None, timeout=None):
        return None

    def wait_for_selector(self, _selector, timeout=None):
        return None

    def content(self) -> str:
        return self._content

    def close(self) -> None:
        self.closed = True


class _FakeAPIResponse:
    def __init__(
        self,
        url: str,
        json_data: dict | None = None,
        ok: bool = True,
        status: int = 200,
        status_text: str = "OK",
    ) -> None:
        self.url = url
        self._json_data = json_data or {}
        self.ok = ok
        self.status = status
        self.status_text = status_text

    def json(self) -> dict:
        return self._json_data


class _FakeRequestContext:
    def __init__(self, response: _FakeAPIResponse) -> None:
        self._response = response

    def get(self, _url, params=None, timeout=None):
        return self._response


class _FakeContext:
    def __init__(self, page: _FakePage, request=None) -> None:
        self._page = page
        self.request = request

    def new_page(self) -> _FakePage:
        return self._page


def _make_session(context: _FakeContext) -> BrowserSession:
    session = object.__new__(BrowserSession)
    session._context = context
    return session


def test_fetch_html_raises_when_redirected_to_login():
    """Redirecionamento para /login/ deve virar LoginRequiredError."""
    login_url = (
        "https://old.reddit.com/login/?reason=lor2&dest=https%3A%2F%2F"
        "old.reddit.com%2Fr%2Fsub%2Fcomments%2Fabc123%2Ftitulo%2F"
    )
    page = _FakePage(login_url)
    session = _make_session(_FakeContext(page))

    try:
        session.fetch_html(
            "https://old.reddit.com/r/sub/comments/abc123/titulo/"
        )
        raised = False
    except LoginRequiredError:
        raised = True

    assert raised
    assert page.closed


def test_fetch_html_returns_content_when_not_redirected():
    """Sem redirecionamento para login, deve devolver o HTML renderizado."""
    page = _FakePage(
        "https://old.reddit.com/r/sub/comments/abc123/titulo/",
        content="<html>conteudo</html>",
    )
    session = _make_session(_FakeContext(page))

    html = session.fetch_html(
        "https://old.reddit.com/r/sub/comments/abc123/titulo/"
    )

    assert html == "<html>conteudo</html>"


class _SlowPage(_FakePage):
    """Pagina cujo conteudo esperado nunca aparece a tempo."""

    def wait_for_selector(self, _selector, timeout=None):
        raise PlaywrightTimeoutError("timeout esperando o seletor")


def test_fetch_html_returns_content_even_if_selector_times_out():
    """Timeout esperando o conteudo nao deve derrubar a chamada."""
    page = _SlowPage(
        "https://old.reddit.com/r/sub/comments/abc123/titulo/",
        content="<html>conteudo incompleto</html>",
    )
    session = _make_session(_FakeContext(page))

    html = session.fetch_html(
        "https://old.reddit.com/r/sub/comments/abc123/titulo/"
    )

    assert html == "<html>conteudo incompleto</html>"


def test_resolve_url_returns_final_url_after_redirect():
    """Deve devolver a URL final apos a navegacao, para links /s/..."""
    page = _FakePage("https://old.reddit.com/r/sub/comments/abc123/titulo/")
    session = _make_session(_FakeContext(page))

    final_url = session.resolve_url("https://old.reddit.com/r/sub/s/xyz")

    assert final_url == "https://old.reddit.com/r/sub/comments/abc123/titulo/"


def test_fetch_json_returns_decoded_payload():
    """Deve devolver o corpo JSON quando a resposta e bem sucedida."""
    response = _FakeAPIResponse(
        "https://old.reddit.com/api/morechildren.json",
        json_data={"json": {"data": {"things": []}}},
    )
    session = _make_session(
        _FakeContext(None, request=_FakeRequestContext(response))
    )

    payload = session.fetch_json(
        "https://old.reddit.com/api/morechildren.json", {"a": "b"}
    )

    assert payload == {"json": {"data": {"things": []}}}


def test_fetch_json_raises_login_required_on_redirect():
    """Redirecionamento para /login/ deve virar LoginRequiredError."""
    response = _FakeAPIResponse(
        "https://old.reddit.com/login/?dest=foo",
    )
    session = _make_session(
        _FakeContext(None, request=_FakeRequestContext(response))
    )

    try:
        session.fetch_json(
            "https://old.reddit.com/api/morechildren.json", {}
        )
        raised = False
    except LoginRequiredError:
        raised = True

    assert raised


def test_fetch_json_raises_runtime_error_on_failed_status():
    """Status de erro na resposta deve virar RuntimeError."""
    response = _FakeAPIResponse(
        "https://old.reddit.com/api/morechildren.json",
        ok=False,
        status=500,
        status_text="Internal Server Error",
    )
    session = _make_session(
        _FakeContext(None, request=_FakeRequestContext(response))
    )

    try:
        session.fetch_json(
            "https://old.reddit.com/api/morechildren.json", {}
        )
        raised = False
    except RuntimeError:
        raised = True

    assert raised
