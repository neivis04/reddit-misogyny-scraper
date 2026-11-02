"""Scraping de comentarios do Reddit via HTML de old.reddit.com.

old.reddit.com ainda serve paginas renderizadas no servidor (ao
contrario do site novo, que e uma SPA em React e so entrega o conteudo
depois de rodar JS no navegador). Isso permite fazer scraping direto
com requests + BeautifulSoup, sem precisar de credenciais da API
oficial do Reddit (PRAW/OAuth).

Desde 2026 o Reddit exige login mesmo em old.reddit.com para alguns
posts (ver `LoginRequiredError`). Para contornar isso sem OAuth, as
requisicoes reusam o cookie de uma sessao ja autenticada no navegador,
configurado conforme `reddit_scraper.auth`; sem esse cookie, o scraper
continua funcionando normalmente para posts que nao exigem login.

A pagina inicial e pedida com ``?limit=500`` (o maximo aceito pelo
Reddit) para reduzir quantos comentarios ficam escondidos atras de
"load more comments" desde a primeira resposta. Os que ainda ficarem
sao buscados em rodadas seguintes, via o endpoint
``api/morechildren.json`` (o mesmo usado pelo old.reddit.com
internamente); se uma rodada trouxer novos stubs "load more" aninhados
dentro dela, eles sao buscados na rodada seguinte, ate
`MORE_CHILDREN_MAX_ROUNDS` rodadas ou nao haver mais stubs novos.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from reddit_scraper.auth import build_headers
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 15
POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/")
SLUG_RE = re.compile(r"[^a-z0-9]+")
MORE_CHILDREN_ONCLICK_RE = re.compile(
    r"morechildren\(this,\s*'[^']*',\s*'[^']*',\s*'([^']*)'"
)
MORE_CHILDREN_URL = "https://old.reddit.com/api/morechildren.json"
MORE_CHILDREN_CHUNK_SIZE = 100
MORE_CHILDREN_MAX_ROUNDS = 6
LOGIN_REQUIRED_PATH = "/login/"
COMMENT_PAGE_LIMIT = 500


class LoginRequiredError(RuntimeError):
    """Erro levantado quando o Reddit exige login para ver o post.

    Pode acontecer com qualquer post desde que o Reddit passou a
    exigir conta logada em old.reddit.com (mais comum em posts NSFW ou
    de subreddits restritos). Configurar um cookie de sessao via
    `reddit_scraper.auth` evita esse erro para posts que a propria
    conta usada tenha permissao de ver.
    """


def resolve_to_old_reddit(url: str) -> str:
    """Resolve redirecionamentos para a URL equivalente em old.reddit.com.

    URLs que ja contem ``/comments/<id>/`` sao resolvidas localmente,
    so trocando o dominio, sem nenhuma requisicao -- evita bater em
    ``www.reddit.com``, cujo bloqueio anti-bot costuma ser mais
    agressivo que o de ``old.reddit.com`` (ver 403 "Blocked"). Apenas
    links de compartilhamento (``/s/...``), que nao trazem o id do
    post na URL, precisam de uma requisicao para seguir o
    redirecionamento -- essa requisicao e feita direto em
    old.reddit.com, pelo mesmo motivo.

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
    old_reddit_url = urlparse(url)._replace(netloc="old.reddit.com").geturl()

    if POST_ID_RE.search(url):
        canonical = old_reddit_url.split("?")[0].rstrip("/")
        return urlparse(canonical)._replace(netloc="old.reddit.com").geturl()

    response = requests.get(
        old_reddit_url,
        headers=build_headers(USER_AGENT),
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

    Raises
    ------
    LoginRequiredError
        Se o Reddit redirecionar para a tela de login (post NSFW ou
        de subreddit restrito).
    """
    response = requests.get(
        url,
        headers=build_headers(USER_AGENT),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    if LOGIN_REQUIRED_PATH in urlparse(response.url).path:
        msg = (
            f"Reddit exige login para ver este post (provavelmente "
            f"NSFW ou restrito): {url}"
        )
        raise LoginRequiredError(msg)
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


def extract_comment_created_utc(comment_div) -> float | None:
    """Extrai o timestamp UTC de publicacao a partir da tag ``<time>``.

    Parameters
    ----------
    comment_div : bs4.Tag
        Elemento ``div.thing.comment`` ja localizado na pagina.

    Returns
    -------
    float or None
        Timestamp Unix (segundos desde a epoch), ou None se a pagina
        nao tiver a tag ``<time datetime="...">`` esperada.
    """
    time_tag = comment_div.find("time")
    if time_tag is None:
        return None
    raw_datetime = time_tag.get("datetime")
    if not raw_datetime:
        return None
    try:
        return datetime.fromisoformat(raw_datetime).timestamp()
    except ValueError:
        return None


def parse_comments(
    html: str,
    submission_id: str,
    submission_title: str,
    keywords_by_category: dict[str, list[str]] | None = None,
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
    keywords_by_category : dict[str, list[str]] or None
        Termos agrupados por categoria, usados no filtro heuristico.
        Usa `OFFENSIVE_KEYWORDS_BY_CATEGORY` quando omitido.

    Returns
    -------
    list[dict]
        Uma entrada por comentario, pronta para virar linha de
        DataFrame.
    """
    keywords_by_category = (
        keywords_by_category
        if keywords_by_category is not None
        else OFFENSIVE_KEYWORDS_BY_CATEGORY
    )
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

        matches = match_categories(body, keywords_by_category)
        flagged_categories, matched_keywords = format_matches(matches)

        rows.append(
            {
                "submission_id": submission_id,
                "submission_title": submission_title,
                "comment_id": comment_id,
                "author": author,
                "body": body,
                "score": score,
                "created_utc": extract_comment_created_utc(comment_div),
                "flagged_by_keyword": bool(matches),
                "flagged_categories": flagged_categories,
                "matched_keywords": matched_keywords,
            }
        )

    return rows


def extract_more_children_ids(soup: BeautifulSoup) -> list[str]:
    """Extrai os ids dos comentarios atras de "load more comments".

    Parameters
    ----------
    soup : bs4.BeautifulSoup
        HTML da pagina do post, ja parseado.

    Returns
    -------
    list[str]
        Ids unicos (``t1_...``) dos comentarios colapsados, na ordem
        em que aparecem na pagina.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for link in soup.select("div.morechildren a.button"):
        match = MORE_CHILDREN_ONCLICK_RE.search(link.get("onclick", ""))
        if not match:
            continue
        _, _, raw_ids = match.group(1).partition(":")
        for child_id in raw_ids.split(","):
            child_id = child_id.strip()
            if child_id and child_id not in seen:
                seen.add(child_id)
                ids.append(child_id)
    return ids


def fetch_more_children(link_id: str, children_ids: list[str]) -> list[dict]:
    """Busca comentarios colapsados via o endpoint api/morechildren.json.

    Parameters
    ----------
    link_id : str
        Fullname do post (``t3_<id>``).
    children_ids : list[str]
        Ids dos comentarios colapsados a buscar (``t1_...``), no
        maximo `MORE_CHILDREN_CHUNK_SIZE` por chamada.

    Returns
    -------
    list[dict]
        Nos ``t1``/``more`` retornados pela API, no mesmo formato do
        endpoint publico ``.json``.
    """
    response = requests.get(
        MORE_CHILDREN_URL,
        params={
            "api_type": "json",
            "link_id": link_id,
            "children": ",".join(children_ids),
            "sort": "confidence",
            "limit_children": "false",
        },
        headers=build_headers(USER_AGENT),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["json"]["data"]["things"]


def _rows_from_json_things(
    things: list[dict],
    submission_id: str,
    submission_title: str,
    keywords_by_category: dict[str, list[str]],
) -> list[dict]:
    """Converte nos JSON (``kind`` ``t1``) da API morechildren em linhas.

    Espelha o formato de linha usado por `parse_comments`, para que
    comentarios colapsados fiquem no mesmo esquema dos demais.

    Parameters
    ----------
    things : list[dict]
        Nos ``t1``/``more`` retornados por `fetch_more_children`.
    submission_id : str
        Id do post ao qual os comentarios pertencem.
    submission_title : str
        Titulo do post.
    keywords_by_category : dict[str, list[str]]
        Termos agrupados por categoria, usados no filtro heuristico.

    Returns
    -------
    list[dict]
        Uma entrada por comentario, incluindo respostas aninhadas.
    """
    rows = []
    for thing in things:
        if thing.get("kind") != "t1":
            continue  # further "more" stubs are not re-fetched
        data = thing["data"]
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
            reply_things = replies.get("data", {}).get("children", [])
            rows.extend(
                _rows_from_json_things(
                    reply_things,
                    submission_id,
                    submission_title,
                    keywords_by_category,
                )
            )
    return rows


def _more_stub_ids_from_things(things: list[dict]) -> list[str]:
    """Varre nos ja buscados por novos stubs "more" aninhados.

    Esses stubs aparecem quando um comentario que acabou de ser
    buscado via `fetch_more_children` tem, ele mesmo, respostas
    colapsadas demais para vir na mesma chamada -- sem essa varredura
    elas ficariam de fora, mesmo em `collect_more_children_rows`.

    Parameters
    ----------
    things : list[dict]
        Nos ``t1``/``more`` retornados por `fetch_more_children`.

    Returns
    -------
    list[str]
        Ids (sem prefixo garantido) dos comentarios ainda colapsados.
    """
    ids: list[str] = []
    for thing in things:
        data = thing.get("data", {})
        if thing.get("kind") == "more":
            ids.extend(data.get("children", []))
            continue
        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_things = replies.get("data", {}).get("children", [])
            ids.extend(_more_stub_ids_from_things(reply_things))
    return ids


def collect_more_children_rows(
    submission_id: str,
    submission_title: str,
    children_ids: list[str],
    keywords_by_category: dict[str, list[str]] | None = None,
    max_rounds: int = MORE_CHILDREN_MAX_ROUNDS,
) -> list[dict]:
    """Busca e converte os comentarios atras de "load more comments".

    Busca em rodadas: cada rodada pode revelar novos stubs "more"
    aninhados dentro dos comentarios que acabaram de ser buscados
    (ver `_more_stub_ids_from_things`), que entao sao buscados na
    rodada seguinte, ate `max_rounds` rodadas ou nao haver mais stubs
    novos. Se uma busca falhar (ex.: endpoint bloqueado nesta rede),
    registra um aviso e devolve o que ja tiver sido coletado ate ali,
    em vez de propagar o erro.

    Parameters
    ----------
    submission_id : str
        Id do post ao qual os comentarios pertencem.
    submission_title : str
        Titulo do post.
    children_ids : list[str]
        Ids dos comentarios colapsados a buscar (``t1_...``).
    keywords_by_category : dict[str, list[str]] or None
        Termos agrupados por categoria, usados no filtro heuristico.
        Usa `OFFENSIVE_KEYWORDS_BY_CATEGORY` quando omitido.
    max_rounds : int
        Numero maximo de rodadas de busca por stubs aninhados.

    Returns
    -------
    list[dict]
        Linhas adicionais, no mesmo formato de `parse_comments`.
    """
    keywords_by_category = (
        keywords_by_category
        if keywords_by_category is not None
        else OFFENSIVE_KEYWORDS_BY_CATEGORY
    )
    link_id = f"t3_{submission_id}"
    rows: list[dict] = []
    pending = list(dict.fromkeys(children_ids))
    seen: set[str] = set(pending)
    made_any_request = False

    for _round in range(max_rounds):
        if not pending:
            break
        next_pending: list[str] = []
        failed = False

        for index in range(0, len(pending), MORE_CHILDREN_CHUNK_SIZE):
            if made_any_request:
                time.sleep(REQUEST_DELAY_SECONDS)
            made_any_request = True
            chunk = pending[index : index + MORE_CHILDREN_CHUNK_SIZE]
            try:
                things = fetch_more_children(link_id, chunk)
            except requests.RequestException as exc:
                logger.warning(
                    "Falha ao buscar comentarios colapsados (%s); "
                    "seguindo so com os comentarios ja coletados.",
                    exc,
                )
                failed = True
                break
            rows.extend(
                _rows_from_json_things(
                    things,
                    submission_id,
                    submission_title,
                    keywords_by_category,
                )
            )
            for stub_id in _more_stub_ids_from_things(things):
                normalized = (
                    stub_id
                    if stub_id.startswith("t1_")
                    else f"t1_{stub_id}"
                )
                if normalized not in seen:
                    seen.add(normalized)
                    next_pending.append(normalized)

        if failed:
            break
        pending = next_pending

    return rows


def slugify(text: str, max_length: int = 60) -> str:
    """Converte um texto em um nome de arquivo seguro.

    Parameters
    ----------
    text : str
        Texto a ser convertido (ex.: titulo de um post).
    max_length : int
        Tamanho maximo do slug resultante.

    Returns
    -------
    str
        Slug em minusculas, sem acentos, com palavras unidas por "_".
    """
    without_accents = unicodedata.normalize("NFKD", text)
    ascii_only = without_accents.encode("ascii", "ignore").decode("ascii")
    slug = SLUG_RE.sub("_", ascii_only.lower()).strip("_")
    return slug[:max_length] or "post"


def _count_flags(rows: list[dict]) -> tuple[int, int]:
    """Conta ocorrencias de palavras-chave e categorias distintas.

    Parameters
    ----------
    rows : list[dict]
        Linhas no formato produzido por `parse_comments`.

    Returns
    -------
    tuple[int, int]
        Total de termos encontrados (somando repeticoes entre
        comentarios) e numero de categorias distintas encontradas.
    """
    categories_found: set[str] = set()
    keywords_found = 0
    for row in rows:
        if row["flagged_categories"]:
            categories_found.update(row["flagged_categories"].split("; "))
        if row["matched_keywords"]:
            for group in row["matched_keywords"].split("; "):
                keywords_found += len(group.split(", "))
    return keywords_found, len(categories_found)


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
    logger.info("Extraindo comentarios de %s", post_url)

    old_reddit_url = resolve_to_old_reddit(post_url)
    html = fetch_html(f"{old_reddit_url}?limit={COMMENT_PAGE_LIMIT}")
    soup = BeautifulSoup(html, "lxml")

    submission_id = extract_submission_id(old_reddit_url)
    submission_title = extract_submission_title(soup)

    rows = parse_comments(html, submission_id, submission_title)
    visible_count = len(rows)

    more_ids = extract_more_children_ids(soup)
    if more_ids:
        more_rows = collect_more_children_rows(
            submission_id, submission_title, more_ids
        )
        rows.extend(more_rows)

    if not rows and not more_ids:
        logger.warning(
            "'%s': 0 comentarios encontrados -- confira manualmente se "
            "a pagina nao veio bloqueada (js challenge/captcha) em vez "
            "de realmente vazia: %s",
            submission_title or submission_id,
            post_url,
        )

    logger.info(
        "'%s': %d comentarios coletados (%d visiveis + %d via 'load "
        "more comments')",
        submission_title,
        len(rows),
        visible_count,
        len(rows) - visible_count,
    )

    keywords_found, categories_found = _count_flags(rows)
    logger.info(
        "%d keywords encontradas, %d categorias encontradas",
        keywords_found,
        categories_found,
    )

    return pd.DataFrame(rows)


def collect_and_save_posts(urls: list[str], output_dir: Path) -> list[Path]:
    """Coleta varios posts e salva um CSV por post, nomeado pelo titulo.

    Parameters
    ----------
    urls : list[str]
        URLs dos posts a coletar.
    output_dir : pathlib.Path
        Diretorio onde os CSVs serao salvos, um por post.

    Returns
    -------
    list[pathlib.Path]
        Caminhos dos arquivos CSV salvos, na mesma ordem de `urls`.
    """
    saved_paths = []
    for index, url in enumerate(urls):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        start_time = time.perf_counter()

        try:
            df = collect_post_comments(url)
        except LoginRequiredError as exc:
            logger.warning("Pulando %s: %s", url, exc)
            continue

        title = df["submission_title"].iloc[0] if not df.empty else ""
        submission_id = df["submission_id"].iloc[0] if not df.empty else "post"

        filename = f"{slugify(title)}_{submission_id}.csv"
        output_path = output_dir / filename
        save_dataset(df, output_path)
        saved_paths.append(output_path)

        elapsed = time.perf_counter() - start_time
        logger.info(
            "Extracao de '%s' concluida em %.1fs",
            title or submission_id,
            elapsed,
        )

    return saved_paths


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
