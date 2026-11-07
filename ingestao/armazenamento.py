"""Tudo que fala com o Qdrant na ingestão."""

import hashlib

from . import parametros as P


def gerar_id_chunk(doc_id, indice):
    """
    Mesma fórmula dos scripts antigos (sha256 de "<id>_<índice>"):
    reingerir um vídeo já cadastrado sobrescreve os mesmos pontos.
    """

    chave = f"{doc_id}_{indice}"
    hash_bytes = hashlib.sha256(chave.encode("utf-8")).digest()

    return int.from_bytes(hash_bytes[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF


class ErroDimensao(RuntimeError):
    """O vetor do modelo não cabe na coleção existente."""


class Armazenamento:

    def __init__(self, client, colecao_id):

        self.client = client
        self.colecao_id = colecao_id

    # --------------------------------------------------------
    # COLEÇÃO E ÍNDICES
    # --------------------------------------------------------

    def garantir_colecao(self, dimensao):

        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(collection_name=self.colecao_id):

            self.client.create_collection(
                collection_name=self.colecao_id,
                vectors_config=VectorParams(
                    size=dimensao,
                    distance=Distance.COSINE
                )
            )

            return "criada"

        info = self.client.get_collection(collection_name=self.colecao_id)
        vetores = info.config.params.vectors

        tamanho = getattr(vetores, "size", None)

        if tamanho is not None and tamanho != dimensao:
            raise ErroDimensao(
                f"A coleção '{self.colecao_id}' usa vetores de {tamanho} "
                f"dimensões, mas o modelo de embedding gera {dimensao}. "
                "Use o mesmo modelo com que o acervo foi criado, ou crie um "
                "acervo novo para o outro modelo."
            )

        return "existente"

    def garantir_indices(self):

        from qdrant_client.models import (
            PayloadSchemaType,
            TextIndexParams,
            TextIndexType,
            TokenizerType
        )

        info = self.client.get_collection(collection_name=self.colecao_id)
        existentes = set((info.payload_schema or {}).keys())

        criados = []

        for campo, tipo in P.INDICES_PAYLOAD.items():

            if campo in existentes:
                continue

            if tipo == "text":
                esquema = TextIndexParams(
                    type=TextIndexType.TEXT,
                    tokenizer=TokenizerType.WORD,
                    lowercase=True,
                    phrase_matching=True
                )
            elif tipo == "integer":
                esquema = PayloadSchemaType.INTEGER
            else:
                esquema = PayloadSchemaType.KEYWORD

            self.client.create_payload_index(
                collection_name=self.colecao_id,
                field_name=campo,
                field_schema=esquema,
                wait=True
            )

            criados.append(campo)

        return criados

    # --------------------------------------------------------
    # DOCUMENTOS
    # --------------------------------------------------------

    def _filtro_documento(self, doc_id):
        """Casa pelo doc_id novo OU pelo video_id dos acervos antigos."""

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        return Filter(
            should=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="video_id", match=MatchValue(value=doc_id)),
            ]
        )

    def contar_documento(self, doc_id):

        return self.client.count(
            collection_name=self.colecao_id,
            count_filter=self._filtro_documento(doc_id),
            exact=True
        ).count

    def documento_existe(self, doc_id):

        return self.contar_documento(doc_id) > 0

    def ids_existentes(self):
        """Todos os doc_id/video_id já presentes (para ingestão incremental)."""

        existentes = set()
        offset = None

        while True:

            pontos, offset = self.client.scroll(
                collection_name=self.colecao_id,
                limit=1000,
                offset=offset,
                with_payload=["doc_id", "video_id"],
                with_vectors=False
            )

            for ponto in pontos:

                payload = ponto.payload or {}
                chave = payload.get("doc_id") or payload.get("video_id")

                if chave:
                    existentes.add(chave)

            if offset is None:
                break

        return existentes

    def upsert(self, pontos, progresso=None):
        """pontos: [(id, vetor, payload)] enviados em lotes."""

        from qdrant_client.models import PointStruct

        enviados = 0

        for inicio in range(0, len(pontos), P.LOTE_UPSERT):

            lote = [
                PointStruct(id=pid, vector=vetor, payload=payload)
                for pid, vetor, payload in pontos[inicio:inicio + P.LOTE_UPSERT]
            ]

            self.client.upsert(
                collection_name=self.colecao_id,
                points=lote,
                wait=True
            )

            enviados += len(lote)

            if progresso:
                progresso(enviados, len(pontos))

        return enviados

    def remover_excedentes(self, doc_id, total_chunks):
        """
        Depois de gravar os chunks novos, remove os antigos que sobraram
        (índice >= total). Gravar antes e limpar depois evita ficar sem o
        documento se algo falhar no meio.
        """

        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            Range
        )

        filtro = Filter(
            must=[
                self._filtro_documento(doc_id),
                FieldCondition(
                    key="chunk_index",
                    range=Range(gte=total_chunks)
                )
            ]
        )

        self.client.delete(
            collection_name=self.colecao_id,
            points_selector=FilterSelector(filter=filtro),
            wait=True
        )

    def apagar_documento(self, doc_id):

        from qdrant_client.models import FilterSelector

        self.client.delete(
            collection_name=self.colecao_id,
            points_selector=FilterSelector(
                filter=self._filtro_documento(doc_id)
            ),
            wait=True
        )

    def apagar_documentos(self, doc_ids, lote=100, progresso=None):
        """Apaga vários documentos (e todos os seus trechos) com poucas chamadas ao Qdrant."""

        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        ids = list(doc_ids)

        for inicio in range(0, len(ids), lote):

            condicoes = []

            for doc_id in ids[inicio:inicio + lote]:
                condicoes.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))
                condicoes.append(FieldCondition(key="video_id", match=MatchValue(value=doc_id)))

            self.client.delete(
                collection_name=self.colecao_id,
                points_selector=FilterSelector(filter=Filter(should=condicoes)),
                wait=True
            )

            if progresso:
                progresso(min(inicio + lote, len(ids)), len(ids))

    def atualizar_payload_documento(self, doc_id, payload):
        """Altera metadados de todos os chunks do documento, sem recalcular vetores."""

        self.client.set_payload(
            collection_name=self.colecao_id,
            payload=payload,
            points=self._filtro_documento(doc_id),
            wait=True
        )

    # --------------------------------------------------------
    # INVENTÁRIO
    # --------------------------------------------------------

    def resumo_documentos(self):
        """
        {doc_id: {"tipo_fonte", "titulo", "data_publicacao", "data_processamento", "data_arquivo", "origem_transcricao", "chunks"}}
        Lê só o payload necessário, sem vetores.
        """

        docs = {}
        offset = None

        campos = ["doc_id", "video_id", "tipo_fonte", "titulo", "titulo_video", "data_publicacao",
                  "data_processamento", "data_arquivo", "origem_transcricao"]

        while True:

            pontos, offset = self.client.scroll(
                collection_name=self.colecao_id,
                limit=1000,
                offset=offset,
                with_payload=campos,
                with_vectors=False
            )

            for ponto in pontos:

                payload = ponto.payload or {}
                chave = payload.get("doc_id") or payload.get("video_id")

                if not chave:
                    continue

                doc = docs.setdefault(chave, {
                    "tipo_fonte": payload.get("tipo_fonte"),
                    "titulo": payload.get("titulo") or payload.get("titulo_video"),
                    "data_publicacao": payload.get("data_publicacao"),
                    "data_processamento": payload.get("data_processamento"),
                    "data_arquivo": payload.get("data_arquivo"),
                    "origem_transcricao": payload.get("origem_transcricao"),
                    "chunks": 0,
                })

                doc["chunks"] += 1

            if offset is None:
                break

        return docs
