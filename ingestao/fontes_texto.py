"""Leitura de transcrições prontas (.srt, .vtt, .json, .txt) para o formato interno."""

import html
import json
import re

_RE_TEMPO = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
)
_RE_TAGS = re.compile(r"<[^>]+>")


def _segundos(h, m, s, ms):

    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def parse_legenda_tempo(texto):
    """SRT e VTT: blocos com 'inicio --> fim' seguidos do texto."""

    segmentos = []
    linhas = texto.replace("\r\n", "\n").replace("﻿", "").split("\n")

    i = 0

    while i < len(linhas):

        achou = _RE_TEMPO.search(linhas[i])

        if not achou:
            i += 1
            continue

        g = achou.groups()
        inicio = _segundos(g[0], g[1], g[2], g[3])
        fim = _segundos(g[4], g[5], g[6], g[7])

        i += 1
        partes = []

        while i < len(linhas) and linhas[i].strip():
            partes.append(linhas[i].strip())
            i += 1

        conteudo = html.unescape(_RE_TAGS.sub("", " ".join(partes))).strip()

        if conteudo:
            segmentos.append({
                "text": conteudo,
                "start": round(inicio, 3),
                "duration": round(max(fim - inicio, 0.0), 3),
            })

    return segmentos


def parse_json(conteudo):
    """
    Aceita o formato do projeto ({"transcript": [...]}) ou uma lista de
    segmentos {text,start,duration} / {text,start,end} (como o Whisper grava).
    """

    dados = json.loads(conteudo)

    lista = dados.get("transcript") if isinstance(dados, dict) else dados

    if not isinstance(lista, list):
        raise ValueError("JSON sem a lista 'transcript' nem lista de segmentos.")

    segmentos = []

    for item in lista:

        texto = str(item.get("text", "")).strip()

        if not texto:
            continue

        inicio = float(item.get("start", 0))

        if "duration" in item:
            duracao = float(item["duration"])
        else:
            duracao = max(float(item.get("end", inicio)) - inicio, 0.0)

        segmentos.append({"text": texto, "start": inicio, "duration": duracao})

    return segmentos


def metadados_json(conteudo):
    """
    Dados embutidos num JSON no formato do projeto ({"video_id","titulo",
    "data_publicacao","origem_transcricao","transcript"}). Outros formatos: {}.
    """

    try:
        dados = json.loads(conteudo)
    except (ValueError, TypeError):
        return {}

    if not isinstance(dados, dict):
        return {}

    return {
        k: dados.get(k)
        for k in ("video_id", "titulo", "data_publicacao", "origem_transcricao")
        if dados.get(k)
    }


def parse_texto_puro(texto):
    """Texto sem tempos: cada parágrafo vira um segmento em 0 (sem marcação de tempo)."""

    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto.replace("\r\n", "\n")) if p.strip()]

    if len(paragrafos) <= 1:
        paragrafos = [l.strip() for l in texto.splitlines() if l.strip()]

    return [{"text": " ".join(p.split()), "start": 0.0, "duration": 0.0} for p in paragrafos]


def ler_transcricao(nome_arquivo, conteudo_bytes):
    """
    Devolve (segmentos, com_tempo).
    com_tempo=False quando a transcrição não tem marcação de tempo.
    """

    nome = nome_arquivo.lower()
    texto = conteudo_bytes.decode("utf-8-sig", errors="replace")

    if nome.endswith((".srt", ".vtt")):
        segmentos = parse_legenda_tempo(texto)
        com_tempo = True
    elif nome.endswith(".json"):
        segmentos = parse_json(texto)
        com_tempo = any(s["start"] > 0 for s in segmentos)
    elif nome.endswith(".txt"):
        segmentos = parse_texto_puro(texto)
        com_tempo = False
    else:
        raise ValueError("Formato não suportado. Use .srt, .vtt, .json ou .txt.")

    if not segmentos:
        raise ValueError("Nenhum texto encontrado na transcrição.")

    return segmentos, com_tempo
