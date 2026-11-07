import os
import json


# ============================================================
# CONFIGURAÇÃO DOS ACERVOS
# ============================================================

ARQUIVO_COLECOES = os.path.join(
    os.path.dirname(__file__),
    "data",
    "colecoes.json"
)


def carregar_colecoes():
    """
    Carrega as coleções disponíveis no arquivo colecoes.json.
    """

    if not os.path.exists(ARQUIVO_COLECOES):
        # Primeira execução (instalação nova): cria um acervo vazio para o usuário começar.
        # O arquivo não vai para o GitHub: cada instalação tem os seus acervos.
        os.makedirs(os.path.dirname(ARQUIVO_COLECOES), exist_ok=True)

        with open(ARQUIVO_COLECOES, "w", encoding="utf-8") as arquivo:
            json.dump(
                {"colecoes": [{
                    "id": "acervo_principal",
                    "nome": "Meu acervo",
                    "descricao": "Acervo inicial. Crie outros na página de Administração.",
                    "default": True,
                    "autor": "Meu acervo"
                }]},
                arquivo, ensure_ascii=False, indent=4
            )

    try:
        with open(
            ARQUIVO_COLECOES,
            "r",
            encoding="utf-8"
        ) as arquivo:
            dados = json.load(arquivo)

    except json.JSONDecodeError as e:
        raise ValueError(
            f"O arquivo colecoes.json possui um JSON inválido: {e}"
        )

    colecoes = dados.get("colecoes")

    if not isinstance(colecoes, list):
        raise ValueError(
            "O arquivo colecoes.json deve possuir uma lista 'colecoes'."
        )

    if not colecoes:
        raise ValueError(
            "Nenhuma coleção foi cadastrada no colecoes.json."
        )

    for colecao in colecoes:
        if not colecao.get("id"):
            raise ValueError(
                "Existe uma coleção sem 'id' no colecoes.json."
            )

    return colecoes


def obter_colecao_default(colecoes):
    """
    Retorna a coleção marcada como default.
    """

    colecoes_default = [
        colecao
        for colecao in colecoes
        if colecao.get("default") is True
    ]

    if len(colecoes_default) == 0:
        raise ValueError(
            "Nenhuma coleção está marcada como default no colecoes.json."
        )

    if len(colecoes_default) > 1:
        raise ValueError(
            "Mais de uma coleção está marcada como default no colecoes.json."
        )

    return colecoes_default[0]

def salvar_colecoes(colecoes):
    """
    Salva a lista de coleções no arquivo colecoes.json.
    """

    dados = {
        "colecoes": colecoes
    }

    with open(
        ARQUIVO_COLECOES,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=4
        )


def recarregar_colecoes():
    """
    Recarrega as coleções diretamente do arquivo colecoes.json.
    """

    colecoes = carregar_colecoes()
    colecao_default = obter_colecao_default(colecoes)

    return colecoes, colecao_default



COLECOES = carregar_colecoes()
COLECAO_DEFAULT = obter_colecao_default(COLECOES)

# ============================================================
# QDRANT
# ============================================================

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = 6333


# ============================================================
# OLLAMA / EMBEDDINGS
# ============================================================

MODELO_EMBEDDING = "nomic-embed-text"


# ============================================================
# LLM
# ============================================================

MODELO_LLM = "openai/gpt-oss-120b"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ============================================================
# RECUPERAÇÃO
# ============================================================

LIMITE_BUSCA = 20
LIMITE_LLM = 20