"""Ponto de entrada simples.

Cole a(s) URL(s) do post do Reddit em `POST_URLS` abaixo e rode
``poetry run python main.py``. Cada post e salvo em um CSV separado,
nomeado pelo titulo, dentro de `OUTPUT_DIR`.
"""

from pathlib import Path

from reddit_scraper.html_scraper import collect_and_save_posts

POST_URLS = [
    "https://www.reddit.com/r/ShitpostBR/comments/1q8a7rd/no_tinder_no_cidade_alerta/",
]

OUTPUT_DIR = Path("data")


def main() -> None:
    """Coleta os comentarios de `POST_URLS`, um CSV por post."""
    saved_paths = collect_and_save_posts(POST_URLS, OUTPUT_DIR)
    for path in saved_paths:
        print(f"Salvo: {path}")


if __name__ == "__main__":
    main()
