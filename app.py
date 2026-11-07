import streamlit as st
import html
from clientes import client_qdrant

import httpx
from urllib.parse import quote

from config import (
    salvar_colecoes,
    recarregar_colecoes,
    QDRANT_HOST, 
    QDRANT_PORT
)

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    FilterSelector,
    VectorParams,
    Distance,
    PointStruct
)

from ui import (
    aplicar_estilo_sidebar,
    renderizar_header,
    exibir_titulo_com_tooltip,
    exibir_relevancia_e_data,
    exibir_localizacao_pdf,
    exibir_fonte
)

from busca import (
    buscar_contexto_qdrant,
    garantir_indice_texto_bruto
)

from geracao import gerar_resposta_groq
from reranking import selecionar_resultados

COLECOES, COLECAO_DEFAULT = recarregar_colecoes()


# Mapa global: ID da coleção -> nome amigável
ids_catalogo = {
    c["id"]: c["nome"]
    for c in COLECOES
}

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(layout="wide", page_title="KIM PAINHO", page_icon="🔮")

aplicar_estilo_sidebar("logo.png")

# ============================================================
# ATUALIZAÇÃO AUTOMÁTICA DOS CANAIS (uma vez por dia, ao abrir o site)
# ============================================================

try:
    from admin import atualizacoes as _atualizacoes
    _atualizacoes.verificar_na_sessao(st.session_state)
except Exception:
    pass

# ============================================================
# GARANTE INFRAESTRUTURA DO QDRANT
# ============================================================

# garantir_indice_texto_bruto()

# ============================================================
# ESTADO DA RESPOSTA DA IA
# ============================================================

if "resposta_ia" not in st.session_state:
    st.session_state["resposta_ia"] = ""
    if "fontes_carregadas" not in st.session_state:
        st.session_state["fontes_carregadas"] = []

    if "fontes_adicionais" not in st.session_state:
        st.session_state["fontes_adicionais"] = []

    if "mostrar_fontes_adicionais" not in st.session_state:
        st.session_state["mostrar_fontes_adicionais"] = False

# ============================================================
# MODAL PARA VISUALIZAÇÃO DO CHUNK
# ============================================================


def ao_fechar_modal():
    st.session_state["modal_aberto"] = None

@st.dialog("👁️ Conteúdo do registro")
def visualizar_chunk(texto):
    st.markdown("### 📜 Texto do chunk")

    if texto:
        st.text_area(
            "Conteúdo recuperado do acervo",
            value=texto,
            height=400,
            label_visibility="collapsed"
        )
    else:
        st.info("Este registro não possui o campo `text`.")

# --- DESENHO DA INTERFACE (FRONTEND) ---

# Barra Lateral Esquerda
with st.sidebar:


    st.header("⚙️ Poderes do Oráculo")
    
    # Filtro de tipo de mídia
    filtro_midia = st.radio(
        "De onde o Kim Painho deve consultar?",
        ["Todo o acervo", "Apenas Vídeos", "Apenas PDFs", "Apenas Áudio/Podcast"],
        index=0
    )

    st.divider()

    # Barra Lateral Esquerda
    with st.sidebar:

        # ============================================================
        # SELEÇÃO DO ACERVO
        # ============================================================

        ids_colecoes = [colecao["id"] for colecao in COLECOES]

        indice_default = ids_colecoes.index(
            COLECAO_DEFAULT["id"]
        )

        colecao_selecionada_id = st.selectbox(
            "📚 Acervo",
            options=ids_colecoes,
            index=indice_default,
            format_func=lambda colecao_id: next(
                colecao["nome"]
                for colecao in COLECOES
                if colecao["id"] == colecao_id
            )
        )

        st.session_state["colecao_selecionada"] = colecao_selecionada_id

        colecao_atual = next(
            c for c in COLECOES if c["id"] == colecao_selecionada_id
        )

        # ============================================================
        # GARANTE INFRAESTRUTURA DO ACERVO SELECIONADO
        # ============================================================

        garantir_indice_texto_bruto(colecao_selecionada_id)

        # ============================================================
        # PODERES DO ORÁCULO
        # ============================================================

        st.header("⚙️ Poderes do Oráculo")

        st.divider()
        
        # Seletor de criatividade (Temperatura da IA)
        temperatura_ia = st.slider(
            "🔮 Grau de vidência",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.1,
            help="Quanto maior, mais criativa é a resposta. Quanto menor, mais o Kim Painho se limita ao que encontrou no acervo."
        )

        st.divider()

        # Ignorar os minutos iniciais dos vídeos durante a consulta
        ignorar_inicio = st.checkbox(
            "⏩ Ignorar início dos vídeos",
            value=False,
            help="Quando ativado, trechos dos primeiros minutos dos vídeos são excluídos da consulta. O conteúdo continua armazenado no Qdrant."
        )

        minutos_ignorar = st.number_input(
            "Minutos a ignorar",
            min_value=0,
            max_value=60,
            value=3,
            step=1,
            disabled=not ignorar_inicio,
            help="Quantidade de minutos iniciais dos vídeos que não serão considerados na consulta."
        )

        st.divider()

        # st.subheader("🔎 Recuperação")

        limite_busca = st.selectbox(
            "Resultados da busca",
            options=[10, 20, 30, 50],
            index=1,
            help="Quantidade de candidatos recuperados pelo Qdrant e avaliados pelo reranker."
        )

        limite_llm = st.selectbox(
            "Contexto para IA",
            options=[5, 10, 15, 20],
            index=1,
            help="Quantidade de trechos mais relevantes enviados para a IA gerar a resposta."
        )
        
        st.divider()
        st.subheader("📚 Expandir os poderes")

    # A ingestão e a manutenção do acervo ficam em página própria.
    try:
        from admin import tarefas as _tarefas
        _ativas = _tarefas.contar_ativas()
    except Exception:
        _ativas = 0

    if st.button(
        "Administração do acervo" + (f" ({_ativas} em andamento)" if _ativas else ""),
        icon="🛠️",
        key="ir_administracao",
        use_container_width=True
    ):
        st.switch_page("pages/1_Administracao.py")

# --- DIVISÃO DA TELA PRINCIPAL (MAIN) ---

# Header Principal
renderizar_header()

# Dividimos a área central em duas colunas: Esquerda (Chat e Resposta) e Direita (Fontes)
col_principal, col_fontes = st.columns([0.7, 0.3])

with col_principal:

    # ========================================================
    # ÁREA SUPERIOR: PERGUNTA
    # ========================================================

    with st.form("form_consulta", clear_on_submit=False):

        col_txt, col_btn = st.columns([0.80, 0.20])

        with col_txt:
            pergunta_usuario = st.text_input(
                "O que os astros tecnológicos revelam?",
                placeholder="Faça sua pergunta... os astros já estão se alinhando.",
                label_visibility="collapsed"
            )

        with col_btn:
            botao_perguntar = st.form_submit_button(
                "🔮 Consultar",
                use_container_width=True
            )

        # ========================================================
        # MODO DE BUSCA
        # ========================================================

        st.markdown(
            """
            <div class="modo-busca">
            """,
            unsafe_allow_html=True
        )

        modo_busca = st.radio(
            "🔎 Buscar por: ",
            ["Contexto", "Expressão exata", "Ambos"],
            index=0,
            horizontal=True
        )

        st.markdown(
            """
            </div>
            """,
            unsafe_allow_html=True
        )

    # ========================================================
    # CONSULTA AO ORÁCULO
    # ========================================================

    if botao_perguntar and pergunta_usuario:

        with st.spinner(
            "🔮 Consultando os astros e perturbando a dimensão "
            "do Qdrant, aquele que tudo guarda..."
        ):

            # 1. Busca no Qdrant
            pontos_encontrados = buscar_contexto_qdrant(
                pergunta_usuario,
                filtro_midia,
                limite_busca,
                colecao_selecionada_id,
                modo_busca,
                ignorar_segundos=(
                    int(minutos_ignorar * 60) if ignorar_inicio else 0
                )
            )

            if pontos_encontrados:

                # 2. Rerank
                if modo_busca == "Expressão exata":
                    # Ocorrências literais não passam pelo reranker.
                    pontos_selecionados = pontos_encontrados
                else:
                    pontos_selecionados = selecionar_resultados(
                        pergunta_usuario,
                        pontos_encontrados
                    )

                # 3. Fontes que não serão enviadas para a IA
                fontes_adicionais = [
                    ponto.payload
                    for ponto in pontos_selecionados[limite_llm:]
                ]

                st.session_state["fontes_adicionais"] = fontes_adicionais

                # 4. Gera resposta na Groq
                resposta_ia, lista_fontes = gerar_resposta_groq(
                    pergunta_usuario,
                    pontos_selecionados,
                    temperatura_ia,
                    limite_llm,
                    colecao_atual
                )

                # 5. Guarda tudo na sessão
                st.session_state["resposta_ia"] = resposta_ia
                st.session_state["fontes_carregadas"] = lista_fontes
                st.session_state["fontes_adicionais"] = fontes_adicionais

            else:

                st.session_state["resposta_ia"] = ""
                st.session_state["fontes_carregadas"] = []
                st.session_state["fontes_adicionais"] = []

                st.warning(
                    "🔮 O Kim Painho não encontrou nada no acervo. "
                    "Talvez os astros estejam de folga."
                )

    # ========================================================
    # EXIBIÇÃO PERSISTENTE DA RESPOSTA
    # ========================================================

    if st.session_state.get("resposta_ia"):

        st.markdown("### 🔮 Revelação do Kim Painho")

        st.write(
            st.session_state["resposta_ia"]
        )


# Preenchimento da Coluna da Direita
with col_fontes:

    # ============================================================
    # FONTES ENVIADAS PARA A IA
    # ============================================================

    if "fontes_carregadas" in st.session_state and st.session_state["fontes_carregadas"]:

        for numero, fonte in enumerate(st.session_state["fontes_carregadas"], start=1):
            exibir_fonte(fonte, f"Fonte {numero}:")

    else:

        st.info(
            "Faça uma pergunta ao poderoso Kim Painho. "
            "Os registros encontrados aparecerão aqui."
        )


    # ============================================================
    # OUTROS RESULTADOS ENCONTRADOS
    # ============================================================

    fontes_adicionais = st.session_state.get(
        "fontes_adicionais",
        []
    )

    if fontes_adicionais:

        # st.divider()

        if st.button(
            f"🔎 Outros resultados encontrados ({len(fontes_adicionais)})",
            use_container_width=True
        ):

            st.session_state["mostrar_fontes_adicionais"] = not st.session_state.get(
                "mostrar_fontes_adicionais",
                False
            )


    # ============================================================
    # EXIBIÇÃO DOS RESULTADOS ADICIONAIS
    # ============================================================

    if (
        fontes_adicionais
        and st.session_state.get("mostrar_fontes_adicionais", False)
    ):

        st.markdown("##### Dados não enviados para a IA")

        for numero, fonte in enumerate(fontes_adicionais, start=1):
            exibir_fonte(fonte, f"Outro resultado {numero}:")
