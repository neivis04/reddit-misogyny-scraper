import requests
from bs4 import BeautifulSoup

from reddit_scraper import html_scraper
from reddit_scraper.html_scraper import (
    _rows_from_json_things as rows_from_json_things,
)
from reddit_scraper.html_scraper import (
    collect_more_children_rows,
    extract_more_children_ids,
    extract_submission_id,
    extract_submission_title,
    parse_comments,
    slugify,
)

SAMPLE_HTML = """
<html>
<head><title>Titulo do post : subreddit</title></head>
<body>
<div class="thing id-t3_abc123 link" data-fullname="t3_abc123">
    <p class="title">
      <a class="title may-blank" href="#">Titulo do post</a>
    </p>
</div>
<div class="commentarea">
  <div class="sitetable nestedlisting">
    <div
      class=" thing id-t1_c1 noncollapsed &#32; comment "
      id="thing_t1_c1"
      data-fullname="t1_c1"
      data-author="usuario_um"
    >
      <div class="entry unvoted">
        <span class="score" title="42">42 points</span>
        <div class="usertext-body">
          <div class="md"><p>comentario neutro</p></div>
        </div>
      </div>
      <div class="child">
        <div class="sitetable listing">
          <div
            class=" thing id-t1_c2 noncollapsed &#32; comment "
            id="thing_t1_c2"
            data-fullname="t1_c2"
            data-author="usuario_dois"
          >
            <div class="entry unvoted">
              <span class="score" title="3">3 points</span>
              <div class="usertext-body">
                <div class="md"><p>que vadia</p></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div
      class=" thing id-t1_c3 noncollapsed &#32; comment score-hidden "
      id="thing_t1_c3"
      data-fullname="t1_c3"
    >
      <div class="entry unvoted">
        <div class="usertext-body">
          <div class="md"><p>[deletado]</p></div>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


def test_extract_submission_id():
    """Deve extrair o id do post a partir da URL de comentarios."""
    url = "https://old.reddit.com/r/sub/comments/1v4hma8/titulo/"
    assert extract_submission_id(url) == "1v4hma8"


def test_extract_submission_title():
    """Deve extrair o titulo do post a partir do link de titulo."""
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    assert extract_submission_title(soup) == "Titulo do post"


SAMPLE_CATEGORIES = {"Sexualidade": ["vadia"]}


def test_parse_comments_extracts_all_including_nested():
    """Deve retornar comentarios de raiz e respostas aninhadas."""
    rows = parse_comments(
        SAMPLE_HTML, "abc123", "Titulo do post", SAMPLE_CATEGORIES
    )

    assert [row["comment_id"] for row in rows] == ["c1", "c2", "c3"]


def test_parse_comments_extracts_score_and_flags_keyword():
    """Deve extrair a pontuacao e marcar comentarios com termo ofensivo."""
    rows = parse_comments(
        SAMPLE_HTML, "abc123", "Titulo do post", SAMPLE_CATEGORIES
    )
    by_id = {row["comment_id"]: row for row in rows}

    assert by_id["c1"]["score"] == 42
    assert by_id["c1"]["flagged_by_keyword"] is False
    assert by_id["c1"]["flagged_categories"] == ""
    assert by_id["c2"]["score"] == 3
    assert by_id["c2"]["flagged_by_keyword"] is True
    assert by_id["c2"]["flagged_categories"] == "Sexualidade"
    assert by_id["c2"]["matched_keywords"] == "vadia"


def test_parse_comments_handles_missing_author_and_score():
    """Autor/pontuacao ausentes devem virar valores padrao seguros."""
    rows = parse_comments(SAMPLE_HTML, "abc123", "Titulo do post")
    by_id = {row["comment_id"]: row for row in rows}

    assert by_id["c3"]["author"] == "[deletado]"
    assert by_id["c3"]["score"] is None


def test_slugify_removes_accents_and_special_chars():
    """Deve virar minusculas, sem acentos, com "_" no lugar de espacos."""
    assert slugify("Galera vê maldade em tudo!") == "galera_ve_maldade_em_tudo"


def test_slugify_truncates_long_titles():
    """Nao deve ultrapassar o tamanho maximo informado."""
    slug = slugify("a" * 100, max_length=10)
    assert slug == "a" * 10


def test_slugify_empty_title_falls_back_to_post():
    """Titulo vazio deve virar o slug padrao "post"."""
    assert slugify("") == "post"


MORE_CHILDREN_HTML = """
<div class="commentarea">
  <div
    class=" thing id-t1_owht1m3 noncollapsed &#32; morechildren "
    id="thing_t1_owht1m3"
  >
    <div class="entry unvoted">
      <span class="morecomments">
        <a
          class="button"
          onclick="return morechildren(this, 't3_1urc8ah',
            'confidence', 'c1:t1_owht1m3', 'False')"
        >load more comments</a>
      </span>
    </div>
  </div>
  <div
    class=" thing id-t1_owh40ez noncollapsed &#32; morechildren "
    id="thing_t1_owh40ez"
  >
    <div class="entry unvoted">
      <span class="morecomments">
        <a
          class="button"
          onclick="return morechildren(this, 't3_1urc8ah',
            'confidence', 'c1:t1_owh40ez,t1_owi7emw,t1_owfwapi',
            'False')"
        >load more comments</a>
      </span>
    </div>
  </div>
</div>
"""


def test_extract_more_children_ids_parses_onclick_and_dedupes():
    """Deve extrair todos os ids, sem duplicatas, na ordem da pagina."""
    soup = BeautifulSoup(MORE_CHILDREN_HTML, "lxml")

    ids = extract_more_children_ids(soup)

    assert ids == ["t1_owht1m3", "t1_owh40ez", "t1_owi7emw", "t1_owfwapi"]


def test_extract_more_children_ids_no_stubs_returns_empty():
    """Pagina sem "load more comments" deve devolver lista vazia."""
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")

    assert extract_more_children_ids(soup) == []


def _json_comment(comment_id: str, body: str, replies=None) -> dict:
    return {
        "kind": "t1",
        "data": {
            "id": comment_id,
            "author": "usuario_exemplo",
            "body": body,
            "score": 5,
            "replies": replies or "",
        },
    }


def test_rows_from_json_things_flat_and_flagged():
    """Deve converter nos t1 em linhas, aplicando o filtro de categoria."""
    things = [_json_comment("j1", "comentario neutro")]

    rows = rows_from_json_things(things, "abc123", "Titulo", SAMPLE_CATEGORIES)

    assert rows[0]["comment_id"] == "j1"
    assert rows[0]["flagged_by_keyword"] is False


def test_rows_from_json_things_recurses_into_replies():
    """Respostas aninhadas nos nos t1 devem aparecer na lista final."""
    reply = _json_comment("j1-r1", "que vadia")
    replies_payload = {"data": {"children": [reply]}}
    parent = _json_comment("j1", "comentario pai", replies=replies_payload)

    rows = rows_from_json_things(
        [parent], "abc123", "Titulo", SAMPLE_CATEGORIES
    )

    assert [row["comment_id"] for row in rows] == ["j1", "j1-r1"]
    assert rows[1]["flagged_categories"] == "Sexualidade"


def test_rows_from_json_things_ignores_more_stub():
    """Stubs "more" aninhados nao devem ser buscados novamente aqui."""
    things = [{"kind": "more", "data": {"children": ["ignored"]}}]

    rows = rows_from_json_things(things, "abc123", "Titulo", SAMPLE_CATEGORIES)

    assert rows == []


def test_collect_more_children_rows_survives_request_failure(monkeypatch):
    """Falha na busca nao deve propagar erro, so registrar e seguir."""

    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError("bloqueado")

    monkeypatch.setattr(html_scraper, "fetch_more_children", _raise)

    rows = collect_more_children_rows(
        "abc123", "Titulo", ["t1_x"], SAMPLE_CATEGORIES
    )

    assert rows == []
