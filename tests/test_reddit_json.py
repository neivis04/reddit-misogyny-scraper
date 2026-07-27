from julgame_scraper.reddit_json import flatten_comments


def _comment(comment_id: str, body: str, replies=None) -> dict:
    return {
        "kind": "t1",
        "data": {
            "id": comment_id,
            "author": "usuario_exemplo",
            "body": body,
            "score": 1,
            "created_utc": 1700000000,
            "replies": replies or "",
        },
    }


def test_flatten_comments_flat_list():
    """Deve retornar uma linha por comentario, na ordem original."""
    children = [
        _comment("c1", "comentario neutro"),
        _comment("c2", "que vadia"),
    ]

    rows = flatten_comments(children, "sub1", "Titulo", keywords=["vadia"])

    assert [row["comment_id"] for row in rows] == ["c1", "c2"]
    assert rows[0]["flagged_by_keyword"] is False
    assert rows[1]["flagged_by_keyword"] is True


def test_flatten_comments_ignores_more_stub():
    """Stubs "more" (comentarios colapsados) devem ser ignorados."""
    children = [{"kind": "more", "data": {"children": ["ignored_id"]}}]

    rows = flatten_comments(children, "sub1", "Titulo")

    assert rows == []


def test_flatten_comments_recurses_into_replies():
    """Respostas aninhadas devem aparecer na lista final."""
    reply = _comment("c1-r1", "resposta neutra")
    replies_payload = {"data": {"children": [reply]}}
    parent = _comment("c1", "comentario pai", replies=replies_payload)

    rows = flatten_comments([parent], "sub1", "Titulo")

    assert [row["comment_id"] for row in rows] == ["c1", "c1-r1"]


def test_flatten_comments_handles_deleted_author():
    """Autor ausente deve virar o marcador "[deletado]"."""
    children = [_comment("c1", "")]
    children[0]["data"]["author"] = None

    rows = flatten_comments(children, "sub1", "Titulo")

    assert rows[0]["author"] == "[deletado]"
