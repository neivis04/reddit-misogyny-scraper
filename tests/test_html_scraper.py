from bs4 import BeautifulSoup

from julgame_scraper.html_scraper import (
    extract_submission_id,
    extract_submission_title,
    parse_comments,
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


def test_parse_comments_extracts_all_including_nested():
    """Deve retornar comentarios de raiz e respostas aninhadas."""
    rows = parse_comments(
        SAMPLE_HTML, "abc123", "Titulo do post", keywords=["vadia"]
    )

    assert [row["comment_id"] for row in rows] == ["c1", "c2", "c3"]


def test_parse_comments_extracts_score_and_flags_keyword():
    """Deve extrair a pontuacao e marcar comentarios com termo ofensivo."""
    rows = parse_comments(
        SAMPLE_HTML, "abc123", "Titulo do post", keywords=["vadia"]
    )
    by_id = {row["comment_id"]: row for row in rows}

    assert by_id["c1"]["score"] == 42
    assert by_id["c1"]["flagged_by_keyword"] is False
    assert by_id["c2"]["score"] == 3
    assert by_id["c2"]["flagged_by_keyword"] is True


def test_parse_comments_handles_missing_author_and_score():
    """Autor/pontuacao ausentes devem virar valores padrao seguros."""
    rows = parse_comments(SAMPLE_HTML, "abc123", "Titulo do post")
    by_id = {row["comment_id"]: row for row in rows}

    assert by_id["c3"]["author"] == "[deletado]"
    assert by_id["c3"]["score"] is None
