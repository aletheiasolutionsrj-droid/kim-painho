"""Aba Saúde e índices."""

import streamlit as st

from admin import saude
from admin.telas import comum


def _servicos():

    st.markdown("#### Serviços e dependências")

    for nome, ok, detalhe in saude.servicos():
        st.markdown(f"{'🟢' if ok else '🔴'} **{nome}** — {detalhe}")


def _executar_diagnostico(acervo):

    try:
        with st.spinner("Conferindo o acervo..."):
            resultado = saude.diagnosticar(comum.qdrant(), acervo["id"])
    except Exception as e:
        st.error(f"Falha no diagnóstico: {e}")
        return

    # Fica na sessão: um botão dentro de "if st.button(...)" some quando o próprio botão é clicado
    # (a página recarrega e o botão de fora volta a "não clicado").
    st.session_state["saude_resultado"] = {"colecao_id": acervo["id"], "r": resultado}


def _acervo():

    st.markdown("#### Diagnóstico de um acervo")

    acervo = comum.escolher_acervo("saude_acervo")

    aviso = st.session_state.pop("saude_aviso", None)

    if aviso:
        st.success(aviso)

    if st.button("Rodar diagnóstico", key="saude_go"):
        _executar_diagnostico(acervo)

    guardado = st.session_state.get("saude_resultado")

    if not guardado or guardado["colecao_id"] != acervo["id"]:
        return

    r = guardado["r"]

    if not r["existe"]:
        st.warning("A coleção ainda não existe no Qdrant (será criada na primeira ingestão).")
        return

    a, b, c, d = st.columns(4)
    a.metric("Trechos", comum.inteiro_br(r["pontos"]))
    b.metric("Documentos", comum.inteiro_br(r["documentos"]))
    c.metric("Vídeos", comum.inteiro_br(r["por_tipo"]["video"]))
    d.metric("PDFs / podcasts", f"{comum.inteiro_br(r['por_tipo']['pdf'])} / {comum.inteiro_br(r['por_tipo']['podcast'])}")

    if not r["amostra_completa"]:
        st.caption(f"Registros conferidos por amostra ({comum.inteiro_br(r['amostra'])} primeiros).")

    problemas = {
        "Trechos sem texto": r["sem_texto"],
        "Trechos sem tipo de fonte": r["sem_tipo_fonte"],
        "Vídeos/podcasts sem marcação de tempo": r["video_sem_tempo"],
    }

    for nome, n in problemas.items():
        (st.warning if n else st.success)(f"{nome}: {comum.inteiro_br(n)}")

    if r["sem_data"]:
        st.info(f"Trechos sem data: {comum.inteiro_br(r['sem_data'])} (use *Reparar datas* na página Documentos).")

    if len(r["modelos"]) > 1:
        st.warning("Há mais de um modelo de embedding misturado neste acervo: " + ", ".join(
            f"{m} ({n})" for m, n in r["modelos"].items()
        ))
    elif r["modelos"]:
        st.caption("Modelo de embedding gravado: " + ", ".join(r["modelos"]))

    st.markdown("**Índices de busca**")

    if r["indices_ausentes"]:

        st.warning("Faltam índices: " + ", ".join(f"`{i}`" for i in r["indices_ausentes"]))

        if st.button("🔧 Criar índices ausentes", key="saude_indices"):
            with st.spinner("Criando índices (em acervos grandes pode levar alguns minutos)..."):
                criados = saude.criar_indices_ausentes(comum.qdrant(), acervo["id"])

            _executar_diagnostico(acervo)                      # confere de novo
            st.session_state["saude_aviso"] = (
                "Índices criados: " + (", ".join(criados) if criados else "nenhum era necessário") + "."
            )
            st.rerun()
    else:
        st.success("Todos os índices necessários existem.")

    if r["video_sem_tempo"] or r["sem_texto"] or r["sem_tipo_fonte"]:
        st.caption(
            "Trechos com defeito não têm correção automática: reingira o documento "
            "(Adicionar conteúdo, com *Reprocessar/Substituir*) ou exclua-o em Documentos."
        )


def render():

    _servicos()
    st.divider()
    _acervo()
