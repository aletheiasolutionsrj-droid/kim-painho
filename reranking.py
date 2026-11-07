from fastembed.rerank.cross_encoder import TextCrossEncoder


MODELO_RERANKER = "Xenova/ms-marco-MiniLM-L-6-v2"

reranker = TextCrossEncoder(
    model_name=MODELO_RERANKER
)


def selecionar_resultados(pergunta, resultados_qdrant):
    """
    Reordena os resultados recuperados pelo Qdrant usando
    um Cross Encoder para avaliar a relevância de cada
    trecho em relação à pergunta.
    """

    if not resultados_qdrant:
        return []

    # Cria pares (pergunta, documento)
    pares = [
        (
            pergunta,
            ponto.payload.get("texto_bruto", "")
        )
        for ponto in resultados_qdrant
    ]

    # Calcula a relevância de cada par
    scores = list(
        reranker.rerank_pairs(pares)
    )

    # Associa o score ao respectivo ponto
    resultados_com_score = []

    for ponto, score in zip(resultados_qdrant, scores):
        ponto.payload["score_reranker"] = float(score)
        resultados_com_score.append(ponto)

    # Maior score = maior relevância
    resultados_com_score.sort(
        key=lambda ponto: ponto.payload["score_reranker"],
        reverse=True
    )

    return resultados_com_score