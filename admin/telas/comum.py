"""Utilitários compartilhados pelas telas de administração."""

import os
import re
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from admin import catalogo, tarefas
from admin.tarefas import RAIZ

PASTA_UPLOADS = RAIZ / "data" / "uploads"
PASTA_ENTRADA = RAIZ / "data" / "entrada"

EXT_AUDIO = (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".mp4", ".webm", ".opus")
EXT_TRANSCRICAO = (".srt", ".vtt", ".json")


_RE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATA_MIN = date(1900, 1, 1)
DATA_MAX = date(2100, 12, 31)


def data_iso(valor):
    """
    Qualquer valor de data (calendário, tabela, texto) -> 'AAAA-MM-DD'; vazio -> ''.
    Texto é devolvido como está (a validação de formato fica com quem chama).
    """

    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")

    return str(valor).strip()


def _como_data(valor):

    if isinstance(valor, date):
        return valor

    texto = data_iso(valor)

    if _RE_ISO.match(texto):
        try:
            return date.fromisoformat(texto)
        except ValueError:
            return None

    return None


def seletor_data(rotulo, valor, key, **kw):
    """Campo de data com calendário (exibe DD/MM/AAAA). Devolve 'AAAA-MM-DD' ou '' se vazio."""

    return data_iso(st.date_input(
        rotulo, value=_como_data(valor), min_value=DATA_MIN, max_value=DATA_MAX,
        format="DD/MM/YYYY", key=key, **kw
    ))


def coluna_data(rotulo="Data"):
    """Coluna de data (com calendário) para st.data_editor."""

    return st.column_config.DateColumn(
        rotulo, format="DD/MM/YYYY", min_value=DATA_MIN, max_value=DATA_MAX
    )


@st.cache_resource
def qdrant():
    from ingestao import pipeline

    return pipeline.criar_cliente_qdrant()


def exigir_senha():
    """Se ADMIN_PASSWORD estiver definida no ambiente, pede a senha antes de mostrar a página."""

    senha = os.getenv("ADMIN_PASSWORD")

    if not senha or st.session_state.get("admin_liberado"):
        return

    st.title("🔒 Administração")

    digitada = st.text_input("Senha de administrador", type="password")

    if digitada:
        if digitada == senha:
            st.session_state["admin_liberado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")

    st.stop()


def escolher_acervo(chave, rotulo="Acervo"):
    """Seletor de acervo. Devolve o dict do catálogo (ou interrompe a tela se não há acervos)."""

    colecoes = catalogo.ler()

    if not colecoes:
        st.info("Nenhum acervo cadastrado. Crie o primeiro na aba **Acervos**.")
        st.stop()

    lembrado = st.session_state.get("acervo_escolhido")

    padrao = next(
        (i for i, c in enumerate(colecoes) if c["id"] == lembrado),
        next((i for i, c in enumerate(colecoes) if c.get("default")), 0)
    )

    escolhido = st.selectbox(
        rotulo,
        options=range(len(colecoes)),
        index=padrao,
        format_func=lambda i: f"{colecoes[i]['nome']}  ·  {colecoes[i]['id']}",
        key=chave
    )

    # os widgets perdem o estado quando a página muda; a escolha fica guardada à parte
    st.session_state["acervo_escolhido"] = colecoes[escolhido]["id"]

    return colecoes[escolhido]


def salvar_upload(arquivo):
    """Grava um arquivo enviado pelo navegador em data/uploads e devolve o caminho."""

    PASTA_UPLOADS.mkdir(parents=True, exist_ok=True)

    nome = re.sub(r"[^\w.\- ]+", "_", arquivo.name)
    destino = PASTA_UPLOADS / f"{uuid.uuid4().hex[:8]}_{nome}"

    with open(destino, "wb") as f:
        f.write(arquivo.getbuffer())

    return destino


def listar_entrada(extensoes):
    """Arquivos soltos na pasta data/entrada (para lotes grandes, sem enviar pelo navegador)."""

    PASTA_ENTRADA.mkdir(parents=True, exist_ok=True)

    return sorted(
        p for p in PASTA_ENTRADA.iterdir()
        if p.is_file() and p.suffix.lower() in extensoes
    )


def enfileirar(tipo, titulo, params, colecao_id):
    """Cria a tarefa, garante que o worker está rodando e devolve o id."""

    tarefa_id = tarefas.criar(tipo, titulo, params, colecao_id=colecao_id)
    tarefas.garantir_worker()

    return tarefa_id


def aviso_enfileirado(quantidade=1):

    st.success(
        f"{quantidade} tarefa(s) na fila. Acompanhe na aba **Tarefas**; "
        "pode continuar usando o sistema enquanto elas rodam."
    )


def inteiro_br(n):

    return f"{int(n):,}".replace(",", ".")


def tamanho_legivel(bytes_):

    for unidade in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidade == "GB":
            return f"{bytes_:.0f} {unidade}" if unidade == "B" else f"{bytes_:.1f} {unidade}"
        bytes_ /= 1024
