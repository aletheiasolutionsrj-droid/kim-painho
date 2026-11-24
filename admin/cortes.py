"""
Editor de cortes: legenda do trecho, arquivos gerados e nomes.

Os tempos exatos de cada fala não ficam no banco (só trechos de ~200 palavras), então a legenda do
trecho vem, em ordem de preferência, de: cópia local já guardada, transcrição do Whisper, legenda
do YouTube (buscada na hora e guardada) ou, no último caso, reconstrução aproximada dos trechos.
"""

import json
import re
import unicodedata
from datetime import datetime

from ingestao import legenda_srt
from ingestao.armazenamento import Armazenamento

from .tarefas import RAIZ

PASTA_CORTES = RAIZ / "data" / "cortes"
PASTA_CACHE_LEGENDAS = RAIZ / "data" / "legendas_cache"
PASTA_TRANSCRICOES = RAIZ / "data" / "transcricoes_whisper"

FONTES = {
    "cache": "cópia local da legenda",
    "whisper": "transcrição do Whisper",
    "youtube": "legenda do YouTube",
    "aproximada": "reconstruída dos trechos do banco (tempos aproximados)",
}


class SemLegenda(Exception):
    pass


def _ler_segmentos(caminho):

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    segmentos = dados.get("transcript") if isinstance(dados, dict) else dados

    return segmentos if isinstance(segmentos, list) and segmentos else None


def _idiomas_de_origem(origem):
    """'youtube:traduzido(en→pt)' -> ['en']"""

    achou = re.search(r"traduzido\(([\w-]+)", origem or "")

    return [achou.group(1)] if achou else None


def segmentos_do_video(video_id, colecao_id=None, qdrant=None, buscar_youtube=None,
                       pasta_cache=None, pasta_transcricoes=None):
    """
    Devolve (segmentos, fonte); fonte é uma chave de FONTES.
    buscar_youtube(video_id, traduzir_de) -> segmentos  (padrão: youtube-transcript-api)
    Levanta SemLegenda se nada serve.
    """

    pasta_cache = pasta_cache or PASTA_CACHE_LEGENDAS
    pasta_transcricoes = pasta_transcricoes or PASTA_TRANSCRICOES

    copia = _ler_segmentos(pasta_cache / f"{video_id}.json")

    if copia:
        return copia, "cache"

    payloads = []

    if colecao_id and qdrant is not None:
        try:
            payloads = Armazenamento(qdrant, colecao_id).chunks_do_documento(video_id)
        except Exception:
            payloads = []

    origem = (payloads[0].get("origem_transcricao") if payloads else "") or ""

    if origem.startswith("whisper") or not payloads:
        guardada = _ler_segmentos(pasta_transcricoes / f"{video_id}.json")

        if guardada:
            return guardada, "whisper"

    # vídeo de legenda do YouTube (ou ainda fora do acervo): busca a legenda original
    if not origem or origem.startswith("youtube") or origem == "desconhecida":

        if buscar_youtube is None:
            def buscar_youtube(v, traduzir_de):
                from ingestao import youtube
                return youtube.baixar_legenda_com_origem(v, traduzir_de=traduzir_de)[0]

        traduzir_de = _idiomas_de_origem(origem) or (["en", "es"] if not payloads else None)

        try:
            segmentos = buscar_youtube(video_id, traduzir_de)
        except Exception:
            segmentos = None          # bloqueio, sem legenda, rede: cai para a reconstrução

        if segmentos:
            pasta_cache.mkdir(parents=True, exist_ok=True)
            (pasta_cache / f"{video_id}.json").write_text(
                json.dumps({"transcript": segmentos}, ensure_ascii=False), encoding="utf-8"
            )
            return segmentos, "youtube"

    if payloads:
        aproximados = legenda_srt.segmentos_aproximados(payloads)

        if aproximados:
            return aproximados, "aproximada"

    raise SemLegenda(
        "Não encontrei legenda para este vídeo (ele não está no acervo e o YouTube não entregou uma)."
    )


# ------------------------------------------------------------
# ARQUIVOS
# ------------------------------------------------------------

def _slug(texto, limite=50):

    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-").lower()

    return texto[:limite].strip("-")


def _marca(segundos):

    s = int(segundos)

    return f"{s // 3600:02d}h{s % 3600 // 60:02d}m{s % 60:02d}s"


def nome_do_arquivo(titulo, video_id, inicio, fim):
    """Nome (sem extensão) do corte: titulo_videoid_00h12m03s-00h13m10s"""

    partes = [p for p in (_slug(titulo), video_id, f"{_marca(inicio)}-{_marca(fim)}") if p]

    return "_".join(partes)


def listar_cortes(pasta=None):
    """Cortes prontos, mais recentes primeiro: [{nome, video, legenda, tamanho, data}]"""

    pasta = pasta or PASTA_CORTES

    if not pasta.exists():
        return []

    itens = []

    for video in pasta.iterdir():

        if video.suffix.lower() not in (".mp4", ".mkv", ".webm") or not video.is_file():
            continue

        srt = video.with_suffix(".srt")

        itens.append({
            "nome": video.stem,
            "video": video,
            "legenda": srt if srt.exists() else None,
            "tamanho": video.stat().st_size,
            "data": datetime.fromtimestamp(video.stat().st_mtime),
        })

    return sorted(itens, key=lambda i: i["data"], reverse=True)


def remover_corte(nome, pasta=None):
    """Apaga o vídeo e a legenda do corte."""

    pasta = pasta or PASTA_CORTES

    if not re.match(r"^[\w.\-]+$", nome):
        raise ValueError("Nome de corte inválido.")

    for arquivo in pasta.glob(f"{nome}.*"):
        if arquivo.stem == nome:
            arquivo.unlink(missing_ok=True)
