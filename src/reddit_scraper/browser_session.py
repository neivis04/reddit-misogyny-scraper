"""Sessao de navegador real (Playwright/Chromium) para acessar o Reddit.

Em testes com `requests`, o Reddit passou a devolver 403 "Blocked" mesmo
em old.reddit.com, mesmo com cookie de sessao valido, headers de
navegador e IP residencial -- um sinal de bloqueio pela "impressao
digital" da conexao (TLS/HTTP) da biblioteca, nao so por headers ou
falta de login. Um navegador real nao tem esse problema, porque e
genuinamente um navegador: o Chromium controlado aqui pelo Playwright
gera o mesmo tipo de conexao que um Chrome comum.

O cookie configurado em `reddit_scraper.auth` (`REDDIT_COOKIE`) e
injetado no contexto do navegador antes de qualquer navegacao, via
`BrowserContext.add_cookies`.
"""

from __future__ import annotations

import logging
from types import TracebackType
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError  # noqa: F401
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from reddit_scraper.auth import (
    cookie_header_to_playwright_cookies,
    get_reddit_cookie,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PAGE_TIMEOUT_MS = 30_000
CONTENT_SELECTOR_TIMEOUT_MS = 10_000
CONTENT_SELECTOR = "div.commentarea, p.title, #search"
LOGIN_REQUIRED_PATH = "/login/"


class LoginRequiredError(RuntimeError):
    """Erro levantado quando o Reddit exige login para ver o conteudo.

    Pode acontecer com qualquer post desde que o Reddit passou a
    exigir conta logada (mais comum em posts NSFW ou de subreddits
    restritos). Configurar um cookie de sessao via
    `reddit_scraper.auth` evita esse erro para posts que a propria
    conta usada tenha permissao de ver.
    """


class BrowserSession:
    """Navegador Chromium controlado via Playwright, com cookie injetado.

    Mantem um unico navegador/contexto abertos durante toda a coleta
    (varios posts), em vez de abrir um novo processo a cada
    requisicao -- isso e caro o suficiente para valer a pena reusar.
    Use como gerenciador de contexto::

        with BrowserSession() as session:
            html = session.fetch_html(url)
    """

    def __init__(self) -> None:
        """Abre o navegador e injeta o cookie de sessao configurado."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(user_agent=USER_AGENT)

        cookie_header = get_reddit_cookie()
        if cookie_header:
            self._context.add_cookies(
                cookie_header_to_playwright_cookies(cookie_header)
            )
        else:
            logger.warning(
                "Nenhum cookie configurado (REDDIT_COOKIE) -- o Reddit "
                "provavelmente vai bloquear a coleta de posts que "
                "exigem login."
            )

    def __enter__(self) -> BrowserSession:
        """Permite usar a sessao como gerenciador de contexto."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Fecha o navegador ao sair do bloco ``with``."""
        self.close()

    def close(self) -> None:
        """Fecha o contexto, o navegador e o processo do Playwright."""
        self._context.close()
        self._browser.close()
        self._playwright.stop()

    def fetch_html(self, url: str) -> str:
        """Navega ate a URL e devolve o HTML renderizado da pagina.

        ``domcontentloaded`` dispara assim que o HTML bruto chega, o
        que pode ser antes da pagina estar realmente pronta (ex.: uma
        verificacao extra do Reddit entre a navegacao e o conteudo
        final). Por isso espera tambem o titulo ou a area de
        comentarios aparecerem no DOM antes de ler o conteudo -- se
        isso nao acontecer a tempo, so registra um aviso e devolve o
        que tiver (quem chama decide se trata como falha).

        Parameters
        ----------
        url : str
            URL a ser carregada.

        Returns
        -------
        str
            Conteudo HTML da pagina apos o carregamento.

        Raises
        ------
        LoginRequiredError
            Se o Reddit redirecionar para a tela de login (post NSFW
            ou de subreddit restrito).
        """
        page = self._context.new_page()
        try:
            page.goto(
                url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
            )
            if LOGIN_REQUIRED_PATH in urlparse(page.url).path:
                msg = (
                    f"Reddit exige login para ver este post (provavelmente "
                    f"NSFW ou restrito): {url}"
                )
                raise LoginRequiredError(msg)
            try:
                page.wait_for_selector(
                    CONTENT_SELECTOR, timeout=CONTENT_SELECTOR_TIMEOUT_MS
                )
            except PlaywrightTimeoutError:
                logger.warning(
                    "Pagina carregou mas titulo/comentarios nao "
                    "apareceram a tempo -- pode ter vindo incompleta "
                    "ou bloqueada: %s",
                    url,
                )
            return page.content()
        finally:
            page.close()

    def resolve_url(self, url: str) -> str:
        """Navega ate a URL e devolve a URL final, apos redirecionamentos.

        Usado para resolver links de compartilhamento (``/s/...``),
        que nao trazem o id do post e precisam de uma navegacao real
        para descobrir a URL canonica.

        Parameters
        ----------
        url : str
            URL a ser navegada (pode redirecionar).

        Returns
        -------
        str
            URL final apos o(s) redirecionamento(s).
        """
        page = self._context.new_page()
        try:
            page.goto(
                url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
            )
            return page.url
        finally:
            page.close()

    def fetch_json(self, url: str, params: dict[str, str]) -> dict:
        """Busca um endpoint JSON usando o mesmo contexto do navegador.

        Usa a API de requisicoes do Playwright (``context.request``),
        que reusa a mesma conexao/cookies do navegador em vez de uma
        biblioteca HTTP separada -- mantendo a mesma "impressao
        digital" de rede que evita o bloqueio 403.

        Parameters
        ----------
        url : str
            URL do endpoint JSON.
        params : dict[str, str]
            Parametros de query string.

        Returns
        -------
        dict
            Corpo da resposta, decodificado como JSON.

        Raises
        ------
        LoginRequiredError
            Se o Reddit redirecionar para a tela de login.
        RuntimeError
            Se a resposta nao tiver um status de sucesso.
        """
        response = self._context.request.get(
            url, params=params, timeout=PAGE_TIMEOUT_MS
        )
        if LOGIN_REQUIRED_PATH in urlparse(response.url).path:
            msg = f"Reddit exige login para ver este conteudo: {url}"
            raise LoginRequiredError(msg)
        if not response.ok:
            msg = (
                f"Requisicao falhou ({response.status}) para {url}: "
                f"{response.status_text}"
            )
            raise RuntimeError(msg)
        return response.json()
