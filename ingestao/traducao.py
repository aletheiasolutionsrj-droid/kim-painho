"""Tradução do título de vídeos para o português, pela Groq (a mesma chave do resto do sistema)."""

PROMPT_SISTEMA = (
    "Você traduz títulos de vídeos para o português do Brasil. Responda SOMENTE com o título traduzido, "
    "em uma linha, sem aspas e sem comentários. Mantenha nomes próprios, marcas e siglas como no original."
)


def _limpar(texto):

    linha = (texto or "").strip().splitlines()[0].strip() if (texto or "").strip() else ""

    return linha.strip().strip('"“”\'«»').strip()


def traduzir_titulo(titulo, cliente=None, modelo=None):
    """
    Devolve o título em português. Se algo falhar (chave, limite de uso, rede) ou a resposta
    vier estranha, devolve o título original: a tradução nunca impede a ingestão do vídeo.
    """

    titulo = (titulo or "").strip()

    if not titulo:
        return titulo

    if cliente is None:
        from clientes import client_groq as cliente
    if modelo is None:
        from config import MODELO_LLM as modelo

    try:
        resposta = cliente.chat.completions.create(
            model=modelo,
            temperature=0,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": titulo},
            ],
        )
        traduzido = _limpar(resposta.choices[0].message.content)
    except Exception:
        return titulo

    # resposta vazia ou muito maior que o original: provavelmente não é só a tradução
    if not traduzido or len(traduzido) > max(3 * len(titulo), 80):
        return titulo

    return traduzido
