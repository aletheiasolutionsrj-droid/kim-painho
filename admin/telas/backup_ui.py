"""Aba Backup e restauração."""

import streamlit as st

from admin import catalogo, saude
from admin.telas import comum
from admin.tarefas import RAIZ

PASTA_BACKUPS = RAIZ / "backups" / "acervos"


def _backup():

    st.write(
        "Gera um arquivo `.snapshot` do acervo, que pode ser restaurado em outra instalação. "
        "Ele guarda os trechos de texto e os vetores."
    )

    st.warning(
        "Se o acervo contém conteúdo pago (como o Atlas Brasileiro), o backup também o contém. "
        "Não distribua esse arquivo: mantenha o conteúdo pago em um acervo separado."
    )

    acervo = comum.escolher_acervo("backup_acervo", "Acervo para backup")

    if st.button("💾 Criar backup", type="primary", key="backup_go"):
        comum.enfileirar("backup", f"Backup: {acervo['nome']}", {"colecao_id": acervo["id"]}, acervo["id"])
        comum.aviso_enfileirado()

    arquivos = sorted(PASTA_BACKUPS.glob("*.snapshot"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if PASTA_BACKUPS.exists() else []

    if arquivos:
        st.markdown("**Backups existentes** (pasta `backups/acervos` do projeto)")
        for p in arquivos[:30]:
            st.markdown(f"- `{p.name}` — {comum.tamanho_legivel(p.stat().st_size)}")


def _restaurar():

    st.write("A restauração só é feita em um acervo **vazio**. Crie o acervo na aba Acervos antes.")

    vazios = []

    try:
        existentes = set(saude.nomes_no_qdrant(comum.qdrant()))

        for c in catalogo.ler():
            if c["id"] in existentes and saude.esta_vazia(comum.qdrant(), c["id"]):
                vazios.append(c)
    except Exception as e:
        st.error(f"Não consegui consultar o Qdrant: {e}")
        return

    if not vazios:
        st.info("Não há acervos vazios disponíveis.")
        return

    indice = st.selectbox(
        "Acervo de destino (somente vazios)", range(len(vazios)),
        format_func=lambda i: f"{vazios[i]['nome']} · {vazios[i]['id']}", key="restore_destino"
    )

    arquivo = st.file_uploader("Arquivo de backup (.snapshot)", type=["snapshot"], key="restore_arq")

    confirmado = st.checkbox("Confirmo a restauração no acervo selecionado.", key="restore_conf")

    if st.button("↩️ Restaurar", type="primary", key="restore_go", disabled=arquivo is None or not confirmado):

        caminho = comum.salvar_upload(arquivo)

        comum.enfileirar("restaurar_snapshot", f"Restaurar em {vazios[indice]['nome']}",
                         {"colecao_id": vazios[indice]["id"], "caminho": str(caminho), "apagar_origem": True},
                         vazios[indice]["id"])
        comum.aviso_enfileirado()


def pagina_backup():

    _backup()


def pagina_restore():

    _restaurar()
