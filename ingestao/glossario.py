"""
Glossário de nomes por acervo.

  nomes      -> lista de nomes próprios; vão como dica ("initial_prompt") para o Whisper.
  correcoes  -> {"grafia errada": "grafia certa"}; aplicadas depois de qualquer
                transcrição (YouTube ou Whisper) antes de gerar os chunks.

Fica em data/glossarios.json.
"""

import json
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parents[1] / "data" / "glossarios.json"


def _ler(arquivo):

    arquivo = Path(arquivo or ARQUIVO_PADRAO)

    if not arquivo.exists():
        return {}

    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def carregar(colecao_id, arquivo=None):

    dados = _ler(arquivo).get(colecao_id) or {}

    return {
        "nomes": list(dados.get("nomes") or []),
        "correcoes": dict(dados.get("correcoes") or {}),
    }


def salvar(colecao_id, nomes, correcoes, arquivo=None):

    arquivo = Path(arquivo or ARQUIVO_PADRAO)
    dados = _ler(arquivo)

    dados[colecao_id] = {
        "nomes": [n.strip() for n in nomes if n and n.strip()],
        "correcoes": {
            str(k).strip(): str(v).strip()
            for k, v in correcoes.items()
            if k and str(k).strip() and v and str(v).strip()
        },
    }

    arquivo.parent.mkdir(parents=True, exist_ok=True)

    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arquivo)


def prompt_whisper(nomes, limite=40):
    """Frase curta com os nomes, usada como initial_prompt do Whisper."""

    if not nomes:
        return None

    return "Nomes citados: " + ", ".join(nomes[:limite]) + "."
