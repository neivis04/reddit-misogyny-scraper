"""Lista semente de termos para pre-filtro de discurso ofensivo/misogino.

Esta lista e apenas um filtro heuristico inicial para reduzir o volume
de comentarios a revisar/anotar manualmente -- ela NAO substitui
anotacao humana e nao deve ser usada como classificador final. Para o
TCC, recomenda-se validar e complementar esta lista com lexicons
academicos ja estabelecidos (ex.: HurtLex-PT) e com as diretrizes de
anotacao de corpora de referencia em portugues, como ToLD-BR e
OffComBR, e submeter a metodologia de coleta ao comite de etica em
pesquisa da instituicao antes da coleta em escala.
"""

from __future__ import annotations

OFFENSIVE_KEYWORDS: list[str] = [
    "vadia",
    "piranha",
    "vagabunda",
    "puta",
    "maluca",
    "cachorra",
    "vaca",
    "porno",
    "gostosa",
]


def contains_keyword(text: str, keywords: list[str]) -> bool:
    """Verifica se o texto contem algum termo da lista, ignorando caixa.

    Parameters
    ----------
    text : str
        Texto a ser analisado (ex.: corpo de um comentario).
    keywords : list[str]
        Termos a procurar dentro do texto.

    Returns
    -------
    bool
        ``True`` se algum termo da lista aparecer em `text`.
    """
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)
