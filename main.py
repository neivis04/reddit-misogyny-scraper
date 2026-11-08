"""Ponto de entrada simples.

Cole a(s) URL(s) do post do Reddit em `POST_URLS` abaixo e rode
``poetry run python main.py``. Cada post e salvo em um CSV separado,
nomeado pelo titulo, dentro de `OUTPUT_DIR`.
"""

from pathlib import Path

from reddit_scraper.html_scraper import collect_and_save_posts

POST_URLS = [
    "https://www.reddit.com/r/ShitpostBR/comments/1qml3zc/cabal%C3%ADstico/",
    "https://www.reddit.com/r/ShitpostBR/comments/1q8a7rd/no_tinder_no_cidade_alerta/",
    "https://www.reddit.com/r/ShitpostBR/s/Sq96xBtb29",
    "https://www.reddit.com/r/ShitpostBR/comments/1urc8ah/aqui_%C3%A9_o_brasil/",
    "https://www.reddit.com/r/ShitpostBR/comments/1uvsmvc/olha_como_t%C3%A1_a_mente_dessas_mina/?solution=1a35c234c129aa001a35c234c129aa00&js_challenge=1&token=7afd7253fec22262ff1c52b1703fe9ec50b6427dc4b61f66095618acd9b0b06e&jsc_orig_r=",
    "https://www.reddit.com/r/ShitpostBR/comments/1uvkwsb/qual_e_a_frase/",
    "https://www.reddit.com/r/ShitpostBR/comments/1v95yd3/nojinho/",
    "https://www.reddit.com/r/ShitpostBR/comments/1vk8gvw/passou_dos_limites/"
]

OUTPUT_DIR = Path("data")


def main() -> None:
    """Coleta os comentarios de `POST_URLS`, um CSV por post."""
    saved_paths = collect_and_save_posts(POST_URLS, OUTPUT_DIR)
    for path in saved_paths:
        print(f"Salvo: {path}")


if __name__ == "__main__":
    main()
