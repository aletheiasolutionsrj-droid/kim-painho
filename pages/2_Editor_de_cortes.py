import streamlit as st

st.set_page_config(layout="wide", page_title="Editor de cortes · Kim Painho", page_icon="✂️")

from admin.telas import comum, cortes_ui                            # noqa: E402

comum.exigir_senha()

with st.sidebar:

    if st.button("Voltar ao Oráculo", icon="🔮", key="voltar_oraculo_cortes", use_container_width=True):
        st.switch_page("app.py")

    if st.button("Administração do acervo", icon="🛠️", key="ir_admin_cortes", use_container_width=True):
        st.switch_page("pages/1_Administracao.py")

st.title("✂️ Editor de cortes")
st.caption(
    "Marque o início e o fim de um trecho no vídeo, baixe a legenda dele em .srt e corte o vídeo. "
    "O player abre no ponto exato em que o assunto foi falado."
)

cortes_ui.render()
