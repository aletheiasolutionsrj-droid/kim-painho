"""Página Atualização automática: canais do YouTube atualizados todo dia, ao abrir o site."""

import streamlit as st

from admin import atualizacoes, catalogo, tarefas
from admin.telas import comum
from admin.telas.adicionar import IDIOMAS_ORIGEM


def _formatar_data(iso):

    if not iso:
        return "nunca"

    a, m, d = iso.split("-")

    return f"{d}/{m}/{a}"


def _situacao(a):
    """Texto com o estado da última tarefa da atualização."""

    if not a.get("ultima_tarefa"):
        return "ainda não rodou"

    t = tarefas.ler(a["ultima_tarefa"])

    if not t:
        return "tarefa não encontrada (já foi limpa da lista)"

    rotulo = {"fila": "na fila", "executando": "em andamento", "concluida": "concluída",
              "cancelada": "cancelada", "erro": "com erro"}.get(t["status"], t["status"])

    r = t.get("resultado") or {}

    if t["status"] == "concluida" and r:
        rotulo += f" — {r.get('inseridos', 0)} vídeo(s) novo(s)"
        if r.get("bloqueado"):
            rotulo += " (o YouTube bloqueou o IP; o restante fica para a próxima execução)"

    return rotulo


def _formulario():

    with st.expander("➕ Cadastrar canal", expanded=not atualizacoes.ler()):

        acervo = comum.escolher_acervo("atu_acervo", "Acervo que será atualizado")

        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        canal = c1.text_input("Link do canal ou playlist", key="atu_canal",
                              placeholder="https://www.youtube.com/@canal")
        nome = c2.text_input("Nome (opcional)", key="atu_nome")

        limite = st.number_input(
            "Máximo de vídeos novos por execução (0 = todos)", 0, 5000, atualizacoes.LIMITE_PADRAO, key="atu_limite",
            help="Protege contra o bloqueio de IP do YouTube. O que passar do limite entra nos dias seguintes."
        )

        c3, c4 = st.columns(2)
        lives = c3.checkbox("Incluir transmissões ao vivo (lives)", key="atu_lives")
        shorts = c4.checkbox("Incluir Shorts", key="atu_shorts")

        traduzir = st.checkbox(
            "Se não houver legenda em português, usar a de outro idioma e traduzir", key="atu_traduzir",
            help="Tradutor do YouTube (grátis). Vídeos sem nenhuma legenda ficam na lista de pendências."
        )

        idiomas, titulo_pt = [], False

        if traduzir:
            idiomas = st.multiselect("Idiomas aceitos como origem", list(IDIOMAS_ORIGEM), default=["en"],
                                     format_func=IDIOMAS_ORIGEM.get, key="atu_idiomas")
            titulo_pt = st.checkbox("Traduzir também o título (usa a Groq)", value=True, key="atu_titulo")

        if st.button("Cadastrar", type="primary", key="atu_criar"):
            try:
                atualizacoes.criar(
                    acervo["id"], canal, nome, limite, lives, shorts,
                    idiomas if traduzir else None, titulo_pt
                )
            except ValueError as e:
                st.error(str(e))
                return

            st.session_state["atu_aviso"] = (
                "Canal cadastrado. A primeira atualização roda na próxima vez que o site for aberto "
                "(ou clique em **Atualizar agora**)."
            )
            st.rerun()


def _cartao(a):

    nome_acervo = (catalogo.obter(a["colecao_id"]) or {}).get("nome", a["colecao_id"])

    with st.container(border=True):

        st.markdown(f"**{'🟢' if a['ativa'] else '⚪'} {a['nome']}** · acervo *{nome_acervo}*")
        st.caption(
            f"{a['canal_url']} · limite {a['limite'] or 'sem limite'} por execução"
            + (" · com lives" if a.get("incluir_lives") else "")
            + (" · com Shorts" if a.get("incluir_shorts") else "")
            + (f" · traduz de {', '.join(a['traduzir_de'])}" if a.get("traduzir_de") else "")
            + (" (e o título)" if a.get("traduzir_titulo") else "")
        )
        st.caption(
            f"Última atualização: {_formatar_data(a.get('ultima_data'))} · {_situacao(a)}"
            + ("" if a["ativa"] else " · **desativada**")
        )

        b1, b2, b3, _ = st.columns([1, 1, 1, 2])

        if b1.button("⏸️ Desativar" if a["ativa"] else "▶️ Ativar", key=f"atu_alt_{a['id']}"):
            atualizacoes.definir_ativa(a["id"], not a["ativa"])
            st.rerun()

        if b2.button("🔄 Atualizar agora", key=f"atu_agora_{a['id']}"):
            if atualizacoes._tarefa_ativa(a["id"]):
                st.session_state["atu_aviso"] = "Já existe uma atualização deste canal em andamento."
            else:
                atualizacoes.criar_tarefa(a)
                tarefas.garantir_worker()
                st.session_state["atu_aviso"] = "Tarefa criada. Acompanhe em **Tarefas**."
            st.rerun()

        if b3.button("🗑️ Excluir", key=f"atu_del_{a['id']}"):
            st.session_state["atu_confirmar"] = a["id"]
            st.rerun()

        if st.session_state.get("atu_confirmar") == a["id"]:

            st.warning(
                "Excluir só remove o agendamento. Os vídeos já incluídos continuam no acervo."
            )

            d1, d2, _ = st.columns([1, 1, 3])

            if d1.button("Confirmar exclusão", type="primary", key=f"atu_del_ok_{a['id']}"):
                atualizacoes.remover(a["id"])
                st.session_state.pop("atu_confirmar", None)
                st.session_state["atu_aviso"] = f"Atualização de “{a['nome']}” excluída."
                st.rerun()

            if d2.button("Cancelar", key=f"atu_del_no_{a['id']}"):
                st.session_state.pop("atu_confirmar", None)
                st.rerun()


def render():

    st.write(
        "Cadastre o link de um canal do YouTube para um acervo. **Uma vez por dia, na primeira vez que o site "
        "for aberto**, o sistema cria uma tarefa que inclui os vídeos novos do canal (os que já estão no acervo "
        "são ignorados). Você pode desativar, reativar ou excluir cada atualização quando quiser."
    )

    st.caption(
        "A verificação acontece quando alguém abre o Kim Painho ou a Administração; se o computador ficou "
        "desligado, a atualização roda no próximo acesso. Se o YouTube bloquear o IP, a tarefa para e o restante "
        "é retomado no dia seguinte."
    )

    aviso = st.session_state.pop("atu_aviso", None)

    if aviso:
        st.success(aviso)

    _formulario()

    itens = atualizacoes.ler()

    if not itens:
        st.info("Nenhum canal cadastrado ainda.")
        return

    st.markdown(f"**{len(itens)} atualização(ões) cadastrada(s)**")

    for a in itens:
        _cartao(a)
