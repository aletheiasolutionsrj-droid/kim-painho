"""
Acesso ao YouTube (yt-dlp e youtube-transcript-api).

As bibliotecas só são importadas quando as funções são chamadas.
"""

# O YouTube pode devolver título traduzido (ex.: para inglês) conforme o
# idioma/IP da requisição. Pedimos português explicitamente.
OPCOES_YDL = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "http_headers": {"Accept-Language": "pt-BR,pt;q=0.9"},
    "extractor_args": {"youtube": {"lang": ["pt"]}},
}


def url_do_video(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def obter_metadados(video_id):
    """
    Consulta o vídeo individualmente (e não pela listagem do canal, que
    não traz a data de publicação).

    Devolve {"titulo", "data_publicacao" (AAAA-MM-DD ou None), "duracao"}.
    """

    from yt_dlp import YoutubeDL

    with YoutubeDL(OPCOES_YDL) as ydl:
        info = ydl.extract_info(url_do_video(video_id), download=False)

    data = info.get("upload_date")

    if data and len(data) == 8:
        data = f"{data[0:4]}-{data[4:6]}-{data[6:8]}"
    else:
        data = None

    return {
        "titulo": info.get("title"),
        "data_publicacao": data,
        "duracao": info.get("duration"),
    }


_ABAS_DO_CANAL = ("videos", "shorts", "streams", "live", "playlists", "releases", "podcasts", "featured", "about")


def _eh_url_de_canal(url):

    url = (url or "").lower()

    return any(m in url for m in ("/@", "/channel/", "/c/", "/user/")) and "list=" not in url


def url_da_aba(url, aba="videos"):
    """
    Endereço da aba de um canal. O link da raiz do canal (youtube.com/@nome) lista as ABAS,
    não os vídeos; o que interessa é @nome/videos.
    """

    partes = url.strip().split("?")[0].rstrip("/").split("/")

    if partes[-1].lower() in _ABAS_DO_CANAL:
        partes = partes[:-1]

    return "/".join(partes) + f"/{aba}"


def _entradas_de_video(info):
    """Percorre a listagem (inclusive listas dentro de listas) e devolve só IDs de vídeo válidos."""

    for e in (info or {}).get("entries") or []:

        if not e:
            continue

        if e.get("entries"):
            yield from _entradas_de_video(e)
        elif _RE_ID.match(e.get("id") or ""):
            yield e


def listar_videos_canal(url_canal, abas=("videos",)):
    """
    IDs e títulos dos vídeos de um canal ou playlist (listagem rápida; sem data de publicação).
    abas: para canais, quais abas ler: "videos", "streams" (lives), "shorts".
    """

    from yt_dlp import YoutubeDL

    opcoes = dict(OPCOES_YDL, extract_flat=True)

    alvos = (
        [url_da_aba(url_canal, aba) for aba in abas]
        if _eh_url_de_canal(url_canal)
        else [url_canal]
    )

    encontrados, vistos = [], set()

    with YoutubeDL(opcoes) as ydl:

        for numero, alvo in enumerate(alvos):

            try:
                info = ydl.extract_info(alvo, download=False)
            except Exception:
                if numero == 0:
                    raise            # a primeira aba é a principal: o erro importa (ex.: bloqueio de IP)
                continue             # lives/shorts podem simplesmente não existir

            for e in _entradas_de_video(info):
                if e["id"] not in vistos:
                    vistos.add(e["id"])
                    encontrados.append({"video_id": e["id"], "titulo": e.get("title")})

    return encontrados


def baixar_legenda_com_origem(video_id, idiomas=("pt-BR", "pt", "pt-PT"), traduzir_de=None, traduzir_para="pt"):
    """
    Devolve ([{"text","start","duration"}], origem).

    Procura primeiro a legenda em português. Se não houver e 'traduzir_de' trouxer idiomas
    (ex.: ["en"]), usa a legenda desse idioma e pede ao YouTube a tradução para 'traduzir_para'.
    origem: "youtube" ou "youtube:traduzido(en→pt)".
    Levanta LegendaIndisponivel quando não há legenda utilizável.
    """

    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi
    )

    api = YouTubeTranscriptApi()

    def montar(legenda):
        return [{"text": i.text, "start": i.start, "duration": i.duration} for i in legenda]

    try:
        return montar(api.fetch(video_id, languages=list(idiomas))), "youtube"

    except NoTranscriptFound:
        if not traduzir_de:
            raise LegendaIndisponivel(video_id)

    except TranscriptsDisabled:
        raise LegendaIndisponivel(video_id)

    except VideoUnavailable:
        raise LegendaIndisponivel(f"{video_id} (vídeo indisponível)")

    # sem legenda em português: tenta traduzir a de outro idioma
    try:
        original = api.list(video_id).find_transcript(list(traduzir_de))

        if not original.is_translatable:
            raise LegendaIndisponivel(f"{video_id} (a legenda em {original.language_code} não pode ser traduzida)")

        traduzida = original.translate(traduzir_para).fetch()

    except (NoTranscriptFound, TranscriptsDisabled):
        raise LegendaIndisponivel(video_id)

    except VideoUnavailable:
        raise LegendaIndisponivel(f"{video_id} (vídeo indisponível)")

    return montar(traduzida), f"youtube:traduzido({original.language_code}→{traduzir_para})"


def baixar_legenda(video_id, idiomas=("pt-BR", "pt", "pt-PT")):
    """Só os segmentos (sem a origem). Levanta LegendaIndisponivel se o vídeo não tem legenda."""

    return baixar_legenda_com_origem(video_id, idiomas)[0]


class LegendaIndisponivel(Exception):
    """O vídeo não tem legenda: a alternativa é transcrever o áudio (Whisper)."""


# ------------------------------------------------------------
# ENTRADA DO USUÁRIO
# ------------------------------------------------------------

import re as _re

_RE_ID = _re.compile(r"^[A-Za-z0-9_-]{11}$")
_RE_URL_VIDEO = _re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def extrair_video_id(texto):
    """ID de 11 caracteres a partir de um ID solto ou de uma URL de vídeo; senão None."""

    texto = (texto or "").strip()

    if _RE_ID.match(texto):
        return texto

    achou = _RE_URL_VIDEO.search(texto)

    return achou.group(1) if achou else None


def eh_canal_ou_playlist(texto):
    """True para links de canal (@nome, /channel/, /c/, /user/) ou playlist (list=)."""

    texto = (texto or "").strip().lower()

    if not texto.startswith(("http://", "https://", "www.", "youtube.com", "m.youtube.com")):
        return False

    if extrair_video_id(texto) and "list=" not in texto:
        return False

    return any(m in texto for m in ("/@", "/channel/", "/c/", "/user/", "/playlist", "list="))


def foi_bloqueio_de_ip(erro):
    """O YouTube recusou as requisições deste IP (comum depois de muitos downloads)."""

    texto = f"{type(erro).__name__} {erro}".lower()

    return any(m in texto for m in ("blocking requests from your ip", "ipblocked", "requestblocked", "429"))


def baixar_audio(video_id, pasta):
    """
    Baixa só o áudio (sem converter, sem ffmpeg) para transcrever com Whisper.
    Devolve o caminho do arquivo.
    """

    from pathlib import Path
    from yt_dlp import YoutubeDL

    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    opcoes = dict(OPCOES_YDL)
    opcoes.update({
        "skip_download": False,
        "format": "bestaudio/best",
        "outtmpl": str(pasta / f"{video_id}.%(ext)s"),
        "noplaylist": True,
    })

    with YoutubeDL(opcoes) as ydl:
        info = ydl.extract_info(url_do_video(video_id), download=True)
        return Path(ydl.prepare_filename(info))
