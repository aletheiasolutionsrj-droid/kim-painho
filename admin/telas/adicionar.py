"""Aba Adicionar conteúdo: YouTube, PDF, podcast/áudio e vídeos sem legenda."""

import hashlib
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from admin import pendencias
from admin.telas import comum
from ingestao import pipeline, whisper, youtube

IDIOMAS_ORIGEM = {"en": "Inglês", "es": "Espanhol", "fr": "Francês", "de": "Alemão", "it": "Italiano",
                  "ru": "Russo", "ja": "Japonês", "zh-Hans": "Chinês"}

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data_ok(texto):

    return not texto or bool(_RE_DATA.match(texto.strip()))


def _controles_whisper(chave, ativo=True):
    """Seletor do modelo; avisa quando a biblioteca não está instalada."""

    if not whisper.disponivel():
        st.warning(
            "O Whisper não está instalado nesta imagem. Adicione `faster-whisper` ao "
            "`requirements.txt` e refaça o build (`docker compose up -d --build`)."
        )
        return None

    return st.selectbox(
        "Modelo do Whisper", whisper.MODELOS, index=1, disabled=not ativo, key=chave,
        help="small: rápido, erra mais nomes. medium: bom equilíbrio. "
             "large-v3: o mais fiel, bem mais lento (ideal com placa de vídeo)."
    )


# ------------------------------------------------------------
# YOUTUBE
# ------------------------------------------------------------

def _youtube_links(acervo):

    st.write(
        "Cole links de vídeos (um por linha) ou o link de um canal/playlist. "
        "Vídeos que já estão no acervo são ignorados."
    )

    texto = st.text_area("Links", height=140, key="yt_links",
                         placeholder="https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/@canal")

    if any(youtube.eh_canal_ou_playlist(linha) for linha in (texto or "").splitlines()):
        st.warning(
            "⚠️ **Baixar um canal ou playlist inteira faz muitas requisições ao YouTube**, que pode bloquear o "
            "seu IP temporariamente (de algumas horas até cerca de 6 horas). O sistema espera de 3 a 7 segundos "
            "entre os vídeos e, se for bloqueado, **para sozinho e avisa** quantos faltaram. Nesse caso, espere "
            "cerca de 6 horas e clique em **Retomar** na tarefa (aba Tarefas): os vídeos já incluídos são "
            "ignorados e o processamento continua do ponto em que parou. Para reduzir o risco em canais grandes, "
            "use o limite de vídeos por tarefa (por exemplo, 100)."
        )

    c1, c2 = st.columns(2, vertical_alignment="bottom")

    limite = c1.number_input(
        "Máximo de vídeos novos por tarefa (0 = todos)", 0, 5000, 0, key="yt_limite",
        help="Em canais grandes, comece com 50–100: o YouTube bloqueia o IP se houver muitas requisições seguidas."
    )
    substituir = c2.checkbox("Reprocessar vídeos já cadastrados", key="yt_subst")

    traduzir = st.checkbox(
        "Se não houver legenda em português, usar a de outro idioma e traduzir para o português",
        key="yt_traduzir",
        help="Usa o tradutor do próprio YouTube (grátis). A qualidade é de tradução automática. "
             "Vale para vídeos em inglês, espanhol etc. que tenham legenda no YouTube; "
             "áudio transcrito pelo Whisper não é traduzido."
    )

    idiomas = []
    traduzir_titulo = False

    if traduzir:
        idiomas = st.multiselect(
            "Idiomas aceitos como origem", list(IDIOMAS_ORIGEM), default=["en"],
            format_func=IDIOMAS_ORIGEM.get, key="yt_idiomas"
        )
        traduzir_titulo = st.checkbox(
            "Traduzir também o título dos vídeos traduzidos", value=True, key="yt_traduzir_titulo",
            help="Usa a IA da Groq (a sua chave), uma chamada curta por vídeo. O título original fica guardado. "
                 "Se a Groq falhar ou atingir o limite, o vídeo entra com o título original."
        )

    c3, c4 = st.columns(2)
    lives = c3.checkbox("Canal: incluir transmissões ao vivo (lives)", key="yt_lives")
    shorts = c4.checkbox("Canal: incluir Shorts", key="yt_shorts")

    pode_whisper = whisper.disponivel()

    usar_whisper = st.checkbox(
        "Se o vídeo não tiver legenda, transcrever o áudio com o Whisper",
        disabled=not pode_whisper, key="yt_whisper",
        help="Mais lento. Sem isso, o vídeo vai para a lista de pendências." if pode_whisper
        else "Whisper não instalado nesta imagem."
    )

    modelo = _controles_whisper("yt_modelo", usar_whisper) if usar_whisper else "medium"

    if not st.button("Adicionar à fila", type="primary", key="yt_go"):
        return

    itens, canais, invalidos = [], [], []

    for linha in (texto or "").splitlines():

        linha = linha.strip()

        if not linha:
            continue

        if youtube.eh_canal_ou_playlist(linha):
            canais.append(linha)
        elif youtube.extrair_video_id(linha):
            itens.append({"video_id": youtube.extrair_video_id(linha)})
        else:
            invalidos.append(linha)

    if invalidos:
        st.warning("Não reconheci estes links: " + ", ".join(f"`{i}`" for i in invalidos[:5]))

    if not itens and not canais:
        st.error("Nenhum link válido.")
        return

    base = {
        "colecao_id": acervo["id"], "substituir": substituir,
        "whisper_se_faltar": bool(usar_whisper and pode_whisper),
        "modelo_whisper": modelo or "medium", "limite": int(limite) or None,
        "incluir_lives": lives, "incluir_shorts": shorts,
        "traduzir_de": idiomas if traduzir else None,
        "traduzir_titulo": bool(traduzir and traduzir_titulo),
    }

    criadas = 0

    if itens:
        comum.enfileirar("legendas_youtube", f"{len(itens)} vídeo(s) avulso(s)",
                         dict(base, itens=itens, limite=None), acervo["id"])
        criadas += 1

    for canal in canais:
        comum.enfileirar("legendas_youtube", f"Canal/playlist: {canal}",
                         dict(base, canal_url=canal), acervo["id"])
        criadas += 1

    comum.aviso_enfileirado(criadas)


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------

def _pdf(acervo):

    st.write("Envie um ou mais PDFs. Cada um vira um documento, com a página exata nas fontes.")

    arquivos = st.file_uploader("PDFs", type=["pdf"], accept_multiple_files=True, key="pdf_up")

    dados = []

    for i, arq in enumerate(arquivos or []):

        edicao, data = pipeline.interpretar_edicao(arq.name)
        sufixo = f"{i}_{arq.name}"

        with st.expander(arq.name, expanded=len(arquivos) == 1):

            titulo = st.text_input("Título", value=Path(arq.name).stem.replace("_", " "), key=f"pdf_t_{sufixo}")
            c1, c2 = st.columns(2)
            ed = c1.text_input("Edição", value=edicao or "", key=f"pdf_e_{sufixo}", placeholder="Janeiro de 2026")
            with c2:
                dt = comum.seletor_data("Data de referência", data, f"pdf_d_{sufixo}")

        dados.append((arq, titulo.strip(), ed.strip(), dt.strip()))

    modo = st.radio(
        "Numeração das páginas",
        ["Ler a numeração impressa no PDF (recomendado)",
         "A capa (e outras páginas iniciais) não têm número"],
        key="pdf_modo"
    )

    sem_numero = None

    if modo.startswith("A capa"):
        sem_numero = int(st.number_input("Quantas páginas iniciais não são numeradas", 1, 20, 1, key="pdf_capa"))

    c1, c2 = st.columns(2)

    copia = c1.checkbox(
        "Guardar cópia para abrir o PDF na página exata", value=True, key="pdf_copia",
        help="A cópia fica em static/pdfs, no seu computador. Não entra nos backups do Qdrant."
    )
    substituir = c2.checkbox("Substituir se já existir", key="pdf_subst")

    if not st.button("Adicionar à fila", type="primary", key="pdf_go", disabled=not dados):
        return

    for arq, titulo, ed, dt in dados:
        if not _data_ok(dt):
            st.error(f"Data inválida em {arq.name}: use AAAA-MM-DD.")
            return

    for arq, titulo, ed, dt in dados:

        caminho = comum.salvar_upload(arq)

        comum.enfileirar("pdf", f"PDF: {titulo or arq.name}", {
            "colecao_id": acervo["id"], "caminho": str(caminho), "titulo": titulo or None,
            "edicao": ed or None, "data_publicacao": dt or None, "substituir": substituir,
            "paginas_sem_numero": sem_numero, "guardar_copia": copia, "apagar_origem": True,
        }, acervo["id"])

    comum.aviso_enfileirado(len(dados))


# ------------------------------------------------------------
# PODCAST / ÁUDIO / TRANSCRIÇÃO PRONTA
# ------------------------------------------------------------

def _numero_do_nome(nome):

    achou = re.search(r"\d+", nome)

    return int(achou.group()) if achou else None


def _podcast(acervo):

    st.write(
        "Envie o **áudio** (o Whisper transcreve) ou uma **transcrição pronta** com tempos "
        "(.srt, .vtt, .json). Para lotes grandes, copie os arquivos para a pasta "
        f"`data/entrada` do projeto e escolha-os abaixo."
    )

    st.info(
        "ℹ️ **Podcasts e áudios não abrem no ponto exato pelo link**, como os vídeos do YouTube fazem. "
        "Por isso, nas respostas o sistema mostra **em que minuto do áudio** o trecho foi falado, "
        "para você localizá-lo no player. O endereço (opcional) serve só para abrir a fonte."
    )

    origem = st.radio("De onde vêm os arquivos?", ["Enviar pelo navegador", "Pasta data/entrada"],
                      horizontal=True, key="pod_origem")

    extensoes = comum.EXT_AUDIO + comum.EXT_TRANSCRICAO

    escolhidos = []      # (nome, enviado|Path, apagar_depois)

    if origem == "Enviar pelo navegador":

        tipos = [e.lstrip(".") for e in extensoes]
        for arq in st.file_uploader("Arquivos", type=tipos, accept_multiple_files=True, key="pod_up") or []:
            escolhidos.append((arq.name, arq, True))
    else:

        disponiveis = comum.listar_entrada(extensoes)

        if not disponiveis:
            st.info("Nenhum arquivo em `data/entrada`.")

        for p in st.multiselect("Arquivos da pasta", disponiveis, format_func=lambda p: p.name, key="pod_pasta"):
            escolhidos.append((p.name, p, False))

    if not escolhidos:
        return

    assinatura = hashlib.md5("|".join(n for n, _, _ in escolhidos).encode()).hexdigest()[:8]

    tabela = pd.DataFrame([
        {
            "Arquivo": nome,
            "Título": Path(nome).stem.replace("_", " ").replace("-", " ").strip(),
            "Episódio": _numero_do_nome(nome),
            "Data": None,
            "Endereço (opcional)": "",
        }
        for nome, _, _ in escolhidos
    ])

    st.caption("Confira e edite os dados de cada arquivo. O título ajuda a IA a citar a fonte.")

    editada = st.data_editor(
        tabela, hide_index=True, use_container_width=True, disabled=["Arquivo"],
        column_config={"Data": comum.coluna_data("Data de publicação")},
        key=f"pod_tabela_{assinatura}"
    )

    tem_audio = any(Path(n).suffix.lower() in comum.EXT_AUDIO for n, _, _ in escolhidos)

    modelo = _controles_whisper("pod_modelo") if tem_audio else None
    substituir = st.checkbox("Substituir se já existir", key="pod_subst")

    bloqueado = tem_audio and modelo is None

    if not st.button("Adicionar à fila", type="primary", key="pod_go", disabled=bloqueado):
        return

    linhas = editada.to_dict("records")

    for linha in linhas:
        if not str(linha["Título"]).strip():
            st.error(f"Informe o título de {linha['Arquivo']}.")
            return
        if not _data_ok(comum.data_iso(linha["Data"])):
            st.error(f"Data inválida em {linha['Arquivo']}: use AAAA-MM-DD.")
            return

    for (nome, fonte, apagar), linha in zip(escolhidos, linhas):

        caminho = comum.salvar_upload(fonte) if apagar else fonte

        try:
            episodio = int(float(linha["Episódio"]))
        except (TypeError, ValueError):
            episodio = None

        comum_params = {
            "colecao_id": acervo["id"], "tipo_fonte": "podcast",
            "titulo": str(linha["Título"]).strip(),
            "data_publicacao": comum.data_iso(linha["Data"]) or None,
            "episodio": episodio, "url": str(linha["Endereço (opcional)"] or "").strip() or None,
            "substituir": substituir, "apagar_origem": apagar,
        }

        if Path(nome).suffix.lower() in comum.EXT_AUDIO:
            comum.enfileirar("transcrever_audio", f"Áudio: {comum_params['titulo']}",
                             dict(comum_params, caminho_audio=str(caminho), modelo_whisper=modelo),
                             acervo["id"])
        else:
            comum.enfileirar("transcricao_arquivo", f"Transcrição: {comum_params['titulo']}",
                             dict(comum_params, caminho=str(caminho), nome_original=nome),
                             acervo["id"])

    comum.aviso_enfileirado(len(escolhidos))


# ------------------------------------------------------------
# VÍDEOS SEM LEGENDA
# ------------------------------------------------------------

def _sem_legenda(acervo):

    lista = pendencias.listar(acervo["id"])

    if not lista:
        st.info("Nenhum vídeo sem legenda neste acervo.")
        return

    st.write(
        f"**{len(lista)}** vídeo(s) não tinham legenda no YouTube. "
        "Escolha o que fazer com eles."
    )

    rotulos = {p["video_id"]: f"{p.get('titulo') or p['video_id']}  ·  {p['video_id']}" for p in lista}

    escolhidos = st.multiselect("Vídeos", list(rotulos), format_func=rotulos.get, key="pend_sel")

    a, b = st.columns(2)

    modelo = _controles_whisper("pend_modelo")

    if a.button("Transcrever com o Whisper", type="primary", key="pend_whisper",
                disabled=not escolhidos or modelo is None):

        for video_id in escolhidos:
            comum.enfileirar("transcrever_audio", f"Whisper: {rotulos[video_id]}",
                             {"colecao_id": acervo["id"], "video_id": video_id, "modelo_whisper": modelo},
                             acervo["id"])

        comum.aviso_enfileirado(len(escolhidos))

    if b.button("Tentar a legenda de novo", key="pend_retry", disabled=not escolhidos):

        comum.enfileirar("legendas_youtube", f"Rever {len(escolhidos)} vídeo(s) sem legenda",
                         {"colecao_id": acervo["id"], "itens": [{"video_id": v} for v in escolhidos],
                          "reavaliar_pendentes": True}, acervo["id"])
        comum.aviso_enfileirado(1)

    with st.expander("Já tenho o áudio deste vídeo"):

        alvo = st.selectbox("Vídeo", list(rotulos), format_func=rotulos.get, key="pend_audio_video")
        audio = st.file_uploader("Áudio (mp3, m4a...)", type=[e.lstrip(".") for e in comum.EXT_AUDIO],
                                 key="pend_audio_arq")

        if st.button("Transcrever este áudio", key="pend_audio_go", disabled=audio is None or modelo is None):

            caminho = comum.salvar_upload(audio)
            comum.enfileirar("transcrever_audio", f"Whisper: {rotulos[alvo]}",
                             {"colecao_id": acervo["id"], "video_id": alvo, "caminho_audio": str(caminho),
                              "modelo_whisper": modelo, "apagar_origem": True}, acervo["id"])
            comum.aviso_enfileirado(1)

    with st.expander("Esquecer estes vídeos"):

        if st.button("Remover da lista de pendências", key="pend_esquecer", disabled=not escolhidos):
            for video_id in escolhidos:
                pendencias.remover(acervo["id"], video_id)
            st.rerun()


# ------------------------------------------------------------
# YOUTUBE: ARQUIVOS DE LEGENDA (.json, .srt, .vtt)
# ------------------------------------------------------------

_RE_ID_NO_JSON = re.compile(r'"video_id"\s*:\s*"([A-Za-z0-9_-]{11})"')
_RE_ID_NO_NOME = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
EXT_LEGENDA = (".json", ".srt", ".vtt")


def _id_no_nome(nome):
    """Procura um ID de vídeo (11 caracteres) no nome do arquivo."""

    stem = Path(nome).stem

    for achado in _RE_ID_NO_NOME.findall(stem):

        # IDs reais misturam números, _ ou - e maiúsculas; palavras comuns de 11 letras não.
        parece_id = any(c.isdigit() or c in "_-" for c in achado) or any(c.isupper() for c in achado[1:])

        if parece_id:
            return achado

    return ""


def _espiar(inicio_bytes, nome):
    """ID do vídeo que já está dentro do .json (lê só o começo do arquivo)."""

    if not nome.lower().endswith(".json"):
        return ""

    achou = _RE_ID_NO_JSON.search(inicio_bytes.decode("utf-8", errors="ignore"))

    return achou.group(1) if achou else ""


def _pasta_do_projeto(texto):
    """Resolve uma pasta relativa ao projeto; só aceita pastas dentro dele."""

    pasta = (comum.RAIZ / (texto or "").strip()).resolve()

    if comum.RAIZ.resolve() not in (pasta, *pasta.parents):
        return None

    return pasta if pasta.is_dir() else None


def _candidatos_legenda():
    """[{"nome","caminho","enviado","id"}] a partir da pasta do projeto ou de envio pelo navegador."""

    origem = st.radio("De onde vêm os arquivos?", ["Pasta do projeto", "Enviar pelo navegador"],
                      horizontal=True, key="leg_origem")

    candidatos = []

    if origem == "Pasta do projeto":

        texto = st.text_input("Pasta (dentro do projeto)", value="legendas_json", key="leg_pasta",
                              help="Ex.: legendas_json, ou data/entrada.")
        pasta = _pasta_do_projeto(texto)

        if pasta is None:
            st.warning("Pasta não encontrada dentro do projeto.")
            return []

        for p in sorted(pasta.iterdir()):
            if p.is_file() and p.suffix.lower() in EXT_LEGENDA:
                with open(p, "rb") as f:
                    inicio = f.read(4096)
                candidatos.append({"nome": p.name, "caminho": p, "enviado": None,
                                   "id": _espiar(inicio, p.name) or _id_no_nome(p.name)})
    else:

        tipos = [e.lstrip(".") for e in EXT_LEGENDA]

        for arq in st.file_uploader("Arquivos de legenda", type=tipos, accept_multiple_files=True,
                                    key="leg_up") or []:
            candidatos.append({"nome": arq.name, "caminho": None, "enviado": arq,
                               "id": _espiar(bytes(arq.getbuffer()[:4096]), arq.name) or _id_no_nome(arq.name)})

    return candidatos


def _youtube_arquivos(acervo):

    st.write(
        "Importe legendas que você já tem em arquivo: **.json** (formato do projeto), **.srt** ou **.vtt**. "
        "Arquivos .json que já trazem o ID do vídeo entram direto. Para os demais, preencha a tabela: "
        "o que ficar em branco pode ser buscado no YouTube. Vídeos que já estão no acervo são ignorados."
    )

    candidatos = _candidatos_legenda()

    if not candidatos:
        st.info("Nenhum arquivo .json, .srt ou .vtt encontrado.")
        return

    completos = [c for c in candidatos if c["id"] and c["nome"].lower().endswith(".json")]
    pendentes = [c for c in candidatos if c not in completos]

    a, b = st.columns(2)
    a.metric("Prontos para importar (.json com ID)", comum.inteiro_br(len(completos)))
    b.metric("Precisam de dados (formulário)", comum.inteiro_br(len(pendentes)))

    linhas = []

    if pendentes:

        assinatura = hashlib.md5("|".join(c["nome"] for c in pendentes).encode()).hexdigest()[:8]

        tabela = pd.DataFrame([
            {"Arquivo": c["nome"], "Link ou ID do vídeo": c["id"], "Título": "", "Data": None}
            for c in pendentes
        ])

        st.markdown("**Dados dos arquivos que não os trazem**")
        st.caption("Título e data em branco: usa o que estiver dentro do arquivo ou busca no YouTube (opção abaixo).")

        editada = st.data_editor(tabela, hide_index=True, use_container_width=True, disabled=["Arquivo"],
                                 column_config={"Data": comum.coluna_data("Data de publicação")},
                                 key=f"leg_tabela_{assinatura}", height=min(40 + 36 * len(tabela), 500))

        linhas = editada.to_dict("records")

    c1, c2 = st.columns(2)

    substituir = c1.checkbox("Reprocessar vídeos já cadastrados", key="leg_subst")
    buscar = c2.checkbox("Buscar no YouTube o título e a data que faltarem", value=True, key="leg_buscar",
                         help="Consulta cerca de 5 s por vídeo, para não ser bloqueado pelo YouTube.")

    converter = st.checkbox("Guardar uma cópia em .json das legendas .srt/.vtt (conversão)", value=True,
                            key="leg_converter",
                            help="Mantém seu acervo de legendas em um formato só, útil para backup e para reindexar.")

    pasta_json = "legendas_json"

    if converter:
        pasta_json = st.text_input("Pasta de destino dos .json convertidos", value="legendas_json", key="leg_destino")

    if not st.button("Adicionar à fila", type="primary", key="leg_go"):
        return

    erros = []

    for c, linha in zip(pendentes, linhas):

        if not youtube.extrair_video_id(str(linha["Link ou ID do vídeo"] or "")):
            erros.append(f"{c['nome']}: informe o link ou o ID do vídeo.")

        if not _data_ok(comum.data_iso(linha["Data"])):
            erros.append(f"{c['nome']}: data inválida (use AAAA-MM-DD).")

    if erros:
        for e in erros[:8]:
            st.error(e)
        return

    destino = None

    if converter:
        pasta = (comum.RAIZ / pasta_json.strip()).resolve()

        if comum.RAIZ.resolve() not in pasta.parents:
            st.error("A pasta de destino precisa ficar dentro do projeto.")
            return

        destino = str(pasta)

    por_arquivo = {c["nome"]: l for c, l in zip(pendentes, linhas)}

    itens = []

    for c in candidatos:

        linha = por_arquivo.get(c["nome"], {})

        caminho = c["caminho"] if c["caminho"] else comum.salvar_upload(c["enviado"])

        itens.append({
            "caminho": str(caminho), "nome_original": c["nome"],
            "video_id": str(linha.get("Link ou ID do vídeo") or c["id"] or ""),
            "titulo": str(linha.get("Título") or "").strip() or None,
            "data_publicacao": comum.data_iso(linha.get("Data")) or None,
            "apagar_origem": c["enviado"] is not None,
        })

    comum.enfileirar("importar_legendas", f"Importar {len(itens)} legenda(s) de arquivo", {
        "colecao_id": acervo["id"], "itens": itens, "substituir": substituir,
        "buscar_metadados": buscar, "salvar_json": destino,
    }, acervo["id"])

    comum.aviso_enfileirado()


# ------------------------------------------------------------
# PÁGINAS DO MENU
# ------------------------------------------------------------

def _acervo():

    return comum.escolher_acervo("adicionar_acervo", "Adicionar ao acervo")


def pagina_youtube():

    acervo = _acervo()

    abas = st.tabs(["🔗 Links e canais", "📁 Arquivos de legenda (.json, .srt, .vtt)"])

    with abas[0]:
        _youtube_links(acervo)

    with abas[1]:
        _youtube_arquivos(acervo)


def pagina_pdf():

    _pdf(_acervo())


def pagina_podcast():

    _podcast(_acervo())


def pagina_sem_legenda():

    _sem_legenda(_acervo())
