import base64
import html
import streamlit as st


def get_base64(img_path):
    """Converte uma imagem para Base64."""
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def aplicar_estilo_sidebar(img_path):
    """Aplica a imagem e o estilo visual da sidebar."""

    img = get_base64(img_path)

    st.markdown(
        f"""
        <style>

        /* Container principal da sidebar */
        [data-testid="stSidebar"] > div:first-child {{
            position: relative;
            padding-top: 50px;
            background-color: #f1f3f6;
        }}

        /* Área da imagem no topo */
        [data-testid="stSidebar"] > div:first-child::before {{
            content: "";
            position: absolute;

            top: 0;
            left: 0;
            right: 0;

            height: 320px;

            background-image: url("data:image/png;base64,{img}");
            background-repeat: no-repeat;
            background-position: top center;
            background-size: 110% auto;

            z-index: 0;
            pointer-events: none;
        }}

        /* Mantém o conteúdo da sidebar acima do fundo */
        [data-testid="stSidebar"] > div:first-child > * {{
            position: relative;
            z-index: 1;
            padding-top: 130px;
        }}

        .icone-fonte {{
            font-size: 16px;
        }}

        .tooltip-olho:hover .tooltip-texto {{
            visibility: visible;
            opacity: 1;
        }}

        .nome-fonte {{
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        section[data-testid="stSidebar"] hr {{
            margin-top: 4px;
            margin-bottom: 4px;
        }}

        .modo-busca {{
            margin-top: -12px;
            margin-bottom: -18px;
        }}

        .modo-busca + div {{
            margin-top: -10px;
        }}

        /* ============================================================
           RADIO - MODO DE BUSCA
           ============================================================ */

        div[data-testid="stForm"] div[data-testid="stRadio"] {{
            display: flex !important;
            align-items: center !important;
            gap: 12px !important;
            margin-top: -20px !important;
            margin-bottom: -20px !important;
        }}

        div[data-testid="stForm"] div[data-testid="stRadio"] > label {{
            margin: 0 !important;
            padding: 0 !important;
            white-space: nowrap !important;
        }}

        div[data-testid="stForm"] div[data-testid="stRadio"] > div {{
            margin: 0 !important;
            padding: 0 !important;
        }}

        </style>
        """,
        unsafe_allow_html=True
    )


def exibir_titulo_com_tooltip(icone, titulo, texto):
    """Exibe o título da fonte com um olho que mostra o chunk ao passar o mouse."""

    titulo_completo = str(titulo or "Sem título")
    titulo = html.escape(titulo_completo)
    texto = str(texto or "Este registro não possui texto disponível.")

    # o título aparece cortado no cartão; no popup ele vem inteiro, antes do texto do trecho
    texto_tooltip = html.escape(f"{titulo_completo}\n\n{texto}", quote=True).replace('\n', '&#10;')

    html_conteudo = f"""
    <div style="
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 8px;
        font-weight: 600;
    ">
        <span style="font-size: 18px;">{icone}</span>

        <span
            title="{texto_tooltip}"
            style="
                font-size: 17px;
                cursor: default;
            "
        >👁️</span>

        <span style="
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        ">
            {titulo}
        </span>
    </div>
    """

    st.html(html_conteudo)


def exibir_relevancia_e_data(fonte):
    """Mostra a relevância (quando houver reranking) e a data da fonte."""

    score = fonte.get("score_reranker")

    if score is not None:
        st.caption(f"💎 Relevância: {score:.2f} pontos")

    data = fonte.get("data_publicacao")

    if data:
        partes = str(data).split("-")

        if len(partes) == 3 and len(partes[0]) == 4:
            data = f"{partes[2]}/{partes[1]}/{partes[0]}"

        st.caption(f"📅 {data}")


def exibir_localizacao_pdf(fonte):
    """
    Página (numeração do autor, a mesma do Sumário), posição no arquivo,
    edição/tema e, se houver cópia local do PDF, o botão que abre na página.
    """

    from ingestao.arquivos import url_pdf

    pag = fonte.get("pagina")
    pag_fim = fonte.get("pagina_fim") or pag
    impressa = fonte.get("pagina_impressa")
    total = fonte.get("total_paginas")

    def faixa(a, b):
        return f"{a}" if a == b or b is None else f"{a}–{b}"

    if impressa is not None and pag is not None:

        impressa_fim = impressa + ((pag_fim or pag) - pag)

        st.markdown(f"📍 **Página:** `{faixa(impressa, impressa_fim)}`")

        st.caption(
            f"Posição no arquivo PDF: {faixa(pag, pag_fim)}"
            + (f" de {total}" if total else "")
        )

    else:

        st.markdown(
            f"📍 **Página:** `{faixa(pag, pag_fim)}`"
            + (f" de {total}" if total else "")
        )

    if fonte.get("edicao"):
        st.caption(f"🗓️ {fonte['edicao']}")

    if fonte.get("tema"):
        st.caption(
            "📚 " + fonte["tema"]
            + (f" › {fonte['subtema']}" if fonte.get("subtema") else "")
        )

    url = url_pdf(fonte.get("doc_id"), pag)

    if url:
        st.link_button(
            "📖 Abrir PDF nesta página",
            url,
            use_container_width=True
        )


def exibir_fonte(fonte, rotulo=None):
    """
    Cartão de um resultado da busca. Cobre PDF, podcast/áudio e vídeo; qualquer outro tipo
    (ou trecho sem tipo, de ingestões antigas) cai no cartão de vídeo, para nada sumir da tela.
    """

    tipo = fonte.get("tipo_fonte")
    titulo = fonte.get("titulo_video") or fonte.get("titulo")

    with st.container(border=True):

        if rotulo:
            st.markdown(f"**{rotulo}**")          # a IA cita "Fonte N": aqui o usuário acha o mesmo número

        if tipo == "pdf":

            exibir_titulo_com_tooltip("📄", fonte.get("arquivo_nome") or titulo, fonte.get("texto_bruto", ""))
            exibir_relevancia_e_data(fonte)
            exibir_localizacao_pdf(fonte)
            st.caption("🔮 Trecho identificado pela visão astral")
            return

        if tipo == "podcast":

            exibir_titulo_com_tooltip("🎙️", titulo, fonte.get("texto_bruto", ""))
            exibir_relevancia_e_data(fonte)

            if fonte.get("episodio") is not None:
                st.caption(f"🎧 Episódio {fonte['episodio']}")

            st.caption(f"⏱️ Falado aos {fonte.get('timestamp_texto') or '?'} do áudio")

            if fonte.get("url"):
                st.link_button("🔗 Abrir a fonte", fonte["url"], use_container_width=True)

            return

        exibir_titulo_com_tooltip("🎬", titulo, fonte.get("texto_bruto", ""))
        exibir_relevancia_e_data(fonte)
        st.caption(f"🔮 Revelação encontrada em: {fonte.get('timestamp_texto') or '?'}")

        if fonte.get("url_com_minuto"):
            st.link_button("▶️ Assistir no Ponto Exato", fonte["url_com_minuto"], use_container_width=True)


def renderizar_header():
    """Renderiza o cabeçalho principal do Kim Painho."""

    st.markdown(
        "<h1 style='text-align: center; color: #1E3A8A; "
        "margin-top:-70px; margin-bottom:0px;'>"
        "🔮 KIM PAINHO</h1>",
        unsafe_allow_html=True
    )

    st.markdown(
        "<p style='text-align: center; color: #6B7280;'>"
        "O Oráculo do Acervo... Ele sabe. Você pergunta.</p>",
        unsafe_allow_html=True
    )

    #st.divider()