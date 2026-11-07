"""
O que cada tipo de tarefa faz. Cada executor recebe (params, ctx) e devolve um
dicionário-resumo que a tela mostra ao final.

Tudo que toca a rede ou o hardware (YouTube, Whisper, Qdrant) passa pelo objeto
`deps`, que os testes substituem por versões falsas.
"""

import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ingestao import arquivos, glossario, pipeline
from ingestao import fontes_texto, parametros as P

from . import pendencias
from .tarefas import RAIZ

PASTA_AUDIO_TEMP = RAIZ / "data" / "audio_tmp"
PASTA_TRANSCRICOES = RAIZ / "data" / "transcricoes_whisper"


# ============================================================
# DEPENDÊNCIAS EXTERNAS (substituíveis nos testes)
# ============================================================

class Dependencias:

    def __init__(self):
        self._qdrant = None

    def qdrant(self):
        if self._qdrant is None:
            self._qdrant = pipeline.criar_cliente_qdrant()
        return self._qdrant

    def embedder(self, colecao_id):
        from ingestao.embeddings import Embedder, modelo_da_colecao
        return Embedder(modelo_da_colecao(colecao_id))

    def metadados(self, video_id):
        from ingestao import youtube
        return youtube.obter_metadados(video_id)

    def legenda(self, video_id, traduzir_de=None):
        """Devolve (segmentos, origem)."""
        from ingestao import youtube
        return youtube.baixar_legenda_com_origem(video_id, traduzir_de=traduzir_de)

    def traduzir_titulo(self, titulo):
        from ingestao import traducao
        return traducao.traduzir_titulo(titulo)

    def listar_canal(self, url, abas=("videos",)):
        from ingestao import youtube
        return youtube.listar_videos_canal(url, abas)

    def audio(self, video_id, pasta):
        from ingestao import youtube
        return youtube.baixar_audio(video_id, pasta)

    def transcrever(self, caminho, **kw):
        from ingestao import whisper
        return whisper.transcrever(caminho, **kw)

    def pausa(self):
        time.sleep(random.uniform(3, 7))      # evita bloqueio de IP pelo YouTube


deps = Dependencias()


# ============================================================
# AUXILIARES
# ============================================================

def _data_do_arquivo(caminho, de_pasta=True):
    """Data de modificação do arquivo de origem (AAAA-MM-DD); None para arquivos enviados pelo navegador."""

    if not de_pasta:
        return None

    try:
        return datetime.fromtimestamp(Path(caminho).stat().st_mtime).strftime("%Y-%m-%d")
    except OSError:
        return None


def _apagar(caminho):

    try:
        if caminho:
            Path(caminho).unlink(missing_ok=True)
    except OSError:
        pass


def _transcrever_audio(caminho, colecao_id, modelo, ctx, nome):
    """Whisper com os nomes do glossário como dica de grafia."""

    nomes = glossario.carregar(colecao_id)["nomes"]

    def progresso(feito, total):
        ctx.sub("whisper", int(feito), int(total or 0),
                f"transcrevendo áudio ({int(feito) // 60} de {int(total or 0) // 60} min)")

    return deps.transcrever(
        caminho,
        idioma="pt",
        modelo=modelo,
        prompt=glossario.prompt_whisper(nomes),
        hotwords=", ".join(nomes[:40]) or None,
        progresso=progresso,
        cancelado=ctx.cancelado
    )


def _guardar_transcricao(doc):
    """Whisper é caro: guarda o resultado para reindexar sem transcrever de novo."""

    PASTA_TRANSCRICOES.mkdir(parents=True, exist_ok=True)

    caminho = PASTA_TRANSCRICOES / f"{doc.get('doc_id') or doc.get('video_id')}.json"
    caminho.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _ingerir(colecao_id, doc, ctx, qdrant, embedder, substituir, existentes=None):

    correcoes = glossario.carregar(colecao_id)["correcoes"]

    return pipeline.ingerir_transcricao(
        colecao_id,
        doc,
        qdrant=qdrant,
        embedder=embedder,
        substituir=substituir,
        correcoes=correcoes,
        existentes=existentes,
        progresso=ctx.callback_pipeline()
    )


def _doc_id_valido(texto):

    doc_id = pipeline.slug(texto)

    if doc_id == "documento":
        raise ValueError("Informe um título ou identificador para o documento.")

    return doc_id


# ============================================================
# YOUTUBE (vídeos avulsos e canal)
# ============================================================

def legendas_youtube(params, ctx):
    """
    params: colecao_id, itens [{"video_id","titulo"}], canal_url, limite,
            substituir, whisper_se_faltar, modelo_whisper, reavaliar_pendentes
    """

    colecao_id = params["colecao_id"]
    substituir = bool(params.get("substituir"))
    usar_whisper = bool(params.get("whisper_se_faltar"))
    modelo = params.get("modelo_whisper") or "medium"
    traduzir_de = params.get("traduzir_de") or None

    qdrant = deps.qdrant()

    ctx.mensagem("Preparando o acervo e os índices...")
    armazenamento, embedder = pipeline.preparar_colecao(colecao_id, qdrant, deps.embedder(colecao_id))

    existentes = None if substituir else armazenamento.ids_existentes()

    itens = [dict(i) for i in (params.get("itens") or [])]

    if params.get("canal_url"):
        ctx.mensagem("Lendo a lista de vídeos do canal...")

        abas = ["videos"]

        if params.get("incluir_lives"):
            abas.append("streams")

        if params.get("incluir_shorts"):
            abas.append("shorts")

        do_canal = deps.listar_canal(params["canal_url"], tuple(abas))

        if not do_canal and not itens:
            raise ValueError(
                "Não encontrei vídeos neste endereço. Confira o link do canal ou da playlist "
                "(ex.: https://www.youtube.com/@nome) e se o canal tem vídeos públicos."
            )

        ctx.log(f"Lista do canal: {len(do_canal)} vídeo(s).")
        itens += do_canal

    vistos, unicos = set(), []

    for item in itens:
        if item["video_id"] not in vistos:
            vistos.add(item["video_id"])
            unicos.append(item)

    resumo = {
        "na_lista": len(unicos), "inseridos": 0, "chunks": 0, "ja_existiam": 0,
        "sem_legenda": [], "whisper": 0, "traduzidos": 0, "titulos_traduzidos": 0, "falhas": [], "bloqueado": False, "restantes": 0,
    }

    sem_legenda_antigos = set()

    if not params.get("reavaliar_pendentes"):
        sem_legenda_antigos = {p["video_id"] for p in pendencias.listar(colecao_id)}

    pendentes = []

    for item in unicos:
        if existentes is not None and item["video_id"] in existentes:
            resumo["ja_existiam"] += 1
        elif item["video_id"] in sem_legenda_antigos and not usar_whisper:
            resumo["sem_legenda"].append(item["video_id"])
        else:
            pendentes.append(item)

    if params.get("limite"):
        pendentes = pendentes[: int(params["limite"])]

    total = len(pendentes)
    ctx.log(f"{total} vídeo(s) para processar ({resumo['ja_existiam']} já estavam no acervo).")

    from ingestao import youtube

    for numero, item in enumerate(pendentes, start=1):

        ctx.verificar()

        video_id = item["video_id"]
        ctx.geral("videos", numero - 1, total, f"Vídeo {numero} de {total}: {item.get('titulo') or video_id}")

        try:
            meta = deps.metadados(video_id)
        except Exception as e:
            if youtube.foi_bloqueio_de_ip(e):
                resumo["bloqueado"], resumo["restantes"] = True, total - numero + 1
                ctx.log(f"O YouTube bloqueou este IP. Pare e tente de novo mais tarde. ({e})")
                break
            meta = {"titulo": item.get("titulo"), "data_publicacao": None}
            ctx.log(f"{video_id}: sem metadados ({e})")

        titulo = meta.get("titulo") or item.get("titulo") or video_id

        origem = "youtube"

        try:
            segmentos, origem = deps.legenda(video_id, traduzir_de)

            if origem != "youtube":
                resumo["traduzidos"] += 1

        except youtube.LegendaIndisponivel:

            if not usar_whisper:
                pendencias.registrar(colecao_id, video_id, titulo)
                resumo["sem_legenda"].append(video_id)
                ctx.log(f"{video_id}: sem legenda no YouTube — fica na lista de pendências.")
                deps.pausa()
                continue

            ctx.log(f"{video_id}: sem legenda — baixando o áudio para o Whisper.")

            try:
                audio = deps.audio(video_id, PASTA_AUDIO_TEMP)
                try:
                    segmentos = _transcrever_audio(audio, colecao_id, modelo, ctx, titulo)
                finally:
                    _apagar(audio)
            except Exception as e:
                if type(e).__name__ == "Cancelado":
                    raise
                resumo["falhas"].append((video_id, f"Whisper: {e}"))
                ctx.log(f"{video_id}: falha no Whisper: {e}")
                continue

            origem = f"whisper:{modelo}"
            resumo["whisper"] += 1

        except Exception as e:

            if youtube.foi_bloqueio_de_ip(e):
                resumo["bloqueado"], resumo["restantes"] = True, total - numero + 1
                ctx.log(f"O YouTube bloqueou este IP. Pare e tente de novo mais tarde. ({e})")
                break

            resumo["falhas"].append((video_id, str(e)))
            ctx.log(f"{video_id}: ERRO {type(e).__name__}: {e}")
            deps.pausa()
            continue

        doc = {
            "tipo_fonte": "video", "video_id": video_id, "titulo": titulo,
            "data_publicacao": meta.get("data_publicacao"),
            "origem_transcricao": origem, "transcript": segmentos,
        }

        if params.get("traduzir_titulo") and origem.startswith("youtube:traduzido"):

            traduzido = deps.traduzir_titulo(titulo)

            if traduzido and traduzido != titulo:
                doc["titulo_original"], doc["titulo"] = titulo, traduzido
                resumo["titulos_traduzidos"] += 1
                ctx.log(f"{video_id}: título traduzido: {titulo} -> {traduzido}")

        if origem.startswith("whisper"):
            _guardar_transcricao(doc)

        try:
            r = _ingerir(colecao_id, doc, ctx, qdrant, embedder, substituir, existentes)
        except Exception as e:
            if type(e).__name__ == "Cancelado":
                raise
            resumo["falhas"].append((video_id, str(e)))
            ctx.log(f"{video_id}: ERRO ao gravar: {type(e).__name__}: {e}")
            continue

        if r["status"] == "inserido":
            resumo["inseridos"] += 1
            resumo["chunks"] += r["chunks"]
            pendencias.remover(colecao_id, video_id)
            ctx.log(f"{video_id}: {doc['titulo']} — {r['chunks']} trechos.")
        elif r["status"] == "vazio":
            resumo["falhas"].append((video_id, "transcrição vazia"))

        if not origem.startswith("whisper"):
            deps.pausa()        # só houve rede do YouTube: espaça os pedidos

    ctx._geral = None
    ctx.progresso("videos", total, total, "Concluído", forcar=True)

    return resumo


# ============================================================
# IMPORTAÇÃO DE LEGENDAS EM ARQUIVO (.json, .srt, .vtt)
# ============================================================

def importar_legendas(params, ctx):
    """
    Importa legendas de vídeos do YouTube que já estão em arquivos.

    params: colecao_id, itens [{"caminho","nome_original","video_id" (ID ou link),
            "titulo","data_publicacao","apagar_origem"}], substituir,
            buscar_metadados (consulta o YouTube para o que faltar),
            salvar_json (pasta onde guardar a conversão .srt/.vtt -> .json, ou None)
    Dados que o formulário deixou vazios são lidos de dentro do .json, quando houver.
    """

    from ingestao import youtube

    colecao_id = params["colecao_id"]
    substituir = bool(params.get("substituir"))
    itens = params.get("itens") or []
    pasta_json = Path(params["salvar_json"]) if params.get("salvar_json") else None

    qdrant = deps.qdrant()

    ctx.mensagem("Preparando o acervo e os índices...")
    armazenamento, embedder = pipeline.preparar_colecao(colecao_id, qdrant, deps.embedder(colecao_id))

    existentes = None if substituir else armazenamento.ids_existentes()

    resumo = {"total": len(itens), "inseridos": 0, "chunks": 0, "ja_existiam": 0,
              "json_salvos": 0, "falhas": []}

    total = len(itens)

    for numero, item in enumerate(itens, start=1):

        ctx.verificar()

        caminho = Path(item["caminho"])
        nome = item.get("nome_original") or caminho.name

        ctx.geral("arquivos", numero - 1, total, f"Arquivo {numero} de {total}: {nome}")

        try:
            conteudo = caminho.read_bytes()

            segmentos, com_tempo = fontes_texto.ler_transcricao(nome, conteudo)

            if not com_tempo:
                raise ValueError("sem marcação de tempo (use .srt, .vtt ou .json com tempos)")

            embutido = fontes_texto.metadados_json(conteudo) if nome.lower().endswith(".json") else {}

            video_id = (
                youtube.extrair_video_id(item.get("video_id") or "")
                or youtube.extrair_video_id(embutido.get("video_id") or "")
            )

            if not video_id:
                raise ValueError("faltou o link ou o ID do vídeo")

            if existentes is not None and video_id in existentes:
                resumo["ja_existiam"] += 1
                continue

            titulo = item.get("titulo") or embutido.get("titulo")
            data = item.get("data_publicacao") or embutido.get("data_publicacao")

            if params.get("buscar_metadados") and (not titulo or not data):
                try:
                    meta = deps.metadados(video_id)
                    titulo = titulo or meta.get("titulo")
                    data = data or meta.get("data_publicacao")
                except Exception as e:
                    ctx.log(f"{nome}: sem metadados do YouTube ({e})")
                deps.pausa()

            doc = {
                "tipo_fonte": "video", "video_id": video_id,
                "titulo": titulo or video_id, "data_publicacao": data or None,
                "origem_transcricao": embutido.get("origem_transcricao") or "arquivo",
                "data_arquivo": _data_do_arquivo(caminho, not item.get("apagar_origem")),
                "transcript": segmentos,
            }

            r = _ingerir(colecao_id, doc, ctx, qdrant, embedder, substituir, existentes)

            if r["status"] == "ja_existe":
                resumo["ja_existiam"] += 1
            elif r["status"] == "vazio":
                resumo["falhas"].append((nome, "transcrição vazia"))
            else:
                resumo["inseridos"] += 1
                resumo["chunks"] += r["chunks"]

                # .srt/.vtt viram .json; um .json sem ID de vídeo ganha uma cópia completa
                precisa_copia = not nome.lower().endswith(".json") or not embutido.get("video_id")

                if pasta_json and precisa_copia:
                    pasta_json.mkdir(parents=True, exist_ok=True)
                    destino = pasta_json / f"{video_id}.json"
                    destino.write_text(json.dumps({
                        "video_id": video_id, "titulo": doc["titulo"],
                        "data_publicacao": doc["data_publicacao"],
                        "origem_transcricao": doc["origem_transcricao"],
                        "transcript": segmentos,
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                    resumo["json_salvos"] += 1

        except Exception as e:

            if type(e).__name__ == "Cancelado":
                raise

            resumo["falhas"].append((nome, str(e)))
            ctx.log(f"{nome}: ERRO {type(e).__name__}: {e}")

        finally:
            if item.get("apagar_origem"):
                _apagar(caminho)

    ctx._geral = None
    ctx.progresso("arquivos", total, total, "Concluído", forcar=True)

    return resumo


# ============================================================
# PDF
# ============================================================

def ingerir_pdf(params, ctx):
    """
    params: colecao_id, caminho, titulo, edicao, data_publicacao, doc_id,
            substituir, paginas_sem_numero, guardar_copia, apagar_origem
    """

    caminho = Path(params["caminho"])

    try:
        resultado = pipeline.ingerir_pdf(
            params["colecao_id"],
            caminho,
            titulo=params.get("titulo") or None,
            edicao=params.get("edicao") or None,
            data_publicacao=params.get("data_publicacao") or None,
            doc_id=params.get("doc_id") or None,
            data_arquivo=_data_do_arquivo(caminho, not params.get("apagar_origem")),
            qdrant=deps.qdrant(),
            embedder=deps.embedder(params["colecao_id"]),
            substituir=bool(params.get("substituir")),
            paginas_sem_numero=params.get("paginas_sem_numero"),
            copiar_para=arquivos.PASTA_PDFS if params.get("guardar_copia", True) else None,
            progresso=ctx.callback_pipeline()
        )
    finally:
        if params.get("apagar_origem"):
            _apagar(caminho)

    return resultado


# ============================================================
# TRANSCRIÇÃO PRONTA (srt, vtt, json) E ÁUDIO (Whisper)
# ============================================================

def _montar_doc(params, segmentos, origem):

    tipo = params.get("tipo_fonte") or "podcast"

    doc_id = params.get("doc_id") or _doc_id_valido(params.get("titulo") or "")

    doc = {
        "tipo_fonte": tipo,
        "doc_id": doc_id,
        "titulo": params.get("titulo") or doc_id,
        "data_publicacao": params.get("data_publicacao") or None,
        "origem_transcricao": origem,
        "transcript": segmentos,
    }

    if tipo == "video":
        doc["video_id"] = doc_id
    else:
        if params.get("url"):
            doc["url"] = params["url"].strip()
        if params.get("episodio") not in (None, ""):
            doc["episodio"] = params["episodio"]

    return doc


def ingerir_transcricao_arquivo(params, ctx):
    """
    params: colecao_id, caminho, nome_original, tipo_fonte (podcast|video),
            titulo, data_publicacao, doc_id, episodio, url, substituir, apagar_origem
    """

    caminho = Path(params["caminho"])

    try:
        segmentos, com_tempo = fontes_texto.ler_transcricao(
            params.get("nome_original") or caminho.name, caminho.read_bytes()
        )

        if not com_tempo:
            raise ValueError(
                "Esta transcrição não tem marcação de tempo, então não dá para mostrar "
                "o minuto exato de cada trecho. Envie o .srt/.vtt/.json com tempos, ou "
                "o áudio para o Whisper transcrever."
            )

        doc = _montar_doc(params, segmentos, "arquivo")
        doc["data_arquivo"] = _data_do_arquivo(caminho, not params.get("apagar_origem"))

        return _ingerir(
            params["colecao_id"], doc, ctx, deps.qdrant(), deps.embedder(params["colecao_id"]),
            bool(params.get("substituir"))
        )

    finally:
        if params.get("apagar_origem"):
            _apagar(caminho)


def transcrever_audio(params, ctx):
    """
    params: colecao_id, caminho_audio (mp3 enviado) OU video_id (baixa do YouTube),
            modelo_whisper, tipo_fonte, titulo, data_publicacao, doc_id,
            episodio, url, substituir, apagar_origem
    """

    colecao_id = params["colecao_id"]
    modelo = params.get("modelo_whisper") or "medium"
    video_id = params.get("video_id")

    audio = params.get("caminho_audio")
    baixado = False

    try:
        if video_id:

            meta = {}

            try:
                meta = deps.metadados(video_id)
            except Exception as e:
                ctx.log(f"Sem metadados do YouTube: {e}")

            params = dict(
                params,
                tipo_fonte="video",
                doc_id=video_id,
                titulo=params.get("titulo") or meta.get("titulo") or video_id,
                data_publicacao=params.get("data_publicacao") or meta.get("data_publicacao"),
            )

            if not audio:
                ctx.mensagem("Baixando o áudio do YouTube...")
                audio = deps.audio(video_id, PASTA_AUDIO_TEMP)
                baixado = True

        nome = params.get("titulo") or Path(audio).name

        segmentos = _transcrever_audio(audio, colecao_id, modelo, ctx, nome)

        if not segmentos:
            raise ValueError("O Whisper não encontrou fala no áudio.")

        doc = _montar_doc(params, segmentos, f"whisper:{modelo}")
        doc["data_arquivo"] = _data_do_arquivo(audio, not baixado and not params.get("apagar_origem"))
        _guardar_transcricao(doc)

        resultado = _ingerir(
            colecao_id, doc, ctx, deps.qdrant(), deps.embedder(colecao_id),
            bool(params.get("substituir"))
        )

        if video_id and resultado["status"] == "inserido":
            pendencias.remover(colecao_id, video_id)

        resultado["segmentos"] = len(segmentos)

        return resultado

    finally:
        if baixado or params.get("apagar_origem"):
            _apagar(audio)


# ============================================================
# MANUTENÇÃO
# ============================================================

def reparar_metadados(params, ctx):

    def pausa():
        ctx.verificar()
        deps.pausa()

    return pipeline.reparar_metadados(
        params["colecao_id"],
        deps.metadados,
        qdrant=deps.qdrant(),
        atualizar_titulo=bool(params.get("atualizar_titulo")),
        limite=params.get("limite"),
        pausa=pausa,
        progresso=ctx.callback_pipeline()
    )


def backup(params, ctx):

    import backup_qdrant

    ctx.mensagem("Criando e baixando o snapshot (pode levar alguns minutos)...")

    return backup_qdrant.criar_backup_qdrant(params["colecao_id"])


def restaurar_snapshot(params, ctx):
    """params: colecao_id (destino, vazio), caminho (.snapshot), apagar_origem"""

    import httpx

    from config import QDRANT_HOST, QDRANT_PORT

    colecao_id = params["colecao_id"]
    caminho = Path(params["caminho"])
    qdrant = deps.qdrant()

    try:
        if qdrant.count(collection_name=colecao_id, exact=True).count != 0:
            raise ValueError("O destino não está vazio. A restauração foi cancelada.")

        ctx.mensagem("Enviando o snapshot ao Qdrant. Aguarde a conclusão...")

        url = (
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{quote(colecao_id, safe='')}"
            "/snapshots/upload?wait=true&priority=snapshot"
        )

        with open(caminho, "rb") as arquivo:
            with httpx.Client(timeout=httpx.Timeout(3600.0, connect=30.0)) as http:
                resposta = http.post(
                    url,
                    files={"snapshot": (caminho.name, arquivo, "application/octet-stream")}
                )

        resposta.raise_for_status()

        if not resposta.json().get("result", False):
            raise RuntimeError("O Qdrant não confirmou a restauração.")

        depois = qdrant.count(collection_name=colecao_id, exact=True).count

        if depois == 0:
            raise RuntimeError(
                "O Qdrant respondeu, mas o destino continua sem pontos. Verifique o snapshot."
            )

        return {"colecao_id": colecao_id, "pontos": depois}

    finally:
        if params.get("apagar_origem"):
            _apagar(caminho)


EXECUTORES = {
    "legendas_youtube": legendas_youtube,
    "importar_legendas": importar_legendas,
    "pdf": ingerir_pdf,
    "transcricao_arquivo": ingerir_transcricao_arquivo,
    "transcrever_audio": transcrever_audio,
    "reparar_metadados": reparar_metadados,
    "backup": backup,
    "restaurar_snapshot": restaurar_snapshot,
}

ROTULOS = {
    "legendas_youtube": "Vídeos do YouTube",
    "importar_legendas": "Importar legendas",
    "pdf": "PDF",
    "transcricao_arquivo": "Transcrição pronta",
    "transcrever_audio": "Áudio (Whisper)",
    "reparar_metadados": "Reparar datas e títulos",
    "backup": "Backup",
    "restaurar_snapshot": "Restaurar backup",
}
