"""Configuracoes carregadas do arquivo .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class MissingConfigError(RuntimeError):
    """Erro levantado quando falta uma variavel de ambiente obrigatoria."""


def _require(name: str) -> str:
    """Le uma variavel de ambiente obrigatoria.

    Parameters
    ----------
    name : str
        Nome da variavel de ambiente a ser lida.

    Returns
    -------
    str
        Valor da variavel de ambiente.

    Raises
    ------
    MissingConfigError
        Se a variavel nao estiver definida ou estiver vazia.
    """
    value = os.getenv(name)
    if not value:
        raise MissingConfigError(
            f"Variavel de ambiente '{name}' nao definida. "
            "Configure o arquivo .env (veja .env.example)."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """Configuracoes necessarias para rodar o scraper baseado em PRAW.

    Parameters
    ----------
    client_id : str
        Client ID do app registrado na API do Reddit.
    client_secret : str
        Client secret do app registrado na API do Reddit.
    user_agent : str
        User-Agent enviado nas requisicoes a API do Reddit.
    subreddit_name : str
        Nome do subreddit alvo da coleta.
    post_limit : int
        Numero maximo de posts a percorrer por execucao.
    output_path : str
        Caminho do arquivo CSV de saida.
    """

    client_id: str
    client_secret: str
    user_agent: str
    subreddit_name: str
    post_limit: int
    output_path: str


def get_settings() -> Settings:
    """Monta as configuracoes a partir das variaveis de ambiente.

    Returns
    -------
    Settings
        Configuracoes prontas para uso pelo scraper baseado em PRAW.
    """
    default_user_agent = "julgame-scraper/0.1 (TCC pesquisa academica)"
    return Settings(
        client_id=_require("REDDIT_CLIENT_ID"),
        client_secret=_require("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", default_user_agent),
        subreddit_name=_require("SUBREDDIT_NAME"),
        post_limit=int(os.getenv("POST_LIMIT", "200")),
        output_path=os.getenv("OUTPUT_PATH", "data/comentarios.csv"),
    )
