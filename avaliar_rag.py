import os
import ollama
from qdrant_client import QdrantClient
from groq import Groq
import time


# ============================================================
# CONFIGURAÇÕES
# ============================================================

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")

NOME_COLECAO = "acervo_kim_painho"

MODELO_EMBEDDING = "nomic-embed-text"

MODELO_LLM = "openai/gpt-oss-120b"

# Quantidade de chunks recuperados para cada pergunta.
# Mantemos 20 nesta fase para analisar o comportamento da busca.
LIMITE_RESULTADOS = 10


# ============================================================
# PERGUNTAS DO BENCHMARK
# ============================================================


PERGUNTAS_1 = [

    "Qual é a relação entre Deltan Dallagnol, o NOVO, MBL, RenovaBR, Livres e empresários?",
    
    "Como o RenovaBR selecionava e formava candidatos políticos?",
    
    "Qual é a relação entre o MBL e Pedro d'Eyrot?",
    
    "Como o dinheiro é usado para rastrear as relações envolvendo o MBL?",

    "O que Kim Paim argumenta sobre Romeu Zema e as eleições de 2026?",
    
    "Quem é Romeu Zema segundo a análise apresentada no vídeo?",
    
    "O que significa o conceito de empilhamento discutido por Kim Paim?",
    
    "Quais são as relações entre Flávio Bolsonaro e os acontecimentos discutidos no vídeo sobre empilhamento?",
    
    "Qual é a tese de Kim Paim sobre a origem dos chamados 'permitidos'?",
    
    "Qual é a diferença entre a direita liberal e a direita soberanista segundo a tese apresentada?",
    
    "Qual foi o papel de Enéas na ruptura política descrita por Kim Paim?",
    
    "Qual foi o papel de Olavo de Carvalho nessa ruptura?"
]

PERGUNTAS_2 = [

    "O que Kim Paim comenta sobre Flávio Bolsonaro no início do vídeo sobre o EIXO?",
    
    "O que Kim Paim menciona sobre Dom Pedro I e Bolsonaro?",
    
    "O que Kim Paim comenta sobre Carlos Bolsonaro e Romeu Zema?",
    
    "O que Kim Paim menciona sobre Michelle Bolsonaro e a eleição de 2022?",
    
    "O que Kim Paim fala sobre a candidatura de Flávio Bolsonaro?",
    
    "O que Kim Paim comenta sobre Jair Bolsonaro e a candidatura de Flávio?",
    
    "O que Kim Paim menciona sobre Romeu Zema no começo do vídeo?",
    
    "O que Kim Paim fala sobre o caso Ramagem?",
]

PERGUNTAS_3 = [

    "Quem era sócio de Pedro d'Eyrot segundo o vídeo sobre o MBL?",
    
    "Qual era a relação de Afonso com o MBL mencionada no vídeo?",
    
    "Quem foi citado como responsável pelo processo de seleção do RenovaBR?",
    
    "Qual era a quantidade de candidatos selecionados pelo RenovaBR para as eleições municipais?",
    
    "Que tipo de teste de posicionamento político era utilizado pelo RenovaBR?",
    
    "Como o RenovaBR definia extremismo no processo de seleção?",
    
    "Quais pessoas foram mencionadas como integrantes ou relacionadas à CPI das Fake News?",
    
    "Qual é a relação mencionada entre o RenovaBR, Novo, Livres e Rede?",
    
    "Que relação empresarial envolvendo integrantes do MBL é discutida?",
]

PERGUNTAS_4 = [

    "O que Kim Paim entende por direita permitida?",
    
    "O que diferencia uma direita liberal de uma direita soberanista?",
    
    "Por que Kim Paim considera que existe uma ruptura dentro da direita?",
    
    "Como o conceito de globalismo aparece na tese sobre Olavo?",
    
    "Como a soberania nacional se relaciona com a tese apresentada no vídeo sobre o EIXO?",
    
    "Qual é a relação entre nacionalismo econômico e soberanismo segundo o vídeo?",
    
    "Como Olavo de Carvalho teria influenciado o debate político e cultural?",
    
    "Como Enéas teria contribuído para colocar o soberanismo no debate eleitoral?",
    
    "Qual é a tese apresentada sobre os critérios que determinam quem é politicamente aceito?",
]

PERGUNTAS_5 = [

    "O que aconteceu com a candidatura de Flávio Bolsonaro e qual foi a reação de Michelle Bolsonaro?",
    
    "Como a eleição de 2022 é utilizada para interpretar os acontecimentos envolvendo Michelle Bolsonaro?",
    
    "Qual é a relação entre Flávio Bolsonaro e Silas mencionada na análise?",
    
    "O que aconteceu entre Flávio e Silas depois do evento na Paulista?",
    
    "Qual era a posição de Moro em relação ao Ceará e ao Girão?",
    
    "Como Michelle Bolsonaro aparece na discussão sobre Tarcísio?",
    
    "Quais acontecimentos anteriores são usados para analisar a candidatura de Flávio Bolsonaro?",
    
    "Como Kim Paim relaciona acontecimentos de 2025 com a situação política atual de Flávio Bolsonaro?",
]

PERGUNTAS_6 = [

    "O que Kim Paim fala sobre frame e frames por segundo?",
    
    "O que Kim Paim comenta sobre o caso Ramagem?",
    
    "O que Kim Paim menciona sobre Carlos Bolsonaro?",
    
    "O que Kim Paim comenta sobre Luciano Huck?",
    
    "O que Kim Paim menciona sobre a CPI das Fake News?",
    
    "O que Kim Paim fala sobre Moro?",
    
    "O que Kim Paim comenta sobre Vargas, Jango e desenvolvimentismo?",
]

PERGUNTAS = [

    

    "Como a ideia de direita permitida é explicada através da história política brasileira?",
    
    "Qual é a relação entre nacionalismo econômico, soberania e crítica ao globalismo?",
    
    "Como o passado político de Michelle Bolsonaro é utilizado para interpretar acontecimentos atuais?",
    
    "Que acontecimentos de 2022 são usados para analisar a situação política atual de Michelle Bolsonaro?",
    
    "Qual é a relação entre RenovaBR e a formação de candidatos políticos?",
    
    "Como o processo de seleção do RenovaBR procurava identificar extremistas?",
    
    "Qual é a cadeia de relações apresentada entre NOVO, MBL, RenovaBR, Livres e empresários?",
    
    "Como Kim Paim utiliza dinheiro, sociedades empresariais e relações pessoais para investigar o MBL?"
]



# ============================================================
# CLIENTES
# ============================================================

client_qdrant = QdrantClient(
    host=QDRANT_HOST,
    port=6333
)

client_groq = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# ============================================================
# EMBEDDING
# ============================================================

def obter_embedding(texto):
    resposta = ollama.embeddings(
        model=MODELO_EMBEDDING,
        prompt=texto
    )

    return resposta["embedding"]


# ============================================================
# BUSCA SEMÂNTICA
# ============================================================

def buscar_contexto(pergunta, limite=LIMITE_RESULTADOS):

    vetor_pergunta = obter_embedding(pergunta)

    resultados = client_qdrant.query_points(
        collection_name=NOME_COLECAO,
        query=vetor_pergunta,
        limit=limite
    ).points

    return resultados


# ============================================================
# MONTAR CONTEXTO PARA O LLM
# ============================================================

def montar_contexto(resultados):

    blocos = []

    for i, resultado in enumerate(resultados, 1):

        payload = resultado.payload

        titulo = payload.get("titulo_video", "")
        data = payload.get("data_publicacao", "")
        timestamp = payload.get("timestamp_texto", "")
        texto = payload.get("texto_bruto", "")

        bloco = f"""
[FONTE {i}]
Título: {titulo}
Data: {data}
Timestamp: {timestamp}

Trecho:
{texto}
"""

        blocos.append(bloco)

    return "\n".join(blocos)


# ============================================================
# GERAR RESPOSTA
# ============================================================

def gerar_resposta(pergunta, contexto):

    prompt = f"""
Você é o assistente do projeto "Kim Painho", especializado
em responder perguntas com base no acervo de vídeos e
documentos disponibilizados para você.

Sua tarefa é responder à pergunta do usuário utilizando
EXCLUSIVAMENTE as informações presentes no CONTEXTO.

REGRAS:

1. Não invente informações.

2. Não utilize conhecimento externo ao contexto.

3. Se o contexto não for suficiente para responder,
   diga claramente que o acervo recuperado não contém
   informação suficiente.

4. Responda em português do Brasil.

5. Seja claro, objetivo e natural.

6. Quando possível, mencione os pontos principais encontrados
   nos diferentes trechos do contexto.

7. Não diga que você "pesquisou na internet".

8. Não trate o conteúdo recuperado como verdade absoluta.
   Atribua as afirmações ao conteúdo do acervo quando apropriado.

9. As transcrições podem conter erros de reconhecimento de voz,
   inclusive nomes próprios. Quando uma expressão aparentemente
   incorreta puder ser identificada pelo contexto, você pode
   indicar a interpretação provável, mas deixe claro que se trata
   de uma inferência e não de uma transcrição literal.

   Exemplo:
   Se a fonte disser "geral do al" e o contexto indicar Geraldo Alckmin,
   diga "o trecho transcrito como 'geral do al', aparentemente se
   referindo a Geraldo Alckmin".

10. Diferencie sempre o que está escrito literalmente na transcrição
    daquilo que é uma interpretação provável baseada no contexto.
    Não apresente uma correção da transcrição como se ela fosse
    literalmente o que foi dito.

PERGUNTA DO USUÁRIO:
{pergunta}

CONTEXTO RECUPERADO DO ACERVO:
{contexto}

Agora responda à pergunta do usuário.
"""

    resposta = client_groq.chat.completions.create(
        model=MODELO_LLM,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    return resposta.choices[0].message.content


# ============================================================
# ANÁLISE DOS RESULTADOS
# ============================================================

def analisar_busca(resultados):

    if not resultados:
        return {
            "melhor_score": 0,
            "videos_distintos": 0,
        }

    scores = [resultado.score for resultado in resultados]

    video_ids = set()

    for resultado in resultados:
        video_id = resultado.payload.get("video_id")

        if video_id:
            video_ids.add(video_id)

    return {
        "melhor_score": max(scores),
        "videos_distintos": len(video_ids),
    }


# ============================================================
# EXIBIR RESULTADOS
# ============================================================

def exibir_resultados(resultados):

    print("-" * 70)
    print("TOP RESULTADOS DA BUSCA")
    print("-" * 70)

    for i, resultado in enumerate(resultados, 1):

        payload = resultado.payload

        print(f"\n#{i}")
        print(f"Score:     {resultado.score:.4f}")
        print(f"Título:    {payload.get('titulo_video')}")
        print(f"Data:      {payload.get('data_publicacao')}")
        print(f"Timestamp: {payload.get('timestamp_texto')}")
        print(f"URL:       {payload.get('url_com_minuto')}")
        print(f"Texto:     {payload.get('texto_bruto')}")


# ============================================================
# EXECUÇÃO DO BENCHMARK
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("KIM PAINHO — BENCHMARK INICIAL DO RAG")
    print("=" * 70)

    print(f"\nColeção:       {NOME_COLECAO}")
    print(f"Embedding:     {MODELO_EMBEDDING}")
    print(f"LLM:           {MODELO_LLM}")
    print(f"Resultados:    {LIMITE_RESULTADOS}")
    print(f"Perguntas:     {len(PERGUNTAS)}")

    print("\nIniciando bateria de testes...")

    for numero, pergunta in enumerate(PERGUNTAS, 1):

        print("\n\n")
        print("=" * 70)
        print(f"TESTE {numero:02d} DE {len(PERGUNTAS):02d}")
        print("=" * 70)

        print(f"\nPERGUNTA:\n{pergunta}")

        try:

            print("\n🧠 Gerando embedding e buscando contexto...")

            resultados = buscar_contexto(
                pergunta,
                limite=LIMITE_RESULTADOS
            )

            if not resultados:

                print("\n❌ Nenhum resultado encontrado.")
                continue

            print(
                f"✅ {len(resultados)} chunks recuperados."
            )

            analise = analisar_busca(resultados)

            print(
                f"📊 Melhor score: {analise['melhor_score']:.4f}"
            )

            print(
                f"📚 Vídeos distintos: "
                f"{analise['videos_distintos']}"
            )

            contexto = montar_contexto(resultados)

            print("\n🤖 Enviando contexto para o LLM via Groq...")

            resposta = gerar_resposta(
                pergunta,
                contexto
            )

            print("\n")
            print("-" * 70)
            print("RESPOSTA DO KIM PAINHO")
            print("-" * 70)
            print(resposta)

            print("\n")

            exibir_resultados(resultados)

            time.sleep(960)

        except Exception as e:

            print("\n❌ ERRO DURANTE O TESTE")
            print(f"Tipo: {type(e).__name__}")
            print(f"Mensagem: {e}")

    print("\n\n")
    print("=" * 70)
    print("BENCHMARK CONCLUÍDO")
    print("=" * 70)
    print()
