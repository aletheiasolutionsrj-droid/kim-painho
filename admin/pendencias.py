"""
Vídeos que ficaram sem legenda no YouTube, por acervo (data/pendencias.json).

Aparecem na tela "Adicionar conteúdo" para o usuário decidir: transcrever o
áudio com o Whisper (baixado do YouTube) ou enviar o mp3 por conta própria.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parents[1] / "data" / "pendencias.json"

_RE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _ler(arquivo):

    arquivo = Path(arquivo or ARQUIVO_PADRAO)

    if not arquivo.exists():
        return {}

    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _gravar(dados, arquivo):

    arquivo = Path(arquivo or ARQUIVO_PADRAO)
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, arquivo)


def listar(colecao_id, arquivo=None):
    """[{"video_id","titulo","motivo","data"}] em ordem de registro."""

    itens = _ler(arquivo).get(colecao_id) or {}

    # só IDs de vídeo reais (11 caracteres): descarta lixo de listagens antigas de canal
    return [dict(video_id=k, **v) for k, v in itens.items() if _RE_ID.match(k)]


def registrar(colecao_id, video_id, titulo=None, motivo="sem legenda", arquivo=None):

    dados = _ler(arquivo)

    dados.setdefault(colecao_id, {})[video_id] = {
        "titulo": titulo,
        "motivo": motivo,
        "data": datetime.now().strftime("%Y-%m-%d"),
    }

    _gravar(dados, arquivo)


def remover(colecao_id, video_id, arquivo=None):

    dados = _ler(arquivo)

    if video_id in (dados.get(colecao_id) or {}):
        del dados[colecao_id][video_id]
        _gravar(dados, arquivo)
