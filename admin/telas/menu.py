"""Menu em árvore na barra lateral da página de Administração."""

import streamlit as st

CHAVE = "pagina_admin"

# Botões da barra lateral com aparência de links: alinhados à esquerda e juntinhos
# (o padrão do Streamlit centraliza o texto e deixa espaço demais entre eles).
ESTILO = """
<style>
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.1rem; }
section[data-testid="stSidebar"] .stButton,
section[data-testid="stSidebar"] .stButton > div { width: 100%; margin: 0; }
section[data-testid="stSidebar"] .stButton button {
    width: 100%; min-height: 0; padding: 0.2rem 0.6rem;
    border: none; box-shadow: none; background: transparent;
    display: flex; justify-content: flex-start; text-align: left;
}
/* o texto fica dentro de divs/parágrafos que também centralizam */
section[data-testid="stSidebar"] .stButton button > div,
section[data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] .stButton button p {
    width: 100%; margin: 0; justify-content: flex-start; text-align: left !important;
}
section[data-testid="stSidebar"] .stButton button p { font-size: 0.95rem; }
section[data-testid="stSidebar"] .stButton button:hover { background: rgba(128,128,128,0.15); }
/* página atual */
section[data-testid="stSidebar"] .stButton button[kind="primary"],
section[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"] {
    background: rgba(128,128,128,0.22);
}
section[data-testid="stSidebar"] .stButton button[kind="primary"] p,
section[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"] p {
    color: inherit;
}
section[data-testid="stSidebar"] hr { margin: 0.4rem 0; }
</style>
"""

# O CSS acima deixa todo botão da barra lateral com cara de link. O "Voltar" é um botão de verdade.
ESTILO_BOTAO_VOLTAR = """
<style>
section[data-testid="stSidebar"] .st-key-voltar_oraculo .stButton button {
    border: 1px solid rgba(128,128,128,0.55); background: rgba(128,128,128,0.10);
    justify-content: center; padding: 0.45rem 0.8rem;
}
section[data-testid="stSidebar"] .st-key-voltar_oraculo .stButton button > div,
section[data-testid="stSidebar"] .st-key-voltar_oraculo .stButton button p {
    justify-content: center; text-align: center !important; width: auto;
}
section[data-testid="stSidebar"] .st-key-voltar_oraculo .stButton button:hover {
    background: rgba(128,128,128,0.25); border-color: rgba(128,128,128,0.9);
}
</style>
"""

RECUO = " " * 6          # o "tab" dos subitens
ESPACO_ENTRE_GRUPOS = "<div style='height:0.7rem'></div>"


def escolher(menu, rotulos_extras=None):
    """
    menu: [(grupo, [(item, função), ...]) ou (grupo, função)]
    Desenha o menu na barra lateral e devolve (grupo, item, função) da página atual.
    Clicar no nome de um grupo abre o primeiro item dele.
    rotulos_extras: {grupo: texto} acrescentado ao nome do grupo (ex.: contador de tarefas).
    """

    extras = rotulos_extras or {}

    paginas = {}

    for grupo, conteudo in menu:
        if callable(conteudo):
            paginas[(grupo, None)] = conteudo
        else:
            for item, funcao in conteudo:
                paginas[(grupo, item)] = funcao

    atual = st.session_state.get(CHAVE)

    if atual not in paginas:
        atual = next(iter(paginas))
        st.session_state[CHAVE] = atual

    escolhida = atual

    with st.sidebar:

        st.markdown(ESTILO, unsafe_allow_html=True)

        for posicao, (grupo, conteudo) in enumerate(menu):

            if posicao:
                st.markdown(ESPACO_ENTRE_GRUPOS, unsafe_allow_html=True)

            rotulo = grupo + (f" ({extras[grupo]})" if extras.get(grupo) else "")

            if callable(conteudo):

                if st.button(f"**{rotulo}**", key=f"menu_{grupo}",
                             type="primary" if atual == (grupo, None) else "secondary"):
                    escolhida = (grupo, None)

                continue

            if st.button(f"**{rotulo}**", key=f"menugrupo_{grupo}", type="secondary"):
                escolhida = (grupo, conteudo[0][0])

            for item, _ in conteudo:

                if st.button(f"{RECUO}{item}", key=f"menu_{grupo}_{item}",
                             type="primary" if atual == (grupo, item) else "secondary"):
                    escolhida = (grupo, item)

    if escolhida != atual:
        st.session_state[CHAVE] = escolhida
        st.rerun()

    return escolhida[0], escolhida[1], paginas[escolhida]
