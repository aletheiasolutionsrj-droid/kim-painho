"""Embeddings em lote, com o modelo definido por acervo."""

from . import parametros as P


# ------------------------------------------------------------
# MODELO DE CADA ACERVO
# ------------------------------------------------------------

def modelo_da_colecao(colecao_id, colecoes=None):
    """
    Lê o campo "embedding_model" do acervo no colecoes.json.
    Acervos antigos, sem o campo, continuam com o modelo original.
    """

    if colecoes is None:
        from config import carregar_colecoes
        colecoes = carregar_colecoes()

    for colecao in colecoes:
        if colecao.get("id") == colecao_id:
            return colecao.get("embedding_model") or P.MODELO_PADRAO

    return P.MODELO_PADRAO


def info_modelo(modelo):

    return P.MODELOS_EMBEDDING.get(
        modelo,
        {"dim": None, "prefixo_documento": "", "prefixo_consulta": ""}
    )


# ------------------------------------------------------------
# CHAMADA AO OLLAMA
# ------------------------------------------------------------

def _cliente_padrao():
    import ollama
    return ollama


def _embed(cliente, modelo, textos):
    """Um lote de textos -> lista de vetores. Usa a API em lote quando existe."""

    if hasattr(cliente, "embed"):

        resposta = cliente.embed(model=modelo, input=list(textos))

        try:
            return resposta["embeddings"]
        except (KeyError, TypeError):
            return resposta.embeddings

    # clientes antigos do ollama: um texto por chamada
    return [
        cliente.embeddings(model=modelo, prompt=texto)["embedding"]
        for texto in textos
    ]


class Embedder:

    def __init__(self, modelo=None, cliente=None):

        self.modelo = modelo or P.MODELO_PADRAO
        self.cliente = cliente or _cliente_padrao()
        self.info = info_modelo(self.modelo)

    @property
    def dimensao(self):

        if self.info["dim"]:
            return self.info["dim"]

        # modelo fora da lista: descobre medindo um vetor
        return len(_embed(self.cliente, self.modelo, ["teste"])[0])

    def documentos(self, textos, progresso=None):
        """Embeda os textos em lotes. progresso(atual, total) é opcional."""

        prefixo = self.info["prefixo_documento"]
        vetores = []

        for inicio in range(0, len(textos), P.LOTE_EMBEDDING):

            lote = [prefixo + t for t in textos[inicio:inicio + P.LOTE_EMBEDDING]]

            vetores.extend(_embed(self.cliente, self.modelo, lote))

            if progresso:
                progresso(len(vetores), len(textos))

        return vetores

    def consulta(self, texto):

        prefixo = self.info["prefixo_consulta"]

        return _embed(self.cliente, self.modelo, [prefixo + texto])[0]


def embed_consulta(texto, modelo=None, cliente=None):
    """Atalho usado pela busca."""

    return Embedder(modelo, cliente).consulta(texto)
