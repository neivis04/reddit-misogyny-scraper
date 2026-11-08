"""Cookie de sessao do Reddit, usado para contornar o login obrigatorio.

Desde 2026 o Reddit passou a exigir uma conta logada para ver posts
mesmo via old.reddit.com ou pelo endpoint publico ``.json`` (ver
``LOGIN_REQUIRED_PATH`` em `reddit_scraper.html_scraper`). Para
continuar raspando sem registrar um app OAuth/PRAW, o scraper reusa os
cookies de uma sessao ja autenticada no navegador:

1. Faca login manualmente em reddit.com com uma conta qualquer.
2. Abra o DevTools (F12) > aba Network, recarregue a pagina e clique em
   qualquer requisicao para reddit.com.
3. Em "Request Headers", copie o valor completo do cabecalho ``Cookie``.
4. Cole esse valor na variavel de ambiente `REDDIT_COOKIE`, ou numa
   linha ``REDDIT_COOKIE=...`` no arquivo ``.env`` na raiz do projeto
   (esse arquivo ja e ignorado pelo git).

O cookie expira periodicamente; quando voltar a tomar erro de login,
repita os passos acima para pegar um cookie novo.
"""

from __future__ import annotations

import os
from pathlib import Path

COOKIE_ENV_VAR = "REDDIT_COOKIE"
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _read_env_file(key: str) -> str | None:
    """Le uma variavel de um arquivo ``.env`` simples (``KEY=VALUE``).

    Parameters
    ----------
    key : str
        Nome da variavel procurada.

    Returns
    -------
    str or None
        Valor associado a chave, ou None se o arquivo ou a chave nao
        existirem.
    """
    if not _ENV_FILE.exists():
        return None
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def get_reddit_cookie() -> str | None:
    """Devolve o cookie de sessao do Reddit configurado, se houver.

    Busca primeiro na variavel de ambiente `REDDIT_COOKIE`; na
    ausencia dela, tenta ler uma linha equivalente do arquivo ``.env``
    na raiz do projeto.

    Returns
    -------
    str or None
        Valor pronto para o cabecalho ``Cookie``, ou None se nao
        configurado (nesse caso as requisicoes seguem anonimas).
    """
    return os.environ.get(COOKIE_ENV_VAR) or _read_env_file(COOKIE_ENV_VAR)


def cookie_header_to_playwright_cookies(
    cookie_header: str,
) -> list[dict[str, str]]:
    """Converte um cabecalho ``Cookie`` na lista que o Playwright espera.

    O Playwright nao aceita a string crua do cabecalho ``Cookie``
    (``nome1=valor1; nome2=valor2``) -- precisa de uma lista de
    dicionarios, um por cookie, com dominio e caminho explicitos.

    Parameters
    ----------
    cookie_header : str
        Valor do cabecalho ``Cookie``, no formato copiado do DevTools.

    Returns
    -------
    list[dict[str, str]]
        Cookies prontos para ``BrowserContext.add_cookies``.
    """
    cookies = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".reddit.com",
                "path": "/",
            }
        )
    return cookies


def build_headers(user_agent: str) -> dict[str, str]:
    """Monta os cabecalhos de requisicao, incluindo cookie se houver.

    Parameters
    ----------
    user_agent : str
        Valor do cabecalho ``User-Agent`` a usar.

    Returns
    -------
    dict[str, str]
        Cabecalhos prontos para `requests.get`.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    cookie = get_reddit_cookie()
    if cookie:
        headers["Cookie"] = cookie
    return headers
