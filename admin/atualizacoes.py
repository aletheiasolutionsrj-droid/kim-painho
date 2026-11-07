"""
Atualização automática: canais do YouTube vinculados a um acervo.

Uma vez por dia, na primeira vez em que o site é aberto, cada atualização ativa gera uma tarefa que
inclui os vídeos novos do canal (os já cadastrados são ignorados). Arquivo: data/atualizacoes.json.
"""

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path

from admin import tarefas

ARQUIVO_PADRAO = Path(__file__).resolve().parents[1] / "data" / "atualizacoes.json"

LIMITE_PADRAO = 100        # vídeos novos por execução: protege contra o bloqueio de IP do YouTube


def _caminho(arquivo):

    return Path(arquivo or ARQUIVO_PADRAO)


def ler(arquivo=None):

    caminho = _caminho(arquivo)

    if not caminho.exists():
        return []

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    return dados if isinstance(dados, list) else []


def salvar(itens, arquivo=None):

    caminho = _caminho(arquivo)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def obter(atualizacao_id, arquivo=None):

    return next((a for a in ler(arquivo) if a["id"] == atualizacao_id), None)


def criar(colecao_id, canal_url, nome=None, limite=LIMITE_PADRAO, incluir_lives=False, incluir_shorts=False,
          traduzir_de=None, traduzir_titulo=False, arquivo=None):

    canal_url = (canal_url or "").strip()

    if not colecao_id:
        raise ValueError("Escolha o acervo.")

    from ingestao import youtube

    if not youtube.eh_canal_ou_playlist(canal_url):
        raise ValueError("Informe o link de um canal ou playlist (ex.: https://www.youtube.com/@nome).")

    itens = ler(arquivo)

    if any(a["colecao_id"] == colecao_id and a["canal_url"] == canal_url for a in itens):
        raise ValueError("Este canal já está cadastrado para este acervo.")

    novo = {
        "id": uuid.uuid4().hex[:8],
        "nome": (nome or "").strip() or canal_url,
        "colecao_id": colecao_id,
        "canal_url": canal_url,
        "ativa": True,
        "limite": int(limite) if limite else None,
        "incluir_lives": bool(incluir_lives),
        "incluir_shorts": bool(incluir_shorts),
        "traduzir_de": list(traduzir_de) if traduzir_de else None,
        "traduzir_titulo": bool(traduzir_de and traduzir_titulo),
        "criada_em": datetime.now().isoformat(timespec="seconds"),
        "ultima_data": None,           # dia (AAAA-MM-DD) em que a última tarefa foi criada
        "ultima_tarefa": None,
    }

    itens.append(novo)
    salvar(itens, arquivo)

    return novo


def definir_ativa(atualizacao_id, ativa, arquivo=None):

    itens = ler(arquivo)

    for a in itens:
        if a["id"] == atualizacao_id:
            a["ativa"] = bool(ativa)

    salvar(itens, arquivo)


def remover(atualizacao_id, arquivo=None):

    salvar([a for a in ler(arquivo) if a["id"] != atualizacao_id], arquivo)


def _tarefa_ativa(atualizacao_id, pasta=None):

    return any(
        t["status"] in tarefas.STATUS_ATIVOS and (t.get("params") or {}).get("atualizacao_id") == atualizacao_id
        for t in tarefas.listar(pasta, limite=200)
    )


def criar_tarefa(a, pasta=None, arquivo=None, hoje=None):
    """Cria a tarefa de atualização e registra o dia. Devolve o id da tarefa."""

    params = {
        "colecao_id": a["colecao_id"], "canal_url": a["canal_url"], "limite": a.get("limite"),
        "incluir_lives": a.get("incluir_lives", False), "incluir_shorts": a.get("incluir_shorts", False),
        "traduzir_de": a.get("traduzir_de"), "traduzir_titulo": a.get("traduzir_titulo", False),
        "atualizacao_id": a["id"],
    }

    tarefa_id = tarefas.criar(
        "legendas_youtube", f"Atualização automática: {a['nome']}", params,
        colecao_id=a["colecao_id"], pasta=pasta
    )

    itens = ler(arquivo)

    for item in itens:
        if item["id"] == a["id"]:
            item["ultima_data"] = (hoje or date.today()).isoformat()
            item["ultima_tarefa"] = tarefa_id

    salvar(itens, arquivo)

    return tarefa_id


def executar_pendentes(pasta=None, arquivo=None, hoje=None):
    """
    Cria a tarefa de cada atualização ativa que ainda não rodou hoje (e não tem tarefa em andamento).
    Devolve a lista de ids de tarefas criadas. Chamar de novo no mesmo dia não cria nada.
    """

    hoje = hoje or date.today()
    criadas = []

    for a in ler(arquivo):

        if not a.get("ativa") or a.get("ultima_data") == hoje.isoformat():
            continue

        if _tarefa_ativa(a["id"], pasta):
            continue

        criadas.append(criar_tarefa(a, pasta, arquivo, hoje))

    if criadas:
        tarefas.garantir_worker()

    return criadas


def verificar_na_sessao(estado, hoje=None, **kw):
    """
    Para chamar ao abrir uma página: confere uma vez por sessão e por dia (estado = st.session_state).
    Nunca levanta erro: uma falha aqui não pode derrubar a página.
    """

    hoje = hoje or date.today()

    if estado.get("atualizacao_verificada_em") == hoje.isoformat():
        return []

    try:
        criadas = executar_pendentes(hoje=hoje, **kw)
    except Exception:
        return []

    estado["atualizacao_verificada_em"] = hoje.isoformat()

    return criadas
