"""Editor de cortes: player com marcação de início e fim, legenda .srt do trecho e vídeo cortado."""

import re

import streamlit as st

from admin import cortes, tarefas
from admin.telas import comum
from admin.tarefas import RAIZ
from ingestao import legenda_srt, youtube
from ingestao.armazenamento import Armazenamento

PASTA_COMPONENTE = RAIZ / "componentes" / "player_corte"
DURACAO_INICIAL = 60          # o corte começa com 1 minuto a partir do ponto aberto

_componente = None


def _player(**kw):
    """O componente é declarado uma única vez (aponta para a pasta com o index.html)."""

    global _componente

    if _componente is None:
        import streamlit.components.v1 as components
        _componente = components.declare_component("player_corte", path=str(PASTA_COMPONENTE))

    return _componente(**kw)


def _tempo_da_url(texto):
    """'...?t=90' | '&t=1m30s' | '?t=90s' -> segundos (ou 0)."""

    achou = re.search(r"[?&]t=(?:(\d+)h)?(?:(\d+)m)?(\d+)?s?(?:&|$)", texto or "")

    if not achou or not any(achou.groups()):
        return 0

    h, m, s = (int(g or 0) for g in achou.groups())

    return h * 3600 + m * 60 + s


def abrir(video_id, titulo=None, posicao=0, colecao_id=None):
    """Define o vídeo do editor (usado pelo botão dos cartões de resultado)."""

    st.session_state["corte_video"] = {
        "video_id": video_id, "titulo": titulo or "", "posicao": int(posicao or 0), "colecao_id": colecao_id,
    }


def _titulo_no_acervo(colecao_id, video_id):

    try:
        payloads = Armazenamento(comum.qdrant(), colecao_id).chunks_do_documento(video_id)
    except Exception:
        return ""

    return (payloads[0].get("titulo") or payloads[0].get("titulo_video") or "") if payloads else ""


def _escolher_video():

    corte = st.session_state.get("corte_video")

    with st.expander("🎬 Abrir outro vídeo", expanded=not corte):

        link = st.text_input("Link ou ID do vídeo do YouTube", key="corte_link",
                             placeholder="https://www.youtube.com/watch?v=...")
        acervo = comum.escolher_acervo("corte_acervo", "Acervo (usado para o título e a legenda)")

        if st.button("Abrir no editor", key="corte_abrir"):

            video_id = youtube.extrair_video_id(link)

            if not video_id:
                st.error("Não reconheci um vídeo do YouTube nesse texto.")
            else:
                abrir(video_id, _titulo_no_acervo(acervo["id"], video_id), _tempo_da_url(link), acervo["id"])
                st.rerun()

    return st.session_state.get("corte_video")


def _legenda(video_id, colecao_id):
    """(segmentos, fonte) ou (None, mensagem de erro). Fica guardada na sessão."""

    chave = f"corte_legenda_{video_id}"

    if chave not in st.session_state:

        with st.spinner("Buscando a legenda do vídeo..."):
            try:
                qdrant = comum.qdrant() if colecao_id else None
                st.session_state[chave] = cortes.segmentos_do_video(video_id, colecao_id, qdrant)
            except cortes.SemLegenda as e:
                st.session_state[chave] = (None, str(e))

    return st.session_state[chave]


def _bloco_legenda(video, nome, inicio, fim):

    segmentos, fonte = _legenda(video["video_id"], video.get("colecao_id"))

    st.markdown("#### 📝 Legenda do trecho")

    if segmentos is None:
        st.info(fonte)
        return

    st.caption(f"Origem: {cortes.FONTES[fonte]}.")

    if fonte == "aproximada":
        st.warning(
            "Os tempos desta legenda são **aproximados** (erro de alguns segundos): o banco guarda blocos de texto, "
            "não cada fala. Para tempos exatos o sistema precisa buscar a legenda no YouTube, o que falhou agora "
            "(bloqueio ou vídeo sem legenda). Tente de novo mais tarde."
        )

    deslocar = st.checkbox(
        "Reiniciar os tempos em 00:00 (para usar junto com o vídeo cortado)", value=True, key="corte_deslocar",
        help="Desmarque para manter os tempos originais do vídeo completo."
    )

    falas = legenda_srt.falas_do_trecho(segmentos, inicio, fim, deslocar=deslocar)

    if not falas:
        st.info("Não há falas dentro do trecho marcado.")
        return

    st.download_button(
        f"⬇️ Baixar a legenda do trecho (.srt) · {len(falas)} falas",
        data=legenda_srt.montar_srt(segmentos, inicio, fim, deslocar).encode("utf-8"),
        file_name=f"{nome}.srt", mime="application/x-subrip", key="corte_baixar_srt"
    )

    with st.expander("Ver as falas do trecho"):
        st.text("\n".join(f"[{legenda_srt.formatar_tempo(a)}] {texto}" for a, _, texto in falas[:200]))


def _bloco_corte(video, nome, inicio, fim):

    st.markdown("#### ✂️ Cortar o vídeo")

    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")

    qualidade = c1.selectbox("Qualidade", list(youtube.QUALIDADES), index=2, key="corte_qualidade")

    pedir = c2.button(
        "✂️ Cortar e salvar o trecho marcado", type="primary", key="corte_cortar",
        disabled=fim - inicio < 0.5, use_container_width=True
    )

    st.caption(
        "O corte é feito em segundo plano: o sistema baixa só o trecho (precisa de internet e do ffmpeg, "
        "já incluído no Docker) e grava em `data/cortes`. Use apenas vídeos seus ou com permissão do autor."
    )

    if pedir:
        comum.enfileirar(
            "cortar_video",
            f"Cortar vídeo: {video.get('titulo') or video['video_id']} ({legenda_srt.formatar_tempo(inicio)}"
            f"–{legenda_srt.formatar_tempo(fim)})",
            {
                "video_id": video["video_id"], "titulo": video.get("titulo"), "inicio": inicio, "fim": fim,
                "altura": youtube.QUALIDADES[qualidade], "colecao_id": video.get("colecao_id"),
                "salvar_legenda": True,
            },
            video.get("colecao_id")
        )
        st.success(
            f"Corte de {legenda_srt.formatar_tempo(fim - inicio)} na fila. Quando terminar, ele aparece em "
            "**Cortes prontos**, logo abaixo (a lista se atualiza sozinha); o andamento fica em "
            "*Administração → Tarefas*."
        )


def _formatar_tamanho(n):

    return comum.tamanho_legivel(n)


def _lista_de_cortes():

    itens = cortes.listar_cortes()
    ativas = [t for t in tarefas.listar(limite=100)
              if t["tipo"] == "cortar_video" and t["status"] in tarefas.STATUS_ATIVOS]

    for t in ativas:
        st.info(f"⏳ {t['titulo']} — {t.get('mensagem') or t['status']}")

    if not itens and not ativas:
        st.caption("Nenhum corte salvo ainda.")
        return

    for item in itens:

        with st.container(border=True):

            st.markdown(f"**{item['nome']}**")
            st.caption(f"{_formatar_tamanho(item['tamanho'])} · {item['data']:%d/%m/%Y %H:%M}")

            a, b, c = st.columns(3)

            with open(item["video"], "rb") as f:
                a.download_button("⬇️ Vídeo", data=f.read(), file_name=item["video"].name,
                                  key=f"cdl_v_{item['nome']}", use_container_width=True)

            if item["legenda"]:
                b.download_button("⬇️ Legenda .srt", data=item["legenda"].read_bytes(),
                                  file_name=item["legenda"].name, mime="application/x-subrip",
                                  key=f"cdl_s_{item['nome']}", use_container_width=True)
            else:
                b.caption("sem legenda")

            if c.button("🗑️ Excluir", key=f"cdel_{item['nome']}", use_container_width=True):
                cortes.remover_corte(item["nome"])
                st.rerun()


def render():

    video = _escolher_video()

    if not video:
        st.info("Abra um vídeo pelo link acima, ou clique em **✂️ Cortar este trecho** em um resultado do Oráculo.")
    else:

        chave = f"{video['video_id']}_{video['posicao']}"
        marcas = st.session_state.get(f"corte_marcas_{chave}") or {
            "inicio": video["posicao"], "fim": video["posicao"] + DURACAO_INICIAL
        }

        if video.get("titulo"):
            st.markdown(f"### {video['titulo']}")

        valor = _player(
            chave=chave, video_id=video["video_id"], posicao=video["posicao"],
            duracao_inicial=DURACAO_INICIAL, marcas=marcas, key=f"player_{chave}", default=marcas
        )

        inicio, fim = float(valor["inicio"]), float(valor["fim"])
        st.session_state[f"corte_marcas_{chave}"] = {"inicio": inicio, "fim": fim}

        nome = cortes.nome_do_arquivo(video.get("titulo"), video["video_id"], inicio, fim)

        st.markdown(
            f"**Trecho marcado:** {legenda_srt.formatar_tempo(inicio)} → {legenda_srt.formatar_tempo(fim)} "
            f"(duração {legenda_srt.formatar_tempo(fim - inicio)})"
        )

        _bloco_legenda(video, nome, inicio, fim)
        _bloco_corte(video, nome, inicio, fim)

    st.divider()
    st.markdown("### 📁 Cortes prontos")

    try:
        st.fragment(run_every=3 if any(
            t["tipo"] == "cortar_video" and t["status"] in tarefas.STATUS_ATIVOS for t in tarefas.listar(limite=100)
        ) else None)(_lista_de_cortes)()
    except TypeError:
        _lista_de_cortes()
