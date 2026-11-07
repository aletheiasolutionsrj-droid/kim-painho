"""Diagnóstico de acervos e dos serviços. Só lógica; a tela apenas mostra o resultado."""

import os
import shutil

from ingestao import parametros as P
from ingestao.armazenamento import Armazenamento


def nomes_no_qdrant(client):

    return sorted(c.name for c in client.get_collections().collections)


def esta_vazia(client, colecao_id):
    """Consulta rápida (sem contagem exata) para decidir se aceita restauração."""

    return client.count(collection_name=colecao_id, exact=True).count == 0


def diagnosticar(client, colecao_id, limite_amostra=20000):
    """
    Resumo de uma coleção: pontos, índices que faltam e problemas nos registros.
    Os registros são conferidos por amostra (até limite_amostra) para não travar.
    """

    from qdrant_client.models import FieldCondition, Filter, MatchValue

    if not client.collection_exists(collection_name=colecao_id):
        return {"existe": False}

    info = client.get_collection(collection_name=colecao_id)
    indices = {
        campo: str(getattr(esq, "data_type", esq))
        for campo, esq in (info.payload_schema or {}).items()
    }

    def contar(tipo):
        return client.count(
            collection_name=colecao_id,
            count_filter=Filter(must=[FieldCondition(key="tipo_fonte", match=MatchValue(value=tipo))]),
            exact=True
        ).count

    total = client.count(collection_name=colecao_id, exact=True).count

    resultado = {
        "existe": True,
        "pontos": total,
        "por_tipo": {t: contar(t) for t in ("video", "pdf", "podcast")},
        "indices": indices,
        "indices_ausentes": [c for c in P.INDICES_PAYLOAD if c not in indices],
        "amostra": 0,
        "sem_texto": 0,
        "sem_tipo_fonte": 0,
        "video_sem_tempo": 0,
        "sem_data": 0,
        "modelos": {},
        "documentos": 0,
    }

    docs, offset = set(), None
    campos = ["doc_id", "video_id", "tipo_fonte", "texto_bruto", "timestamp_segundos",
              "data_publicacao", "modelo_embedding"]

    while resultado["amostra"] < limite_amostra:

        pontos, offset = client.scroll(
            collection_name=colecao_id, limit=1000, offset=offset,
            with_payload=campos, with_vectors=False
        )

        for ponto in pontos:

            pl = ponto.payload or {}
            resultado["amostra"] += 1

            docs.add(pl.get("doc_id") or pl.get("video_id"))

            if not (pl.get("texto_bruto") or "").strip():
                resultado["sem_texto"] += 1

            if not pl.get("tipo_fonte"):
                resultado["sem_tipo_fonte"] += 1

            if pl.get("tipo_fonte") in ("video", "podcast") and pl.get("timestamp_segundos") is None:
                resultado["video_sem_tempo"] += 1

            if not pl.get("data_publicacao"):
                resultado["sem_data"] += 1

            modelo = pl.get("modelo_embedding") or "não registrado"
            resultado["modelos"][modelo] = resultado["modelos"].get(modelo, 0) + 1

        if offset is None:
            break

    docs.discard(None)
    resultado["documentos"] = len(docs)
    resultado["amostra_completa"] = offset is None

    return resultado


def criar_indices_ausentes(client, colecao_id):

    return Armazenamento(client, colecao_id).garantir_indices()


def servicos(cliente_ollama=None):
    """Estado das dependências do sistema: [(nome, ok, detalhe)]."""

    itens = []

    itens.append((
        "pdftotext (leitura de PDF)",
        shutil.which("pdftotext") is not None,
        "instalado" if shutil.which("pdftotext") else "não encontrado na imagem do Docker"
    ))

    chave = bool(os.getenv("GROQ_API_KEY"))
    itens.append((
        "Chave da Groq (respostas da IA)", chave,
        "configurada" if chave else "GROQ_API_KEY ausente no .env"
    ))

    try:
        import ollama

        modelos = {m.get("model") or m.get("name") for m in (cliente_ollama or ollama).list().get("models", [])}
        modelos = {str(m).split(":")[0] for m in modelos}

        for nome in P.MODELOS_EMBEDDING:
            itens.append((
                f"Ollama: modelo {nome}", nome in modelos,
                "disponível" if nome in modelos else f"execute: ollama pull {nome}"
            ))

    except Exception as e:
        itens.append(("Ollama", False, f"não respondeu ({type(e).__name__})"))

    from ingestao import whisper

    ok = whisper.disponivel()
    itens.append((
        "Whisper (transcrição de áudio)", ok,
        "instalado" if ok else "faster-whisper não instalado: adicione ao requirements.txt e refaça o build"
    ))

    return itens
