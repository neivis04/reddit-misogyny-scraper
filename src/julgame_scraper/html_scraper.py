"""Scraping de comentarios do Reddit via HTML de old.reddit.com.

old.reddit.com ainda serve paginas renderizadas no servidor (ao
contrario do site novo, que e uma SPA em React e so entrega o conteudo
depois de rodar JS no navegador). Isso permite fazer scraping direto
com requests + BeautifulSoup, sem precisar de credenciais da API
oficial do Reddit.

Limitacao: assim como a pagina normal do Reddit, uma unica requisicao
nao traz comentarios colapsados atras de "load more comments" -- esses
ficam de fora. Para uma analise simples via CSV isso costuma ser
suficiente.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from julgame_scraper.keywords import OFFENSIVE_KEYWORDS, contains_keyword

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 15
POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/")


def resolve_to_old_reddit(url: str) -> str:
    """Resolve redirecionamentos para a URL equivalente em old.reddit.com.

    Parameters
    ----------
    url : str
        URL de um post do Reddit, incluindo links de compartilhamento
        (``/s/...``).

    Returns
    -------
    str
        URL canonica do post no dominio old.reddit.com.
    """
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    canonical = response.url.split("?")[0].rstrip("/")
    parsed = urlparse(canonical)
    return parsed._replace(netloc="old.reddit.com").geturl()


def fetch_html(url: str) -> str:
    """Baixa o HTML de uma URL, com User-Agent de navegador.

    Parameters
    ----------
    url : str
        URL a ser baixada.

    Returns
    -------
    str
        Conteudo HTML da pagina.
    """
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def extract_submission_id(url: str) -> str:
    """Extrai o id do post a partir da URL.

    Parameters
    ----------
    url : str
        URL de um post, no formato ``.../comments/<id>/...``.

    Returns
    -------
    str
        Id do post.

    Raises
    ------
    ValueError
        Se a URL nao contiver um id de post reconhecivel.
    """
    match = POST_ID_RE.search(url)
    if not match:
        msg = f"Nao foi possivel extrair o id do post da URL: {url}"
        raise ValueError(msg)
    return match.group(1)


def extract_submission_title(soup: BeautifulSoup) -> str:
    """Extrai o titulo do post a partir do HTML ja parseado.

    Parameters
    ----------
    soup : bs4.BeautifulSoup
        HTML da pagina do post, ja parseado.

    Returns
    -------
    str
        Titulo do post, ou string vazia se nao encontrado.
    """
    title_link = soup.select_one("div.thing.link p.title a.title")
    if title_link:
        return title_link.get_text(strip=True)
    if soup.title:
        return soup.title.get_text(strip=True)
    return ""


def parse_comments(
    html: str,
    submission_id: str,
    submission_title: str,
    keywords: list[str] | None = None,
) -> list[dict]:
    """Extrai comentarios (incluindo respostas aninhadas) do HTML.

    Parameters
    ----------
    html : str
        HTML da pagina do post em old.reddit.com.
    submission_id : str
        Id do post ao qual os comentarios pertencem.
    submission_title : str
        Titulo do post.
    keywords : list[str] or None
        Termos usados no filtro heuristico. Usa
        `OFFENSIVE_KEYWORDS` quando omitido.

    Returns
    -------
    list[dict]
        Uma entrada por comentario, pronta para virar linha de
        DataFrame.
    """
    keywords = keywords if keywords is not None else OFFENSIVE_KEYWORDS
    soup = BeautifulSoup(html, "lxml")
    rows = []

    for comment_div in soup.select("div.thing.comment"):
        raw_id = comment_div.get("id", "").removeprefix("thing_")
        fullname = comment_div.get("data-fullname") or raw_id
        comment_id = fullname.removeprefix("t1_") if fullname else None
        author = comment_div.get("data-author") or "[deletado]"

        entry = comment_div.find("div", class_="entry")
        body = ""
        score = None
        if entry is not None:
            md = entry.find("div", class_="md")
            if md is not None:
                body = md.get_text(separator="\n", strip=True)

            score_span = entry.find("span", class_="score")
            if score_span is not None:
                score_text = score_span.get("title") or score_span.get_text(
                    strip=True
                )
                score_text = score_text.split()[0] if score_text else ""
                if score_text.lstrip("-").isdigit():
                    score = int(score_text)

        rows.append(
            {
                "submission_id": submission_id,
                "submission_title": submission_title,
                "comment_id": comment_id,
                "author": author,
                "body": body,
                "score": score,
                "flagged_by_keyword": contains_keyword(body, keywords),
            }
        )

    return rows


def collect_post_comments(post_url: str) -> pd.DataFrame:
    """Coleta todos os comentarios de um unico post do Reddit.

    Parameters
    ----------
    post_url : str
        URL do post (aceita links de compartilhamento ``/s/...``).

    Returns
    -------
    pandas.DataFrame
        Um comentario por linha.
    """
    old_reddit_url = resolve_to_old_reddit(post_url)
    html = fetch_html(old_reddit_url)
    soup = BeautifulSoup(html, "lxml")

    submission_id = extract_submission_id(old_reddit_url)
    submission_title = extract_submission_title(soup)

    rows = parse_comments(html, submission_id, submission_title)
    logger.info(
        "Post '%s': %d comentarios coletados", submission_title, len(rows)
    )
    return pd.DataFrame(rows)


def collect_multiple_posts(urls: list[str]) -> pd.DataFrame:
    """Coleta comentarios de varios posts, com pausa entre requisicoes.

    Parameters
    ----------
    urls : list[str]
        URLs dos posts a coletar.

    Returns
    -------
    pandas.DataFrame
        Comentarios de todos os posts concatenados em um unico
        DataFrame.
    """
    frames = []
    for index, url in enumerate(urls):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        frames.append(collect_post_comments(url))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def save_dataset(df: pd.DataFrame, output_path: Path) -> None:
    """Salva o dataset em CSV, criando os diretorios necessarios.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataset a ser salvo.
    output_path : pathlib.Path
        Caminho do arquivo CSV de saida.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("Dataset salvo em %s (%d linhas)", output_path, len(df))
