"""
Catálogo de acervos (data/colecoes.json): criar, editar, definir padrão e remover.

Só mexe no arquivo. Apagar a coleção no Qdrant é outro passo (a tela faz os dois,
com confirmação).
"""

import json
import os
import re
from pathlib import Path

from ingestao import parametros as P

ARQUIVO_PADRAO = Path(__file__).resolve().parents[1] / "data" / "colecoes.json"

_RE_ID = re.compile(r"^[a-z0-9][a-z0-9_]{2,59}$")
_RE_ID_EXISTENTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,99}$")


def _caminho(arquivo):

    return Path(arquivo or ARQUIVO_PADRAO)


def ler(arquivo=None):
    """Lista de acervos. Sem o arquivo, devolve lista vazia."""

    caminho = _caminho(arquivo)

    if not caminho.exists():
        return []

    dados = json.loads(caminho.read_text(encoding="utf-8"))

    return list(dados.get("colecoes") or [])


def salvar(colecoes, arquivo=None):
    """Grava de forma atômica (arquivo temporário + troca), para não corromper."""

    caminho = _caminho(arquivo)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(
        json.dumps({"colecoes": colecoes}, ensure_ascii=False, indent=4),
        encoding="utf-8"
    )
    os.replace(temporario, caminho)


def sugerir_id(nome):
    """'Olavo de Carvalho' -> 'acervo_olavo_de_carvalho'."""

    from ingestao.pipeline import slug

    return f"acervo_{slug(nome)}"[:60]


def validar_id(colecao_id, existente=False):
    """existente=True: aceita o nome de uma coleção que já existe no Qdrant (qualquer caixa)."""

    if existente and _RE_ID_EXISTENTE.match(colecao_id or ""):
        return

    if not _RE_ID.match(colecao_id or ""):
        raise ValueError(
            "O ID deve ter de 3 a 60 caracteres: letras minúsculas sem acento, "
            "números e _ (sublinhado)."
        )


def obter(colecao_id, arquivo=None):

    for c in ler(arquivo):
        if c["id"] == colecao_id:
            return c

    return None


def padrao(arquivo=None):

    for c in ler(arquivo):
        if c.get("default") is True:
            return c

    return None


def criar(colecao_id, nome, descricao="", autor="", embedding_model=None, arquivo=None, existente=False):

    colecao_id = (colecao_id or "").strip()
    nome = (nome or "").strip()

    validar_id(colecao_id, existente)

    if not nome:
        raise ValueError("Informe o nome do acervo.")

    if embedding_model and embedding_model not in P.MODELOS_EMBEDDING:
        raise ValueError(f"Modelo de embedding desconhecido: {embedding_model}")

    colecoes = ler(arquivo)

    if any(c["id"] == colecao_id for c in colecoes):
        raise ValueError(f"Já existe um acervo com o ID '{colecao_id}'.")

    novo = {
        "id": colecao_id,
        "nome": nome,
        "descricao": (descricao or "").strip(),
        "default": not colecoes,          # o primeiro acervo vira o padrão
        "autor": (autor or "").strip() or nome,
        "embedding_model": embedding_model or P.MODELO_PADRAO,
    }

    colecoes.append(novo)
    salvar(colecoes, arquivo)

    return novo


def editar(colecao_id, nome=None, descricao=None, autor=None, arquivo=None):
    """O ID e o modelo de embedding não mudam: os vetores já gravados dependem deles."""

    colecoes = ler(arquivo)

    for c in colecoes:

        if c["id"] != colecao_id:
            continue

        if nome is not None:

            if not nome.strip():
                raise ValueError("O nome não pode ficar vazio.")

            c["nome"] = nome.strip()

        if descricao is not None:
            c["descricao"] = descricao.strip()

        if autor is not None:
            c["autor"] = autor.strip() or c["nome"]

        salvar(colecoes, arquivo)

        return c

    raise ValueError(f"Acervo '{colecao_id}' não encontrado.")


def definir_padrao(colecao_id, arquivo=None):

    colecoes = ler(arquivo)

    if not any(c["id"] == colecao_id for c in colecoes):
        raise ValueError(f"Acervo '{colecao_id}' não encontrado.")

    for c in colecoes:
        c["default"] = c["id"] == colecao_id

    salvar(colecoes, arquivo)


def remover(colecao_id, arquivo=None):
    """Tira do catálogo. O acervo padrão não pode ser removido."""

    colecoes = ler(arquivo)

    alvo = next((c for c in colecoes if c["id"] == colecao_id), None)

    if alvo is None:
        raise ValueError(f"Acervo '{colecao_id}' não encontrado.")

    if alvo.get("default"):
        raise ValueError(
            "O acervo padrão não pode ser excluído. Defina outro como padrão antes."
        )

    salvar([c for c in colecoes if c["id"] != colecao_id], arquivo)


def orfas(nomes_no_qdrant, arquivo=None):
    """Coleções que existem no Qdrant mas não estão no catálogo."""

    cadastradas = {c["id"] for c in ler(arquivo)}

    return sorted(n for n in nomes_no_qdrant if n not in cadastradas)
