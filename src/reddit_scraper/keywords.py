"""Lista semente de termos, por categoria, para pre-filtro de ofensas.

Esta lista e apenas um filtro heuristico inicial para reduzir o volume
de comentarios a revisar/anotar manualmente -- ela NAO substitui
anotacao humana e nao deve ser usada como classificador final. Para o
TCC, recomenda-se validar e complementar esta lista com lexicons
academicos ja estabelecidos (ex.: HurtLex-PT) e com as diretrizes de
anotacao de corpora de referencia em portugues, como ToLD-BR e
OffComBR, e submeter a metodologia de coleta ao comite de etica em
pesquisa da instituicao antes da coleta em escala.

O casamento exige que o termo comece em um limite de palavra (ex.:
"vadia" casa com "vadias"/"vadiazinha", mas nao com o meio de outra
palavra). Isso evita falsos positivos grosseiros com termos curtos e
comuns como "dar" e "pau" (ex.: "andar", "cuidar", "paulista"), mas nao
elimina o risco por completo -- vale revisar manualmente os
comentarios marcados antes de qualquer analise quantitativa.
"""

from __future__ import annotations

import re

OFFENSIVE_KEYWORDS_BY_CATEGORY: dict[str, list[str]] = {
    "Capacidade cognitiva": [
        "burra",
        "idiota",
        "imbecil",
        "ignorante",
        "inútil",
        "leiga",
        "analfabeta",
        "retardada",
        "irracional",
        "doida",
        "louca",
        "desequilibrada",
        "maluca",
        "pirada",
    ],
    "Aparência física": [
        "feia",
        "gorda",
        "gordinha",
        "velha",
        "horrorosa",
        "bunduda",
        "gostosa",
    ],
    "Sexualidade": [
        "safada",
        "vagabunda",
        "piranha",
        "prostituta",
        "vadia",
        "galinha",
        "cachorra",
        "vulgar",
        "indecente",
        "porno",
        "pornô",
        "sexo",
        "pelada",
        "puta",
        "pau",
        "arrombada",
        "fetiche",
    ],
    "Conduta moral": [
        "imoral",
        "desonesta",
        "mentirosa",
        "falsa",
        "traidora",
        "oportunista",
        "interesseira",
        "manipuladora",
        "aproveitadora",
        "irresponsável",
        "negligente",
        "perdida",
        "hipócrita",
    ],
    "Submissão": [
        "frustrada",
        "submissa",
        "dependente",
        "obediente",
        "servil",
        "doméstica",
        "inferior",
        "frágil",
        "passiva",
    ],
    "Instabilidade emocional": [
        "hormonal",
        "tpm",
        "emocional",
        "sentimental",
        "instável",
        "volátil",
        "imprevisível",
        "menstruação",
        "complicada",
        "possessiva",
        "confusa",
    ],
    "Deslegitimação": [
        "dramática",
        "exagerada",
        "chata",
        "reclamona",
        "vitima",
        "emotiva",
        "sensível",
        "chorona",
        "neurótica",
        "paranoica",
    ],
    "Criação": [
        "pai",
        "ausente",
        "mãe",
        "abandonada",
        "criança",
        "solo",
        "filha",
    ],
}


def _starts_with_term(lowered_text: str, term: str) -> bool:
    """Verifica se `term` aparece em `lowered_text` a partir de um limite.

    Parameters
    ----------
    lowered_text : str
        Texto ja convertido para minusculas.
    term : str
        Termo a procurar (tambem em minusculas).

    Returns
    -------
    bool
        ``True`` se o termo ocorrer logo apos um limite de palavra.
    """
    pattern = rf"\b{re.escape(term)}"
    return re.search(pattern, lowered_text) is not None


def match_categories(
    text: str,
    keywords_by_category: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Encontra, para cada categoria, os termos que aparecem no texto.

    Parameters
    ----------
    text : str
        Texto a ser analisado (ex.: corpo de um comentario).
    keywords_by_category : dict[str, list[str]] or None
        Termos agrupados por categoria. Usa
        `OFFENSIVE_KEYWORDS_BY_CATEGORY` quando omitido.

    Returns
    -------
    dict[str, list[str]]
        Somente as categorias com pelo menos um termo encontrado,
        cada uma mapeada para a lista de termos encontrados nela.
    """
    keywords_by_category = (
        keywords_by_category
        if keywords_by_category is not None
        else OFFENSIVE_KEYWORDS_BY_CATEGORY
    )
    lowered = text.lower()
    matches: dict[str, list[str]] = {}
    for category, terms in keywords_by_category.items():
        found = [term for term in terms if _starts_with_term(lowered, term)]
        if found:
            matches[category] = found
    return matches


def format_matches(matches: dict[str, list[str]]) -> tuple[str, str]:
    """Formata os matches por categoria em duas colunas prontas para CSV.

    Parameters
    ----------
    matches : dict[str, list[str]]
        Saida de `match_categories`.

    Returns
    -------
    tuple[str, str]
        Categorias separadas por ``"; "`` e, na mesma ordem, os termos
        encontrados em cada categoria (``", "`` dentro do grupo e
        ``"; "`` entre grupos).
    """
    categories = "; ".join(matches.keys())
    keywords = "; ".join(", ".join(terms) for terms in matches.values())
    return categories, keywords
