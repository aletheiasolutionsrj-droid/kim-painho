"""
Legenda (.srt) de um trecho de vídeo e utilidades de tempo para o editor de cortes.

Funções puras: recebem segmentos [{"text", "start", "duration"}] e devolvem texto.
"""

import re

from . import parametros as P


# ------------------------------------------------------------
# TEMPOS
# ------------------------------------------------------------

def formatar_tempo(segundos):
    """90.5 -> '1:30.5' ; 3725 -> '1:02:05.0' (uma casa decimal)"""

    segundos = max(0.0, float(segundos))
    decimos = int(round(segundos * 10))

    horas, resto = divmod(decimos, 36000)
    minutos, resto = divmod(resto, 600)
    seg, dec = divmod(resto, 10)

    if horas:
        return f"{horas}:{minutos:02d}:{seg:02d}.{dec}"

    return f"{minutos}:{seg:02d}.{dec}"


def interpretar_tempo(texto):
    """'1:02:03.5' | '12:03' | '90' | '90,5' -> segundos (float). Levanta ValueError se inválido."""

    texto = str(texto or "").strip().replace(",", ".")

    if not re.match(r"^\d+(:\d{1,2}){0,2}(\.\d+)?$", texto):
        raise ValueError(f"Tempo inválido: {texto!r}. Use mm:ss, h:mm:ss ou segundos.")

    partes = texto.split(":")
    total = 0.0

    for parte in partes:
        total = total * 60 + float(parte)

    return total


def tempo_srt(segundos):
    """HH:MM:SS,mmm"""

    ms = int(round(max(0.0, segundos) * 1000))

    horas, ms = divmod(ms, 3_600_000)
    minutos, ms = divmod(ms, 60_000)
    seg, ms = divmod(ms, 1000)

    return f"{horas:02d}:{minutos:02d}:{seg:02d},{ms:03d}"


# ------------------------------------------------------------
# SELEÇÃO E SRT
# ------------------------------------------------------------

def falas_do_trecho(segmentos, inicio, fim, deslocar=False):
    """
    Falas que tocam [inicio, fim], com os tempos cortados nas bordas.
    Devolve [(inicio, fim, texto)]. Com deslocar=True os tempos passam a contar a partir do
    início do trecho (é o que o vídeo cortado precisa).
    """

    ordenados = sorted(segmentos, key=lambda s: s["start"])
    falas = []

    for i, seg in enumerate(ordenados):

        ini = float(seg["start"])
        proximo = float(ordenados[i + 1]["start"]) if i + 1 < len(ordenados) else None

        duracao = float(seg.get("duration") or 0)
        fim_seg = ini + duracao if duracao > 0 else (proximo if proximo and proximo > ini else ini + 2.0)

        # legendas automáticas costumam se sobrepor: a fala termina quando a próxima começa
        if proximo is not None and ini < proximo < fim_seg:
            fim_seg = proximo

        if fim_seg <= inicio or ini >= fim:
            continue

        a, b = max(ini, inicio), min(fim_seg, fim)
        texto = " ".join(str(seg.get("text", "")).split())

        if not texto or b - a < 0.05:
            continue

        if deslocar:
            a, b = a - inicio, b - inicio

        falas.append((a, b, texto))

    return falas


def montar_srt(segmentos, inicio, fim, deslocar=True):
    """Texto do arquivo .srt do trecho. Vazio se não houver fala no intervalo."""

    blocos = [
        f"{n}\n{tempo_srt(a)} --> {tempo_srt(b)}\n{texto}\n"
        for n, (a, b, texto) in enumerate(falas_do_trecho(segmentos, inicio, fim, deslocar), start=1)
    ]

    return "\n".join(blocos)


# ------------------------------------------------------------
# RECONSTRUÇÃO A PARTIR DOS TRECHOS DO BANCO (aproximada)
# ------------------------------------------------------------

def segmentos_aproximados(payloads, palavras_por_linha=8, sobreposicao=None):
    """
    O banco guarda trechos (chunks) de ~200 palavras, não as falas originais. Esta função reconstrói
    falas curtas: tira a sobreposição entre trechos vizinhos e distribui as palavras de cada trecho
    de forma uniforme entre o início e o fim dele. Os tempos ficam aproximados (erro de alguns segundos).
    """

    sobreposicao = P.CHUNK_SOBREPOSICAO if sobreposicao is None else sobreposicao

    trechos = sorted(payloads, key=lambda p: p.get("chunk_index", 0))
    segmentos = []

    for posicao, p in enumerate(trechos):

        palavras = (p.get("texto_bruto") or "").split()

        if not palavras:
            continue

        t0 = float(p.get("timestamp_segundos") or 0)
        t1 = float(p.get("timestamp_fim_segundos") or t0)
        t1 = max(t1, t0 + 1.0)

        total = len(palavras)
        descartar = min(sobreposicao, total - 1) if posicao else 0

        por_palavra = (t1 - t0) / total

        for inicio_linha in range(descartar, total, palavras_por_linha):

            linha = palavras[inicio_linha:inicio_linha + palavras_por_linha]

            segmentos.append({
                "text": " ".join(linha),
                "start": round(t0 + inicio_linha * por_palavra, 3),
                "duration": round(len(linha) * por_palavra, 3),
            })

    return segmentos
