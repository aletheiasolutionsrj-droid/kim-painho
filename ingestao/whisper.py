"""
Transcrição de áudio com faster-whisper (CPU ou GPU).

A biblioteca só é importada quando a transcrição roda. Os modelos são
baixados na primeira vez e guardados em data/modelos_whisper (persistem
porque a pasta do projeto é um volume do Docker).
"""

import os
from pathlib import Path

PASTA_MODELOS = Path(__file__).resolve().parents[1] / "data" / "modelos_whisper"

MODELOS = ["small", "medium", "large-v3"]


class Cancelado(Exception):
    pass


def disponivel():
    """True se a biblioteca faster-whisper está instalada nesta imagem."""

    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def configuracao():
    """
    (dispositivo, tipo_de_cálculo). Sem placa de vídeo usa a CPU com int8: o padrão da biblioteca
    seria 32 bits, que gasta ~4x mais memória e é bem mais lento. Pode ser forçado no .env com
    WHISPER_DEVICE (cpu|cuda) e WHISPER_COMPUTE_TYPE (int8, float16, float32...).
    """

    dispositivo = os.getenv("WHISPER_DEVICE", "auto").lower()

    if dispositivo == "auto":
        try:
            import ctranslate2

            dispositivo = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            dispositivo = "cpu"

    tipo = os.getenv("WHISPER_COMPUTE_TYPE") or ("int8" if dispositivo == "cpu" else "float16")

    return dispositivo, tipo


_carregado = {"chave": None, "modelo": None}


def _modelo(nome):
    """Reaproveita o modelo já carregado (carregar leva segundos e vários GB de memória)."""

    from faster_whisper import WhisperModel

    dispositivo, tipo = configuracao()
    chave = (nome, dispositivo, tipo)

    if _carregado["chave"] != chave:

        _carregado["modelo"] = None          # libera o anterior antes de carregar outro
        _carregado["chave"] = None

        PASTA_MODELOS.mkdir(parents=True, exist_ok=True)

        _carregado["modelo"] = WhisperModel(
            nome, device=dispositivo, compute_type=tipo, download_root=str(PASTA_MODELOS)
        )
        _carregado["chave"] = chave

    return _carregado["modelo"]


def transcrever(
    caminho_audio,
    idioma="pt",
    modelo="medium",
    prompt=None,
    hotwords=None,
    progresso=None,
    cancelado=None
):
    """
    Devolve [{"text","start","duration"}].

    prompt: dica de nomes próprios (ver glossario.prompt_whisper).
    hotwords: os mesmos nomes, separados por vírgula (reforço extra).
    progresso(segundos_transcritos, duracao_total) e cancelado() são opcionais.
    """

    whisper = _modelo(modelo)

    opcoes = dict(
        language=idioma,
        initial_prompt=prompt,
        vad_filter=True,          # ignora silêncio: reduz texto inventado
        beam_size=5
    )

    try:
        # "hotwords" reforça a grafia dos nomes; versões antigas não têm o parâmetro
        trechos, info = whisper.transcribe(str(caminho_audio), hotwords=hotwords, **opcoes)
    except TypeError:
        trechos, info = whisper.transcribe(str(caminho_audio), **opcoes)

    segmentos = []

    for trecho in trechos:

        if cancelado and cancelado():
            raise Cancelado()

        texto = trecho.text.strip()

        if texto:
            segmentos.append({
                "text": texto,
                "start": round(trecho.start, 3),
                "duration": round(trecho.end - trecho.start, 3),
            })

        if progresso:
            progresso(trecho.end, info.duration)

    return segmentos
