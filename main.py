"""Ponto de entrada simples.

Cole a(s) URL(s) do post do Reddit em `POST_URLS` abaixo e rode
``poetry run python main.py``.
"""

from pathlib import Path

from julgame_scraper.html_scraper import collect_multiple_posts, save_dataset

POST_URLS = [
    "https://www.reddit.com/r/ShitpostBR/s/Sq96xBtb29",
]

OUTPUT_PATH = Path("data/comentarios.csv")


def main() -> None:
    """Coleta os comentarios de `POST_URLS` e salva em `OUTPUT_PATH`."""
    df = collect_multiple_posts(POST_URLS)
    save_dataset(df, OUTPUT_PATH)

    flagged = int(df["flagged_by_keyword"].sum()) if not df.empty else 0
    print(
        f"{flagged} de {len(df)} comentarios marcados pelo filtro de "
        "palavras-chave"
    )


if __name__ == "__main__":
    main()
