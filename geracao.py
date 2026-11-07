from clientes import client_groq
from config import MODELO_LLM


# ============================================================
# AUXILIARES
# ============================================================

def formatar_data(valor):
    """Converte 'AAAA-MM-DD' em 'DD/MM/AAAA'. Outros formatos passam como estão."""

    if not valor:
        return None

    texto = str(valor).strip()

    partes = texto.split("-")

    if len(partes) == 3 and len(partes[0]) == 4:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"

    return texto


def rotulo_fonte(numero, payload):
    """
    Cabeçalho que identifica cada trecho no prompt, para que a IA
    consiga citar a fonte, o momento e distinguir épocas diferentes.
    """

    data = formatar_data(payload.get("data_publicacao")) or "data não informada"

    if payload.get("tipo_fonte") == "pdf":
        return (
            f'[Fonte {numero}] PDF: "{payload.get("arquivo_nome", "sem nome")}" '
            f'| Data/edição: {data} '
            f'| Página {payload.get("pagina", "?")}'
        )

    titulo = payload.get("titulo_video") or payload.get("titulo") or "sem título"

    if payload.get("tipo_fonte") == "podcast":

        episodio = payload.get("episodio")

        return (
            f'[Fonte {numero}] Podcast/áudio: "{titulo}"'
            + (f" (episódio {episodio})" if episodio is not None else "")
            + f' | Publicado em: {data} '
            f'| Trecho a partir de {payload.get("timestamp_texto", "?")}'
        )

    return (
        f'[Fonte {numero}] Vídeo: "{titulo}" '
        f'| Publicado em: {data} '
        f'| Trecho a partir de {payload.get("timestamp_texto", "?")}'
    )


def montar_contexto(pontos):
    """Devolve (contexto_unificado, lista_de_payloads)."""

    blocos = []
    fontes = []

    for numero, ponto in enumerate(pontos, start=1):
        payload = ponto.payload or {}
        texto = payload.get("texto_bruto", "")

        blocos.append(f"{rotulo_fonte(numero, payload)}\n{texto}")
        fontes.append(payload)

    return "\n\n---\n\n".join(blocos), fontes


def montar_prompt_sistema(colecao=None):
    """Prompt de sistema, personalizado pelo acervo selecionado."""

    colecao = colecao or {}

    nome_acervo = colecao.get("nome", "Acervo")
    autor = colecao.get("autor") or nome_acervo
    descricao = colecao.get("descricao") or (
        f"Conteúdos de {autor} (transcrições de vídeos e áudios, e documentos PDF)."
    )

    return f"""
        Você é o Kim Painho, um oráculo que consulta o acervo "{nome_acervo}",
        reunido a partir do conteúdo de {autor} e disponibilizado nesta aplicação.

        Descrição do acervo: {descricao}

        Cada trecho recebido vem identificado por um cabeçalho
        "[Fonte N] ..." com título, data e momento (minuto ou página).

        Comece a resposta com UMA frase curta, bem-humorada, dizendo que o
        Kim Painho consultou o acervo "{nome_acervo}" para trazer os dados
        (varie a frase). Depois responda normalmente.

        Responda utilizando prioritariamente e estritamente as informações
        presentes nos trechos recuperados.

        Não invente informações e não complete lacunas utilizando conhecimento
        externo ao contexto fornecido.

        Diferencie claramente fatos, declarações, opiniões e interpretações
        presentes nas fontes. Quando uma afirmação for opinião ou interpretação
        de {autor}, deixe isso claro na resposta.

        Considere as datas: opiniões e fatos mudam com o tempo. Se as fontes
        forem de épocas diferentes, informe a cronologia e aponte mudanças de
        posição, quando existirem. Se uma fonte não tiver data, não presuma uma.

        Cite as fontes no corpo da resposta usando o formato [Fonte N],
        com N igual ao número do cabeçalho.

        Se os trechos recuperados não forem suficientes para responder à
        pergunta, informe que o Kim Painho não encontrou informações
        suficientes no acervo.
        """


# ============================================================
# GERAÇÃO
# ============================================================

def gerar_resposta_groq(
    pergunta,
    resultados_qdrant,
    temperatura,
    limite_llm,
    colecao=None
):
    """Monta o prompt RAG e envia para a Groq gerar o resumo explicativo."""

    resultados_qdrant = resultados_qdrant[:limite_llm]

    contexto_unificado, fontes = montar_contexto(resultados_qdrant)

    prompt_sistema = montar_prompt_sistema(colecao)

    prompt_usuario = f"""
    Contexto do acervo:
    {contexto_unificado}

    Pergunta: {pergunta}
    """

    try:
        resposta = client_groq.chat.completions.create(
            model=MODELO_LLM,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=temperatura
        )

        conteudo = resposta.choices[0].message.content

        # A Groq respondeu, mas não retornou conteúdo
        if not conteudo or not conteudo.strip():
            mensagem = (
                "⚠️ **Não foi possível gerar a resposta do Kim Painho.**\n\n"
                "A consulta ao acervo foi realizada e os trechos relevantes "
                "foram encontrados, mas a Inteligência Artificial não retornou "
                "uma resposta.\n\n"
                "Se você estiver utilizando a **Groq na modalidade gratuita**, "
                "é possível que tenha atingido algum limite de uso ou processamento.\n\n"
                "🔄 Tente novamente em alguns instantes ou considere utilizar "
                "um plano da Groq com maior capacidade. Acesse groq.com \n\n"
                "👉 **Os resultados encontrados continuam disponíveis na lateral.**"
            )

            return mensagem, fontes

        return conteudo, fontes

    except Exception as e:
        erro = str(e).lower()

        if "rate" in erro or "limit" in erro or "quota" in erro:
            mensagem = (
                "⚠️ **O Kim Painho encontrou os registros, mas atingiu um limite "
                "da Inteligência Artificial.**\n\n"
                "Se você estiver utilizando a **Groq na modalidade gratuita**, "
                "pode ter atingido um limite de uso ou processamento.\n\n"
                "🔄 Tente novamente em alguns instantes ou considere utilizar "
                "um plano da Groq com maior capacidade.\n\n"
                "👉 **Os resultados encontrados continuam disponíveis na lateral.**"
            )
        else:
            mensagem = (
                "⚠️ **Não foi possível gerar a resposta do Kim Painho.**\n\n"
                "A consulta ao acervo foi realizada, mas ocorreu um problema "
                "ao solicitar a resposta à Inteligência Artificial.\n\n"
                "🔄 Tente novamente em alguns instantes.\n\n"
                "👉 **Os resultados encontrados continuam disponíveis na lateral.**"
            )

        return mensagem, fontes
