"""Coleta comentarios de posts do Reddit via o endpoint publico ``.json``.

Nao usa PRAW nem credenciais OAuth: basta pegar a URL de qualquer
post/comentario publico do Reddit e acrescentar ``.json`` no final para
receber o post e a arvore de comentarios em formato estruturado. Util
enquanto o acesso a API oficial nao esta disponivel. Aceita tambem
links de compartilhamento (``/s/...``), resolvendo o redirecionamento
ate a URL canonica do post antes de buscar o JSON.

Aviso: em alguns ambientes (ex.: IPs de datacenter/cloud) o Reddit
bloqueia requisicoes a ``.json`` com 403, mesmo sem OAuth envolvido.
Nesse caso, use `reddit_scraper.html_scraper`.

Limitacao: assim como a pagina normal do Reddit, uma unica chamada nao
traz comentarios colapsados por "load more comments" (stubs
``kind == "more"``) -- esses sao ignorados aqui. Para uma analise
simples via CSV isso costuma ser suficiente.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from reddit_scraper.keywords import (
    OFFENSIVE_KEYWORDS_BY_CATEGORY,
    format_matches,
    match_categories,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

USER_AGENT = (
    "reddit-scraper/0.1 (TCC pesquisa academica sobre discurso ofensivo)"
)
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 10


def resolve_post_url(url: str) -> str:
    """Segue redirecionamentos e devolve a URL canonica do post.

    Parameters
    ----------
    url : str
        URL de um post do Reddit, incluindo links de compartilhamento
        (``/s/...``).

    Returns
    -------
    str
        URL canonica do post, sem query string.
    """
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.url.split("?")[0].rstrip("/")


def fetch_post_json(post_url: str) -> list[dict]:
    """Busca o JSON publico de um post (post + arvore de comentarios).

    Parameters
    ----------
    post_url : str
        URL canonica do post, sem o sufixo ``.json``.

    Returns
    -------
    list[dict]
        Payload decodificado, com dois elementos: post e comentarios.
    """
    json_url = f"{post_url}.json"
    response = requests.get(
        json_url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def flatten_comments(
    children: list[dict],
    submission_id: str,
    submission_title: str,
    keywords_by_category: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Converte a arvore de comentarios do JSON em uma lista plana.

    Parameters
    ----------
    children : list[dict]
        Lista de nos ``t1``/``more`` conforme retornado pela API.
    submission_id : str
        Id do post ao qual os comentarios pertencem.
    submission_title : str
        Titulo do post.
    keywords_by_category : dict[str, list[str]] or None
        Termos agrupados por categoria, usados no filtro heuristico.
        Usa `OFFENSIVE_KEYWORDS_BY_CATEGORY` quando omitido.

    Returns
    -------
    list[dict]
        Uma entrada por comentario, incluindo respostas aninhadas.
    """
    keywords_by_category = (
        keywords_by_category
        if keywords_by_category is not None
        else OFFENSIVE_KEYWORDS_BY_CATEGORY
    )
    rows = []
    for child in children:
        if child.get("kind") != "t1":
            continue  # skip "more" stubs (collapsed comments)
        data = child["data"]
        body = data.get("body") or ""
        matches = match_categories(body, keywords_by_category)
        flagged_categories, matched_keywords = format_matches(matches)
        rows.append(
            {
                "submission_id": submission_id,
                "submission_title": submission_title,
                "comment_id": data.get("id"),
                "author": data.get("author") or "[deletado]",
                "body": body,
                "score": data.get("score"),
                "created_utc": data.get("created_utc"),
                "flagged_by_keyword": bool(matches),
                "flagged_categories": flagged_categories,
                "matched_keywords": matched_keywords,
            }
        )
        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            rows.extend(
                flatten_comments(
                    reply_children,
                    submission_id,
                    submission_title,
                    keywords_by_category,
                )
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
    canonical_url = resolve_post_url(post_url)
    payload = fetch_post_json(canonical_url)

    post_data = payload[0]["data"]["children"][0]["data"]
    submission_id = post_data["id"]
    submission_title = post_data.get("title", "")

    comment_children = payload[1]["data"]["children"]
    rows = flatten_comments(comment_children, submission_id, submission_title)
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


def main() -> None:
    """Ponto de entrada de linha de comando do scraper via ``.json``."""
    parser = argparse.ArgumentParser(
        description="Coleta comentarios de posts do Reddit via endpoint "
        "publico .json (sem OAuth)"
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="URL(s) de post do Reddit (aceita links de compartilhamento "
        "/s/...)",
    )
    parser.add_argument(
        "--output",
        default="data/comentarios.csv",
        help="Caminho do CSV de saida",
    )
    args = parser.parse_args()

    df = collect_multiple_posts(args.urls)
    save_dataset(df, Path(args.output))

    flagged = int(df["flagged_by_keyword"].sum()) if not df.empty else 0
    logger.info(
        "%d de %d comentarios marcados pelo filtro de palavras-chave "
        "para revisao manual",
        flagged,
        len(df),
    )


if __name__ == "__main__":
    main()
