"""
Chunking por janela de palavras, com sobreposição e corte em fim de frase.

Serve para transcrições (a "posição" de cada palavra é o tempo em segundos)
e para PDFs (a "posição" é a página).
"""

import re

from . import parametros as P

_RE_FIM_FRASE = re.compile(r"[.!?…]+[\"”’')\]]*$")


def formatar_timestamp(segundos):
    """MM:SS (os minutos podem passar de 59, como já era no projeto)."""

    segundos = int(segundos)

    return f"{segundos // 60:02d}:{segundos % 60:02d}"


def chunkar_palavras(
    palavras,
    inicios,
    fins,
    alvo=None,
    sobreposicao=None,
    busca_fim_frase=None,
    minimo=None,
    minimo_resto=None
):
    """
    palavras: lista de strings
    inicios/fins: posição (segundo ou página) de cada palavra

    Devolve lista de dicts:
        {"indice", "texto", "inicio", "fim", "palavras"}
    """

    alvo = alvo or P.CHUNK_PALAVRAS
    sobreposicao = P.CHUNK_SOBREPOSICAO if sobreposicao is None else sobreposicao
    busca_fim_frase = P.CHUNK_BUSCA_FIM_FRASE if busca_fim_frase is None else busca_fim_frase
    minimo = P.CHUNK_MIN_PALAVRAS if minimo is None else minimo
    minimo_resto = P.CHUNK_MIN_RESTO if minimo_resto is None else minimo_resto

    assert len(palavras) == len(inicios) == len(fins)
    assert 0 <= sobreposicao < alvo

    n = len(palavras)
    chunks = []
    i = 0

    while i < n:

        fim = min(i + alvo, n)

        if fim < n:

            # Procura o fim de frase mais próximo do limite, olhando para trás.
            menor = max(i + alvo - busca_fim_frase, i + 1)

            for j in range(fim, menor - 1, -1):

                if _RE_FIM_FRASE.search(palavras[j - 1]):
                    fim = j
                    break

            # Sobra pequena demais para virar chunk próprio: anexa a este.
            if n - fim < minimo_resto:
                fim = n

        if fim - i >= minimo:

            chunks.append({
                "indice": len(chunks),
                "texto": " ".join(palavras[i:fim]),
                "inicio": inicios[i],
                "fim": fins[fim - 1],
                "palavras": fim - i,
            })

        if fim >= n:
            break

        i = max(fim - sobreposicao, i + 1)

    return chunks


def chunkar_transcricao(segmentos):
    """segmentos já limpos: [{"text", "start", "duration"}]"""

    palavras, inicios, fins = [], [], []

    for seg in segmentos:

        fim_seg = seg["start"] + seg.get("duration", 0.0)

        for palavra in seg["text"].split():
            palavras.append(palavra)
            inicios.append(seg["start"])
            fins.append(fim_seg)

    chunks = chunkar_palavras(palavras, inicios, fins)

    for chunk in chunks:
        chunk["inicio_s"] = int(chunk["inicio"])
        chunk["fim_s"] = int(chunk["fim"])
        chunk["timestamp_texto"] = formatar_timestamp(chunk["inicio"])

    return chunks


def chunkar_paginas(paginas):
    """
    paginas: [{"numero": int, "texto": str, ...}] na ordem do documento.
    O chunk pode atravessar páginas: guarda a página inicial e a final.
    """

    palavras, inicios, fins = [], [], []

    for pagina in paginas:

        for palavra in pagina["texto"].split():
            palavras.append(palavra)
            inicios.append(pagina["numero"])
            fins.append(pagina["numero"])

    chunks = chunkar_palavras(palavras, inicios, fins)

    for chunk in chunks:
        chunk["pagina"] = int(chunk["inicio"])
        chunk["pagina_fim"] = int(chunk["fim"])

    return chunks
