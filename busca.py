import streamlit as st
import ollama

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    MatchPhrase,
    Range
)

from clientes import client_qdrant

from ingestao.embeddings import embed_consulta, modelo_da_colecao

def garantir_indice_texto_bruto(colecao_id):

    try:

        info = client_qdrant.get_collection(
            collection_name=colecao_id
        )

        if "texto_bruto" in info.payload_schema:

            print(
                "✅ Índice texto_bruto já existe.",
                flush=True
            )

            return

        print(
            "🔎 Índice texto_bruto não encontrado. Criando...",
            flush=True
        )

        from qdrant_client.models import (
            TextIndexParams,
            TextIndexType,
            TokenizerType
        )

        client_qdrant.create_payload_index(
            collection_name=colecao_id,
            field_name="texto_bruto",
            field_schema=TextIndexParams(
                type=TextIndexType.TEXT,
                tokenizer=TokenizerType.WORD,
                lowercase=True,
                phrase_matching=True
            ),
            wait=True
        )

        print(
            "✅ Índice texto_bruto criado com phrase matching.",
            flush=True
        )

    except Exception as e:

        print(
            f"⚠️ Não foi possível verificar/criar o índice texto_bruto: {e}",
            flush=True
        )

# Opção da barra lateral -> valor gravado em tipo_fonte
TIPOS_DE_FONTE = {
    "Apenas Vídeos": "video",
    "Apenas PDFs": "pdf",
    "Apenas Áudio/Podcast": "podcast",
}


def buscar_contexto_qdrant(
    pergunta,
    tipo_filtro,
    limite_busca,
    colecao_id,
    modo_busca="Contexto",
    ignorar_segundos=0
):
    """
    Busca trechos relevantes no Qdrant.

    Modos disponíveis:
    - 🔮 Contexto: busca semântica por embeddings.
    - 📌 Expressão exata: busca literal por uma expressão em texto_bruto.
    - 🔮📌 Ambos: combina busca semântica e busca literal.
    """

    try:

        print("DEBUG COLEÇÃO:", repr(colecao_id), flush=True)
        print("DEBUG MODO:", repr(modo_busca), flush=True)
        print("DEBUG PERGUNTA:", repr(pergunta), flush=True)

        # ============================================================
        # FILTRO POR TIPO DE FONTE
        # ============================================================

        condicoes = []

        if tipo_filtro != "Todo o acervo":

            tag_fonte = TIPOS_DE_FONTE.get(tipo_filtro)

            if tag_fonte:
                condicoes.append(
                    FieldCondition(
                        key="tipo_fonte",
                        match=MatchValue(value=tag_fonte)
                    )
                )

        # Ignorar o início: vídeos só a partir de N segundos.
        # Fontes que não são vídeo (PDF, podcast) passam direto.
        # O filtro é aplicado dentro do Qdrant, então o limite de
        # resultados continua valendo depois do filtro.
        if (
            ignorar_segundos and ignorar_segundos > 0
            and tipo_filtro in ("Todo o acervo", "Apenas Vídeos")
        ):

            condicoes.append(
                Filter(
                    should=[
                        Filter(
                            must_not=[
                                FieldCondition(
                                    key="tipo_fonte",
                                    match=MatchValue(value="video")
                                )
                            ]
                        ),
                        FieldCondition(
                            key="timestamp_segundos",
                            range=Range(gte=ignorar_segundos)
                        )
                    ]
                )
            )

        filtro_qdrant = (
            Filter(must=condicoes)
            if condicoes
            else None
        )


        # ============================================================
        # BUSCA SEMÂNTICA
        # ============================================================

        resultados_semanticos = []

        if modo_busca in ["Contexto", "Ambos"]:

            # O modelo de embedding é definido por acervo (campo
            # "embedding_model" do colecoes.json). Sem o campo, usa o original.
            vetor_pergunta = embed_consulta(
                pergunta,
                modelo_da_colecao(colecao_id)
            )

            resultados_semanticos = client_qdrant.query_points(
                collection_name=colecao_id,
                query=vetor_pergunta,
                limit=limite_busca,
                query_filter=filtro_qdrant
            ).points


        # ============================================================
        # BUSCA POR EXPRESSÃO EXATA
        # ============================================================

        resultados_textuais = []

        if modo_busca in ["Expressão exata", "Ambos"]:

            filtro_textual = Filter(
                must=[
                    FieldCondition(
                        key="texto_bruto",
                        match=MatchPhrase(
                            phrase=pergunta
                        )
                    )
                ]
            )

            # Se houver filtro de mídia, acrescenta ao filtro textual
            if filtro_qdrant is not None:
                filtro_textual.must.extend(
                    filtro_qdrant.must
                )

            resultados_textuais, _ = client_qdrant.scroll(
                collection_name=colecao_id,
                scroll_filter=filtro_textual,
                limit=limite_busca,
                with_payload=True,
                with_vectors=False
            )


        # ============================================================
        # RESULTADO FINAL
        # ============================================================

        if modo_busca == "Contexto":

            return resultados_semanticos


        if modo_busca == "Expressão exata":

            return resultados_textuais


        # ============================================================
        # AMBOS
        # ============================================================

        resultados_combinados = []

        ids_adicionados = set()

        for ponto in resultados_semanticos + resultados_textuais:

            if ponto.id not in ids_adicionados:

                resultados_combinados.append(ponto)
                ids_adicionados.add(ponto.id)


        return resultados_combinados


    except Exception as e:

        st.error(
            f"Erro ao conectar com o banco vetorial ou Ollama: {e}"
        )

        return []