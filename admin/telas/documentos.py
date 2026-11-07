"""Página Documentos: lista, filtros, edição de metadados e exclusão em lote."""

import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from admin import tarefas
from admin.telas import comum
from ingestao import arquivos
from ingestao.armazenamento import Armazenamento

TIPOS = {"video": "Vídeo", "pdf": "PDF", "podcast": "Podcast"}

PROCESSADO = ["Qualquer data", "Hoje", "Últimos 7 dias", "Sem data de processamento"]
ORDEM = ["Publicação (mais recente)", "Processamento (mais recente)", "Título (A–Z)"]

COLUNAS = ["Selecionar", "ID", "Tipo", "Título", "Publicação", "Data do arquivo", "Processado em", "Trechos"]
SO_LEITURA = [c for c in COLUNAS if c != "Selecionar"]


def _marca_das_tarefas():
    """Muda quando uma tarefa é criada, começa ou termina: sinal de que o acervo pode ter mudado."""

    return tuple((x["id"], x["status"]) for x in tarefas.listar(limite=200))


def _carregar(acervo, forcar=False):
    """
    Lê o resumo dos documentos do Qdrant e guarda na sessão (a leitura completa é demorada).
    A cópia é descartada sozinha quando uma tarefa começa ou termina; o botão Recarregar força.
    """

    chave = f"docs_{acervo['id']}"
    marca = _marca_das_tarefas()

    guardado = st.session_state.get(chave)

    if forcar or guardado is None or guardado["marca"] != marca:
        with st.spinner("Lendo os documentos do acervo..."):
            guardado = {
                "docs": Armazenamento(comum.qdrant(), acervo["id"]).resumo_documentos(),
                "marca": marca,
                "hora": datetime.now().strftime("%H:%M:%S"),
            }
            st.session_state[chave] = guardado

    st.session_state["docs_hora_leitura"] = guardado["hora"]

    return guardado["docs"]


def _processado_em(valor):
    """'2026-11-05T18:02:11' -> '2026-11-05 18:02'"""

    return (valor or "").replace("T", " ")[:16]


def _passa_filtro_processado(d, filtro, hoje):

    dia = (d.get("data_processamento") or "")[:10]

    if filtro == "Hoje":
        return dia == hoje.isoformat()

    if filtro == "Últimos 7 dias":
        return dia >= (hoje - timedelta(days=7)).isoformat() and bool(dia)

    if filtro == "Sem data de processamento":
        return not dia

    return True


def _tabela(docs, tipo, busca, so_sem_data, processado="Qualquer data", ordem=ORDEM[0],
            marcar_todos=False, hoje=None):

    hoje = hoje or date.today()
    linhas = []

    for doc_id, d in docs.items():

        if tipo != "Todos" and TIPOS.get(d["tipo_fonte"], d["tipo_fonte"]) != tipo:
            continue

        if so_sem_data and d["data_publicacao"]:
            continue

        if busca and busca.lower() not in f"{d['titulo'] or ''} {doc_id}".lower():
            continue

        if not _passa_filtro_processado(d, processado, hoje):
            continue

        linhas.append({
            "Selecionar": marcar_todos,
            "ID": doc_id,
            "Tipo": TIPOS.get(d["tipo_fonte"], d["tipo_fonte"] or "?"),
            "Título": d["titulo"] or "",
            "Publicação": d["data_publicacao"] or "",
            "Data do arquivo": d.get("data_arquivo") or "",
            "Processado em": _processado_em(d.get("data_processamento")),
            "Trechos": d["chunks"],
        })

    tabela = pd.DataFrame(linhas, columns=COLUNAS)

    if tabela.empty:
        return tabela

    if ordem == ORDEM[1]:
        tabela = tabela.sort_values(["Processado em", "ID"], ascending=[False, True])
    elif ordem == ORDEM[2]:
        tabela = tabela.sort_values("Título", key=lambda s: s.str.lower())
    else:
        tabela = tabela.sort_values(["Publicação", "ID"], ascending=[False, True])

    return tabela.reset_index(drop=True)


def _apagar(acervo, ids, docs):
    """Apaga os documentos e todos os seus trechos. Devolve (documentos, trechos)."""

    armazenamento = Armazenamento(comum.qdrant(), acervo["id"])
    barra = st.progress(0.0)

    armazenamento.apagar_documentos(ids, progresso=lambda feito, total: barra.progress(feito / total))

    for doc_id in ids:
        if (docs.get(doc_id) or {}).get("tipo_fonte") == "pdf":
            arquivos.caminho_copia(doc_id).unlink(missing_ok=True)

    return len(ids), sum((docs.get(i) or {}).get("chunks", 0) for i in ids)


def comum_data_ok(texto):

    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", texto.strip()))


def render():

    acervo = comum.escolher_acervo("docs_acervo")

    aviso = st.session_state.pop("docs_aviso", None)

    if aviso:
        st.success(aviso)

    try:
        docs = _carregar(acervo)
    except Exception as e:
        st.error(f"Não foi possível ler o acervo: {e}")
        return

    total_chunks = sum(d["chunks"] for d in docs.values())
    sem_data = sum(1 for d in docs.values() if d["tipo_fonte"] == "video" and not d["data_publicacao"])

    ativas = sum(1 for x in tarefas.listar(limite=200) if x["status"] in tarefas.STATUS_ATIVOS)

    st.caption(
        f"Lista lida do banco às {st.session_state.get('docs_hora_leitura')}. "
        + ("Há tarefas em andamento: ela será atualizada quando terminarem (ou clique em Recarregar do banco)."
           if ativas else "Ela se atualiza sozinha quando uma tarefa termina.")
    )

    a, b, c = st.columns(3)
    a.metric("Documentos", comum.inteiro_br(len(docs)))
    b.metric("Trechos", comum.inteiro_br(total_chunks))
    c.metric("Vídeos sem data", comum.inteiro_br(sem_data))

    f1, f2, f3 = st.columns([1, 2, 1], vertical_alignment="bottom")
    tipo = f1.selectbox("Tipo", ["Todos"] + list(TIPOS.values()), key="docs_tipo")
    busca = f2.text_input("Buscar no título ou ID", key="docs_busca")
    so_sem_data = f3.checkbox("Só sem data de publicação", key="docs_sem_data")

    g1, g2, g3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    processado = g1.selectbox("Processado", PROCESSADO, key="docs_processado",
                              help="Quando o documento foi indexado. Documentos indexados antes desta "
                                   "versão não têm essa data.")
    ordem = g2.selectbox("Ordenar por", ORDEM, key="docs_ordem")

    if g3.button("🔄 Recarregar do banco", key="docs_reload", use_container_width=True):
        _carregar(acervo, forcar=True)
        st.rerun()

    if sem_data and st.button(f"Reparar datas e títulos de {sem_data} vídeo(s)", key="docs_reparar"):
        comum.enfileirar("reparar_metadados", "Reparar datas e títulos",
                         {"colecao_id": acervo["id"], "atualizar_titulo": True}, acervo["id"])
        comum.aviso_enfileirado()

    marcar_todos = bool(st.session_state.get("docs_marcar_todos"))
    versao = st.session_state.get("docs_versao_selecao", 0)

    tabela = _tabela(docs, tipo, busca, so_sem_data, processado, ordem, marcar_todos)

    if tabela.empty:
        st.info("Nenhum documento com estes filtros.")
        return

    total = len(tabela)

    s1, s2, s3 = st.columns([1, 1, 3])

    if s1.button("☑️ Selecionar todos os listados", key="docs_sel_todos"):
        st.session_state["docs_marcar_todos"] = True
        st.session_state["docs_versao_selecao"] = versao + 1
        st.rerun()

    if s2.button("⬜ Limpar seleção", key="docs_sel_nenhum"):
        st.session_state["docs_marcar_todos"] = False
        st.session_state["docs_versao_selecao"] = versao + 1
        st.rerun()

    s3.markdown(
        f"Mostrando **todos os {comum.inteiro_br(total)}** documento(s) com estes filtros. "
        "A tabela rola por dentro: use a barra de rolagem dela para ver os demais."
    )

    editada = st.data_editor(
        tabela, hide_index=True, use_container_width=True,
        disabled=SO_LEITURA,
        key=f"docs_tabela_{acervo['id']}_{tipo}_{busca}_{so_sem_data}_{processado}_{ordem}_{versao}",
        height=min(40 + 36 * total, 600)
    )

    selecionados = list(editada.loc[editada["Selecionar"], "ID"])
    trechos_sel = sum(docs[i]["chunks"] for i in selecionados)

    st.caption(
        f"{len(selecionados)} documento(s) selecionado(s)"
        + (f" · {comum.inteiro_br(trechos_sel)} trecho(s)" if selecionados else "")
        + ". Marque a caixa da primeira coluna de cada linha."
    )

    # ---- editar um documento ----
    if len(selecionados) == 1:

        doc_id = selecionados[0]
        d = docs[doc_id]

        with st.expander(f"✏️ Editar título e data de publicação de `{doc_id}`", expanded=True):

            with st.form(f"form_doc_{doc_id}"):

                titulo = st.text_input("Título", value=d["titulo"] or "", key=f"doc_titulo_{doc_id}")
                data = comum.seletor_data("Data de publicação", d["data_publicacao"], f"doc_data_{doc_id}")

                if st.form_submit_button("Salvar"):

                    if data and not comum_data_ok(data):
                        st.error("Data inválida: use AAAA-MM-DD.")
                    else:
                        Armazenamento(comum.qdrant(), acervo["id"]).atualizar_payload_documento(
                            doc_id, {"titulo": titulo, "titulo_video": titulo, "data_publicacao": data or None}
                        )
                        _carregar(acervo, forcar=True)
                        st.rerun()

    # ---- excluir (sempre visível, logo abaixo da tabela) ----
    with st.container(border=True):

        st.markdown("**🗑️ Excluir documentos selecionados**")

        st.caption(
            "Apaga cada documento selecionado **e todos os seus trechos** do acervo. "
            "Útil para desfazer uma ingestão feita por engano. Para um vídeo, basta incluí-lo de novo "
            "para recuperar; faça um backup antes de apagar muita coisa."
        )

        contador = st.session_state.get("docs_exclusoes", 0)

        confirmacao = st.text_input("Para confirmar, digite APAGAR", key=f"docs_conf_{contador}")

        if st.button(
            f"🗑️ Excluir {len(selecionados)} documento(s) e seus trechos" if selecionados
            else "🗑️ Excluir (selecione documentos na tabela)",
            type="primary", disabled=not selecionados or confirmacao.strip() != "APAGAR", key="docs_del"
        ):
            n_docs, n_trechos = _apagar(acervo, selecionados, docs)

            st.session_state["docs_exclusoes"] = contador + 1          # a próxima exclusão pede a confirmação de novo
            st.session_state["docs_marcar_todos"] = False
            st.session_state["docs_versao_selecao"] = versao + 1
            st.session_state["docs_aviso"] = (
                f"{n_docs} documento(s) e {comum.inteiro_br(n_trechos)} trecho(s) excluído(s) do acervo."
            )

            _carregar(acervo, forcar=True)
            st.rerun()
