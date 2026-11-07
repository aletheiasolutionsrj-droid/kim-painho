import streamlit as st

st.set_page_config(layout="wide", page_title="Administração · Kim Painho", page_icon="🛠️")

from admin import tarefas                                           # noqa: E402
from admin.telas import (                                           # noqa: E402
    acervos, adicionar, atualizacao_ui, backup_ui, comum, documentos, menu, saude_ui, tarefas_ui
)

comum.exigir_senha()

from admin import atualizacoes                                      # noqa: E402

atualizacoes.verificar_na_sessao(st.session_state)

MENU = [
    ("📚 Acervos", [
        ("Acervos cadastrados", acervos.pagina_lista),
        ("Novo acervo", acervos.pagina_novo),
        ("Editar ou excluir", acervos.pagina_gerenciar),
        ("Glossário de nomes", acervos.pagina_glossario),
    ]),
    ("➕ Adicionar conteúdo", [
        ("Vídeos do YouTube", adicionar.pagina_youtube),
        ("PDFs", adicionar.pagina_pdf),
        ("Podcast e áudio", adicionar.pagina_podcast),
        ("Vídeos sem legenda", adicionar.pagina_sem_legenda),
    ]),
    ("🔄 Atualização automática", atualizacao_ui.render),
    ("🗂️ Documentos", documentos.render),
    ("⚙️ Tarefas", tarefas_ui.render),
    ("💾 Backup", backup_ui.pagina_backup),
    ("↩️ Restore", backup_ui.pagina_restore),
    ("❤️ Saúde e índices", saude_ui.render),
]

with st.sidebar:
    st.markdown(menu.ESTILO_BOTAO_VOLTAR, unsafe_allow_html=True)

    if st.button("Voltar ao Oráculo", icon="🔮", key="voltar_oraculo", use_container_width=True):
        st.switch_page("app.py")

    st.divider()
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)   # afasta o menu do link

ativas = tarefas.contar_ativas()

grupo, item, pagina = menu.escolher(MENU, {"⚙️ Tarefas": ativas} if ativas else None)

st.title(f"🛠️ {item or grupo}")
st.caption("Administração do acervo" + (f" · {grupo}" if item else ""))

pagina()
