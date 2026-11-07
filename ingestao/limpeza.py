"""Limpeza de segmentos de legenda e aplicação de glossário de nomes."""

import html
import re

_RE_COLCHETES = re.compile(r"\[[^\]]*\]")          # [música], [Aplausos], [ __ ]
_RE_MARCA_FALANTE = re.compile(r"^\s*(?:>>|&gt;&gt;)\s*")
_RE_ESPACOS = re.compile(r"\s+")


def limpar_texto(texto):
    """Remove ruído típico de legendas automáticas."""

    texto = html.unescape(str(texto or ""))
    texto = _RE_MARCA_FALANTE.sub("", texto)
    texto = _RE_COLCHETES.sub(" ", texto)
    texto = _RE_ESPACOS.sub(" ", texto)

    return texto.strip()


def limpar_segmentos(segmentos, correcoes=None):
    """
    Recebe [{"text", "start", "duration"}] e devolve a lista limpa:
    sem ruído, sem segmentos vazios, sem repetições consecutivas idênticas
    e com o glossário de correções aplicado.
    """

    regras = compilar_glossario(correcoes)

    limpos = []
    anterior = None

    for seg in segmentos or []:

        texto = limpar_texto(seg.get("text"))

        if not texto:
            continue

        if texto == anterior:
            continue

        anterior = texto

        texto = aplicar_regras(texto, regras)

        inicio = float(seg.get("start", 0.0))
        duracao = float(seg.get("duration", 0.0))

        limpos.append({
            "text": texto,
            "start": inicio,
            "duration": duracao,
        })

    return limpos


# ------------------------------------------------------------
# GLOSSÁRIO (correção de nomes próprios)
# ------------------------------------------------------------

def compilar_glossario(correcoes):
    """
    correcoes: {"grafia errada": "grafia certa"}.
    Casa palavra inteira, sem diferenciar maiúsculas de minúsculas.
    Grafias mais longas são aplicadas primeiro.
    """

    regras = []

    for errado, certo in sorted(
        (correcoes or {}).items(),
        key=lambda par: len(par[0]),
        reverse=True
    ):

        errado = str(errado).strip()

        if not errado:
            continue

        padrao = re.compile(
            r"(?<!\w)" + re.escape(errado) + r"(?!\w)",
            re.IGNORECASE | re.UNICODE
        )

        regras.append((padrao, str(certo)))

    return regras


def aplicar_regras(texto, regras):

    for padrao, certo in regras:
        texto = padrao.sub(certo, texto)

    return texto
