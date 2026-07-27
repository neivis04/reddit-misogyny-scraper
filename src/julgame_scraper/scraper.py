"""Coleta comentarios de um subreddit via API oficial do Reddit (PRAW).

Requer credenciais de app registradas em reddit.com/prefs/apps,
configuradas via variaveis de ambiente (ver `julgame_scraper.config`).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import praw
from tqdm import tqdm

from julgame_scraper.config import get_settings
from julgame_scraper.keywords import OFFENSIVE_KEYWORDS, contains_keyword

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def build_reddit_client() -> praw.Reddit:
    """Cria um cliente PRAW autenticado a partir das configuracoes do .env.

    Returns
    -------
    praw.Reddit
        Cliente autenticado pronto para uso.
    """
    settings = get_settings()
    return praw.Reddit(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        user_agent=settings.user_agent,
    )


def collect_comments(
    reddit: praw.Reddit,
    subreddit_name: str,
    limit: int = 200,
    keywords: list[str] | None = None,
) -> pd.DataFrame:
    """Coleta comentarios dos posts mais recentes de um subreddit.

    Parameters
    ----------
    reddit : praw.Reddit
        Cliente PRAW autenticado.
    subreddit_name : str
        Nome do subreddit alvo da coleta.
    limit : int
        Numero maximo de posts a percorrer.
    keywords : list[str] or None
        Termos usados no filtro heuristico. Usa
        `OFFENSIVE_KEYWORDS` quando omitido.

    Returns
    -------
    pandas.DataFrame
        Um comentario por linha, com a coluna `flagged_by_keyword`
        indicando candidatos a revisao manual.
    """
    keywords = keywords if keywords is not None else OFFENSIVE_KEYWORDS
    subreddit = reddit.subreddit(subreddit_name)
    rows = []

    submissions = tqdm(subreddit.new(limit=limit), total=limit, desc="Posts")
    for submission in submissions:
        # "more comments" stubs sao ignorados (replace_more(limit=0))
        submission.comments.replace_more(limit=0)
        for comment in submission.comments.list():
            body = comment.body or ""
            author = str(comment.author) if comment.author else "[deletado]"
            rows.append(
                {
                    "submission_id": submission.id,
                    "submission_title": submission.title,
                    "comment_id": comment.id,
                    "author": author,
                    "body": body,
                    "score": comment.score,
                    "created_utc": comment.created_utc,
                    "flagged_by_keyword": contains_keyword(body, keywords),
                }
            )

    return pd.DataFrame(rows)


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
    """Executa a coleta completa usando as configuracoes do .env."""
    settings = get_settings()
    reddit = build_reddit_client()
    df = collect_comments(
        reddit, settings.subreddit_name, limit=settings.post_limit
    )
    save_dataset(df, Path(settings.output_path))

    flagged = int(df["flagged_by_keyword"].sum()) if not df.empty else 0
    logger.info(
        "%d de %d comentarios marcados pelo filtro de palavras-chave "
        "para revisao manual",
        flagged,
        len(df),
    )


if __name__ == "__main__":
    main()
