"""Aba Acervos: criar, editar, definir padrão, excluir e glossário de nomes."""

import pandas as pd
import streamlit as st

from admin import catalogo, saude
from admin.telas import comum
from ingestao import glossario, parametros as P
from ingestao.armazenamento import Armazenamento


def _rotulo_modelo(nome):

    return f"{nome} ({P.MODELOS_EMBEDDING[nome]['dim']} dimensões)"


def _modelo_do_acervo(c):

    return c.get("embedding_model") or P.MODELO_PADRAO


def _contagem(colecao_id):

    try:
        if not comum.qdrant().collection_exists(collection_name=colecao_id):
            return None
        return comum.qdrant().count(collection_name=colecao_id, exact=True).count
    except Exception:
        return None


def _modelo_por_dimensao(colecao_id):

    try:
        dim = comum.qdrant().get_collection(collection_name=colecao_id).config.params.vectors.size
    except Exception:
        return P.MODELO_PADRAO

    return next((n for n, m in P.MODELOS_EMBEDDING.items() if m["dim"] == dim), P.MODELO_PADRAO)


# ------------------------------------------------------------
# LISTA
# ------------------------------------------------------------

def _lista():

    colecoes = catalogo.ler()

    for c in colecoes:

        pontos = _contagem(c["id"])

        with st.container(border=True):

            a, b = st.columns([4, 2])

            a.markdown(
                f"**{c['nome']}** {'⭐ padrão' if c.get('default') else ''}  \n"
                f"<small>`{c['id']}` · autor: {c.get('autor') or c['nome']} · "
                f"modelo: {_modelo_do_acervo(c)}</small>",
                unsafe_allow_html=True
            )

            if c.get("descricao"):
                a.caption(c["descricao"])

            b.metric(
                "Trechos indexados",
                comum.inteiro_br(pontos) if pontos is not None else "coleção não criada"
            )


# ------------------------------------------------------------
# CRIAR
# ------------------------------------------------------------

def _criar():

    with st.form("form_novo_acervo", clear_on_submit=True):

        nome = st.text_input("Nome do acervo", placeholder="ex.: Olavo de Carvalho", key="novo_nome")
        autor = st.text_input(
            "Autor ou fonte", placeholder="ex.: Olavo de Carvalho", key="novo_autor",
            help="Aparece nas respostas da IA. Se ficar vazio, usa o nome do acervo."
        )
        descricao = st.text_area("Descrição", height=80, key="novo_desc")

        col1, col2 = st.columns(2)

        identificador = col1.text_input(
            "ID técnico (opcional)", key="novo_id",
            help="Nome da coleção no Qdrant. Se ficar vazio, é gerado a partir do nome."
        )

        modelo = col2.selectbox(
            "Modelo de embedding",
            options=list(P.MODELOS_EMBEDDING),
            format_func=_rotulo_modelo,
            index=list(P.MODELOS_EMBEDDING).index(P.MODELO_PADRAO), key="novo_modelo",
            help="Não pode ser trocado depois: os vetores gravados dependem dele. "
                 "O bge-m3 entende melhor o português (execute `ollama pull bge-m3`)."
        )

        enviado = st.form_submit_button("Criar acervo", type="primary")

    if not enviado:
        return

    colecao_id = (identificador or "").strip() or catalogo.sugerir_id(nome)

    try:
        novo = catalogo.criar(colecao_id, nome, descricao, autor, modelo)
    except ValueError as e:
        st.error(str(e))
        return

    try:
        armazenamento = Armazenamento(comum.qdrant(), colecao_id)
        armazenamento.garantir_colecao(P.MODELOS_EMBEDDING[modelo]["dim"])
        armazenamento.garantir_indices()
    except Exception as e:
        st.warning(
            f"Acervo cadastrado, mas não consegui criar a coleção no Qdrant agora ({e}). "
            "Ela será criada na primeira ingestão."
        )
    else:
        st.success(f"Acervo **{novo['nome']}** criado.")

    st.rerun()


def _orfas():

    try:
        sobras = catalogo.orfas(saude.nomes_no_qdrant(comum.qdrant()))
    except Exception:
        return

    if not sobras:
        return

    st.markdown("#### Coleções no Qdrant fora do catálogo")
    st.caption("Existem no banco mas não aparecem nas listas. Cadastre ou apague.")

    for nome_colecao in sobras:

        with st.expander(f"`{nome_colecao}`"):

            pontos = _contagem(nome_colecao)
            st.write(f"{comum.inteiro_br(pontos or 0)} trechos.")

            nome = st.text_input("Nome", value=nome_colecao, key=f"orfa_nome_{nome_colecao}")
            modelo = _modelo_por_dimensao(nome_colecao)

            a, b = st.columns(2)

            if a.button("Cadastrar no catálogo", key=f"orfa_cad_{nome_colecao}"):
                try:
                    catalogo.criar(nome_colecao, nome, embedding_model=modelo, existente=True)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

            if pontos == 0 and b.button("Apagar coleção vazia", key=f"orfa_del_{nome_colecao}"):
                comum.qdrant().delete_collection(collection_name=nome_colecao)
                st.rerun()


# ------------------------------------------------------------
# EDITAR, PADRÃO, EXCLUIR
# ------------------------------------------------------------

def _gerenciar():

    colecoes = catalogo.ler()

    if not colecoes:
        return

    indice = st.selectbox(
        "Acervo", options=range(len(colecoes)),
        format_func=lambda i: colecoes[i]["nome"], key="gerenciar_acervo"
    )

    c = colecoes[indice]

    with st.form(f"form_editar_{c['id']}"):

        nome = st.text_input("Nome", value=c["nome"], key=f"ed_nome_{c['id']}")
        autor = st.text_input("Autor ou fonte", value=c.get("autor") or "", key=f"ed_autor_{c['id']}")
        descricao = st.text_area("Descrição", value=c.get("descricao") or "", height=80, key=f"ed_desc_{c['id']}")

        st.caption(
            f"ID `{c['id']}` e modelo `{_modelo_do_acervo(c)}` não podem ser alterados."
        )

        if st.form_submit_button("Salvar alterações"):
            try:
                catalogo.editar(c["id"], nome=nome, descricao=descricao, autor=autor)
                st.success("Salvo.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    if c.get("default"):
        st.info("⭐ Este é o acervo padrão (o que abre selecionado na busca).")
    elif st.button("⭐ Tornar este o acervo padrão", key=f"padrao_{c['id']}"):
        catalogo.definir_padrao(c["id"])
        st.rerun()

    with st.expander("🗑️ Excluir acervo"):

        if c.get("default"):
            st.error("O acervo padrão não pode ser excluído. Defina outro como padrão antes.")
            return

        pontos = _contagem(c["id"])

        st.warning(
            f"Isto apaga a coleção `{c['id']}` do Qdrant"
            + (f" ({comum.inteiro_br(pontos)} trechos)" if pontos else "")
            + " e tira o acervo do catálogo. Não dá para desfazer. "
              "Faça um backup antes, na aba Backup."
        )

        confirmacao = st.text_input(f"Para confirmar, digite o ID: {c['id']}", key=f"conf_del_{c['id']}")

        if st.button("Excluir permanentemente", type="primary",
                     disabled=confirmacao.strip() != c["id"], key=f"del_{c['id']}"):

            try:
                if comum.qdrant().collection_exists(collection_name=c["id"]):
                    comum.qdrant().delete_collection(collection_name=c["id"])

                if comum.qdrant().collection_exists(collection_name=c["id"]):
                    st.error("O Qdrant não confirmou a exclusão. O catálogo não foi alterado.")
                    return

                catalogo.remover(c["id"])
                st.rerun()

            except Exception as e:
                st.error(f"Não foi possível excluir: {e}")


# ------------------------------------------------------------
# GLOSSÁRIO
# ------------------------------------------------------------

def _glossario():

    colecoes = catalogo.ler()

    if not colecoes:
        return

    st.caption(
        "Nomes próprios que o Whisper e as legendas automáticas costumam errar. "
        "**Nomes** viram dica para o Whisper. **Correções** trocam uma grafia errada pela certa "
        "em qualquer transcrição nova. Para aplicar a documentos já indexados, reingira-os."
    )

    indice = st.selectbox(
        "Acervo do glossário", options=range(len(colecoes)),
        format_func=lambda i: colecoes[i]["nome"], key="glossario_acervo"
    )

    colecao_id = colecoes[indice]["id"]
    atual = glossario.carregar(colecao_id)

    nomes = st.text_area(
        "Nomes (um por linha)", value="\n".join(atual["nomes"]), height=140,
        key=f"gl_nomes_{colecao_id}", placeholder="Olavo de Carvalho\nKim Paim"
    )

    tabela = pd.DataFrame(
        [{"Grafia errada": k, "Grafia certa": v} for k, v in atual["correcoes"].items()]
        or [{"Grafia errada": "", "Grafia certa": ""}]
    )

    editada = st.data_editor(
        tabela, num_rows="dynamic", use_container_width=True, hide_index=True,
        key=f"gl_corr_{colecao_id}"
    )

    if st.button("Salvar glossário", key=f"gl_salvar_{colecao_id}"):

        correcoes = {
            str(l["Grafia errada"]).strip(): str(l["Grafia certa"]).strip()
            for _, l in editada.iterrows()
            if str(l["Grafia errada"]).strip() and str(l["Grafia certa"]).strip()
            and str(l["Grafia errada"]) != "None" and str(l["Grafia certa"]) != "None"
        }

        glossario.salvar(colecao_id, [n for n in nomes.splitlines()], correcoes)
        st.success("Glossário salvo.")


# ------------------------------------------------------------
# PÁGINAS DO MENU
# ------------------------------------------------------------

def pagina_lista():

    _lista()
    _orfas()


def pagina_novo():

    _criar()


def pagina_gerenciar():

    _gerenciar()


def pagina_glossario():

    _glossario()
