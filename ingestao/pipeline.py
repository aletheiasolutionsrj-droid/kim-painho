"""
Pipeline de ingestão: transcrições (vídeo/podcast) e PDFs.

Os clientes do Qdrant e do Ollama podem ser injetados; sem isso, são criados
a partir das variáveis de ambiente (QDRANT_HOST e OLLAMA_HOST).
"""

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import parametros as P
from .armazenamento import Armazenamento, gerar_id_chunk
from .chunking import chunkar_paginas, chunkar_transcricao
from .embeddings import Embedder, modelo_da_colecao
from .limpeza import limpar_segmentos

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# ------------------------------------------------------------
# CLIENTES PADRÃO
# ------------------------------------------------------------

def criar_cliente_qdrant():

    from qdrant_client import QdrantClient

    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=6333,
        timeout=600
    )


def _preparar(colecao_id, qdrant, embedder):

    embedder = embedder or Embedder(modelo_da_colecao(colecao_id))
    qdrant = qdrant or criar_cliente_qdrant()

    return Armazenamento(qdrant, colecao_id), embedder


def preparar_colecao(colecao_id, qdrant=None, embedder=None):
    """
    Garante coleção e índices. Os índices precisam existir ANTES de qualquer
    consulta por documento: sem eles, o Qdrant varre todos os pontos e
    estoura o tempo em coleções grandes. Na primeira vez, criar os índices
    de uma coleção grande pode levar alguns minutos.
    """

    armazenamento, embedder = _preparar(colecao_id, qdrant, embedder)

    armazenamento.garantir_colecao(embedder.dimensao)
    armazenamento.garantir_indices()

    return armazenamento, embedder


def _avisar(progresso, fase, atual, total):

    if progresso:
        progresso(fase, atual, total)


# ------------------------------------------------------------
# UTILIDADES
# ------------------------------------------------------------

def slug(texto):

    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_").lower()

    return texto or "documento"


def agora_iso():
    """Momento do processamento, gravado em cada trecho (data_processamento)."""

    return datetime.now().isoformat(timespec="seconds")


def formatar_data_br(data):

    partes = str(data or "").split("-")

    if len(partes) == 3 and len(partes[0]) == 4:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"

    return str(data) if data else ""


def interpretar_edicao(nome_arquivo):
    """
    'Atlas Brasileiro - Janeiro de 2026 final.pdf'
        -> ("Janeiro de 2026", "2026-01-01")
    """

    achou = re.search(
        r"(" + "|".join(MESES + ["marco"]) + r")\s*(?:de\s*)?(\d{4})",
        nome_arquivo,
        re.IGNORECASE
    )

    if not achou:
        return None, None

    mes = achou.group(1).lower()
    mes = "março" if mes == "marco" else mes
    ano = achou.group(2)

    return f"{mes.capitalize()} de {ano}", f"{ano}-{MESES.index(mes) + 1:02d}-01"


def _cabecalho(*partes):

    texto = " — ".join(str(p) for p in partes if p)

    return f"{texto}\n" if texto and P.USAR_CABECALHO else ""


# ------------------------------------------------------------
# GRAVAÇÃO COMUM
# ------------------------------------------------------------

def _gravar(armazenamento, embedder, doc_id, chunks, textos_embedding, payloads, progresso):

    _avisar(progresso, "embeddings", 0, len(chunks))

    vetores = embedder.documentos(
        textos_embedding,
        lambda a, t: _avisar(progresso, "embeddings", a, t)
    )

    pontos = [
        (gerar_id_chunk(doc_id, chunk["indice"]), vetor, payload)
        for chunk, vetor, payload in zip(chunks, vetores, payloads)
    ]

    armazenamento.upsert(
        pontos,
        lambda a, t: _avisar(progresso, "gravando", a, t)
    )

    # só agora remove restos de uma versão anterior do documento
    armazenamento.remover_excedentes(doc_id, len(chunks))


# ------------------------------------------------------------
# TRANSCRIÇÕES (vídeo e podcast)
# ------------------------------------------------------------

def ingerir_transcricao(
    colecao_id,
    doc,
    *,
    qdrant=None,
    embedder=None,
    substituir=False,
    correcoes=None,
    existentes=None,
    progresso=None
):
    """
    existentes: conjunto de doc_id já cadastrados (opcional). Em lotes grandes,
    carregue-o uma vez com Armazenamento.ids_existentes() e passe aqui: evita
    uma consulta ao Qdrant por documento.

    doc: {
        "tipo_fonte": "video" (padrão) | "podcast",
        "video_id" ou "doc_id", "titulo", "data_publicacao",
        "url" (opcional), "episodio" (opcional),
        "origem_transcricao", "transcript": [{"text","start","duration"}]
    }
    """

    tipo = doc.get("tipo_fonte") or "video"
    doc_id = doc.get("doc_id") or doc.get("video_id")

    if not doc_id:
        raise ValueError("O documento precisa de 'video_id' ou 'doc_id'.")

    armazenamento, embedder = preparar_colecao(colecao_id, qdrant, embedder)

    if not substituir:

        ja_existe = (
            doc_id in existentes
            if existentes is not None
            else armazenamento.documento_existe(doc_id)
        )

        if ja_existe:
            return {"status": "ja_existe", "doc_id": doc_id, "chunks": 0}

    _avisar(progresso, "chunking", 0, 1)

    segmentos = limpar_segmentos(doc.get("transcript"), correcoes)
    chunks = chunkar_transcricao(segmentos)

    if not chunks:
        return {"status": "vazio", "doc_id": doc_id, "chunks": 0}

    titulo = doc.get("titulo") or doc_id
    data = doc.get("data_publicacao")
    origem = doc.get("origem_transcricao", "desconhecida")

    textos_embedding, payloads = [], []

    processado_em = agora_iso()

    for chunk in chunks:

        indice = chunk["indice"]

        payload = {
            "data_processamento": processado_em,
            "data_arquivo": doc.get("data_arquivo"),
            "tipo_fonte": tipo,
            "doc_id": doc_id,
            "titulo": titulo,
            "titulo_video": titulo,
            "data_publicacao": data,
            "origem_transcricao": origem,
            "chunk_index": indice,
            "chunk_id": f"{doc_id}_{indice:04d}",
            "timestamp_segundos": chunk["inicio_s"],
            "timestamp_fim_segundos": chunk["fim_s"],
            "timestamp_texto": chunk["timestamp_texto"],
            "texto_bruto": chunk["texto"],
            "versao_chunking": P.VERSAO_CHUNKING,
            "modelo_embedding": embedder.modelo,
        }

        if doc.get("titulo_original") and doc["titulo_original"] != titulo:
            payload["titulo_original"] = doc["titulo_original"]

        if tipo == "video":
            payload["video_id"] = doc_id
            payload["url"] = doc.get("url") or f"https://www.youtube.com/watch?v={doc_id}"
            payload["url_com_minuto"] = f"https://youtu.be/{doc_id}?t={chunk['inicio_s']}"
        else:
            # podcast: o endereço varia e não aceita minuto de forma padrão
            if doc.get("url"):
                payload["url"] = doc["url"]
            if doc.get("episodio") is not None:
                payload["episodio"] = doc["episodio"]

        payloads.append(payload)

        textos_embedding.append(
            _cabecalho(titulo, formatar_data_br(data)) + chunk["texto"]
        )

    _gravar(armazenamento, embedder, doc_id, chunks, textos_embedding, payloads, progresso)

    if existentes is not None:
        existentes.add(doc_id)

    return {
        "status": "inserido",
        "doc_id": doc_id,
        "chunks": len(chunks),
        "palavras": sum(c["palavras"] for c in chunks),
    }


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------

def ingerir_pdf(
    colecao_id,
    caminho,
    *,
    titulo=None,
    edicao=None,
    data_publicacao=None,
    doc_id=None,
    data_arquivo=None,
    qdrant=None,
    embedder=None,
    substituir=False,
    paginas_sem_numero=None,
    copiar_para=None,
    progresso=None
):
    """
    paginas_sem_numero: ver pdf.extrair_documento (None = ler do PDF).
    copiar_para: pasta onde guardar uma cópia do PDF, para abrir na página
    exata. A cópia é feita mesmo que o documento já esteja indexado.
    """
    from .arquivos import copiar_pdf
    from .pdf import extrair_documento, titulo_interno

    caminho = Path(caminho)

    doc_id = doc_id or slug(caminho.stem)

    if copiar_para:
        copiar_pdf(caminho, doc_id, copiar_para)

    armazenamento, embedder = preparar_colecao(colecao_id, qdrant, embedder)

    if not substituir and armazenamento.documento_existe(doc_id):
        return {"status": "ja_existe", "doc_id": doc_id, "chunks": 0}

    _avisar(progresso, "lendo_pdf", 0, 1)

    paginas, sumario = extrair_documento(caminho, paginas_sem_numero)

    interno = titulo_interno(caminho)

    edicao_nome, data_nome = interpretar_edicao(caminho.name)

    if not edicao_nome and interno:
        edicao_nome, data_nome = interpretar_edicao(interno)

    edicao = edicao or edicao_nome
    data_publicacao = data_publicacao or data_nome

    if not titulo and interno:
        titulo = re.sub(r"\.pdf$", "", interno, flags=re.IGNORECASE)
        titulo = re.sub(r"\s+final$", "", titulo, flags=re.IGNORECASE).strip()

    titulo = titulo or edicao or caminho.stem

    uteis = [p for p in paginas if not p.sumario and p.texto.strip()]

    chunks = chunkar_paginas([{"numero": p.numero, "texto": p.texto} for p in uteis])

    if not chunks:
        return {"status": "vazio", "doc_id": doc_id, "chunks": 0}

    por_numero = {p.numero: p for p in paginas}

    textos_embedding, payloads = [], []

    processado_em = agora_iso()

    for chunk in chunks:

        indice = chunk["indice"]
        inicio = por_numero[chunk["pagina"]]

        payload = {
            "data_processamento": processado_em,
            "data_arquivo": data_arquivo,
            "tipo_fonte": "pdf",
            "doc_id": doc_id,
            "identificador_documento": doc_id,
            "arquivo_nome": caminho.name,
            "titulo": titulo,
            "edicao": edicao,
            "data_publicacao": data_publicacao,
            "data_precisao": "mes" if data_publicacao and data_publicacao.endswith("-01") else "dia",
            "pagina": chunk["pagina"],
            "pagina_fim": chunk["pagina_fim"],
            "pagina_impressa": inicio.impressa,
            "total_paginas": len(paginas),
            "tema": inicio.tema,
            "subtema": inicio.subtema,
            "chunk_index": indice,
            "chunk_id": f"{doc_id}_{indice:04d}",
            "texto_bruto": chunk["texto"],
            "versao_chunking": P.VERSAO_CHUNKING,
            "modelo_embedding": embedder.modelo,
        }

        payloads.append(payload)

        textos_embedding.append(
            _cabecalho(titulo, inicio.tema, inicio.subtema) + chunk["texto"]
        )

    _gravar(armazenamento, embedder, doc_id, chunks, textos_embedding, payloads, progresso)

    return {
        "status": "inserido",
        "doc_id": doc_id,
        "chunks": len(chunks),
        "paginas": len(paginas),
        "temas_no_sumario": len(sumario),
    }


# ------------------------------------------------------------
# REPARO DE METADADOS (sem recalcular embeddings)
# ------------------------------------------------------------

def reparar_metadados(
    colecao_id,
    buscar_metadados,
    *,
    qdrant=None,
    atualizar_titulo=False,
    limite=None,
    pausa=None,
    progresso=None
):
    """
    Preenche data_publicacao (e opcionalmente o título) dos vídeos que
    estão sem data, consultando o YouTube e atualizando só o payload.

    buscar_metadados(video_id) -> {"titulo", "data_publicacao"}
    pausa: função sem argumentos chamada entre consultas (ex.: time.sleep aleatório)
    """

    qdrant = qdrant or criar_cliente_qdrant()
    armazenamento = Armazenamento(qdrant, colecao_id)

    pendentes = [
        doc_id
        for doc_id, doc in armazenamento.resumo_documentos().items()
        if doc["tipo_fonte"] == "video" and not doc["data_publicacao"]
    ]

    if limite:
        pendentes = pendentes[:limite]

    resultado = {"pendentes": len(pendentes), "reparados": 0, "falhas": []}

    for numero, doc_id in enumerate(pendentes, start=1):

        _avisar(progresso, "reparando", numero, len(pendentes))

        try:
            meta = buscar_metadados(doc_id)
        except Exception as e:
            resultado["falhas"].append((doc_id, str(e)))
            continue

        novo = {}

        if meta.get("data_publicacao"):
            novo["data_publicacao"] = meta["data_publicacao"]

        if atualizar_titulo and meta.get("titulo"):
            novo["titulo"] = meta["titulo"]
            novo["titulo_video"] = meta["titulo"]

        if novo:
            armazenamento.atualizar_payload_documento(doc_id, novo)
            resultado["reparados"] += 1

        if pausa and numero < len(pendentes):
            pausa()

    return resultado
