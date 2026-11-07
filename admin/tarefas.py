"""
Tarefas em segundo plano.

Ingestões longas (centenas de vídeos, Whisper em áudio de 1h) não podem rodar
dentro da tela do Streamlit: qualquer clique reinicia o script. Aqui cada
tarefa é um arquivo JSON em data/tarefas/ e um processo separado (o "worker",
admin/worker.py) executa a fila, uma tarefa por vez.

Regras que evitam conflito entre a tela e o worker:
  - só o worker grava o JSON da tarefa depois de criada;
  - o pedido de cancelamento é um arquivo à parte (<id>.cancelar);
  - o log é outro arquivo (<id>.log), só com acréscimos.

Status: fila -> executando -> concluida | erro | cancelada
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA_PADRAO = RAIZ / "data" / "tarefas"

STATUS_ATIVOS = ("fila", "executando")
STATUS_FINAIS = ("concluida", "erro", "cancelada")

LIMITE_BATIDA = 60        # segundos sem sinal de vida = worker considerado morto
INTERVALO_BATIDA = 5


class Cancelado(Exception):
    """A tarefa foi cancelada pelo usuário."""


def _pasta(pasta):

    pasta = Path(pasta or PASTA_PADRAO)
    pasta.mkdir(parents=True, exist_ok=True)

    return pasta


def _agora():

    return datetime.now().isoformat(timespec="seconds")


def _gravar_json(caminho, dados):

    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


# ------------------------------------------------------------
# CRIAR, LER, LISTAR
# ------------------------------------------------------------

def criar(tipo, titulo, params, colecao_id=None, pasta=None):
    """Põe uma tarefa na fila e devolve o id."""

    pasta = _pasta(pasta)
    tarefa_id = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid.uuid4().hex[:4]}"

    _gravar_json(pasta / f"{tarefa_id}.json", {
        "id": tarefa_id,
        "tipo": tipo,
        "titulo": titulo,
        "colecao_id": colecao_id,
        "params": params,
        "status": "fila",
        "criada_em": _agora(),
        "iniciada_em": None,
        "finalizada_em": None,
        "progresso": {"fase": "", "atual": 0, "total": 0, "mensagem": ""},
        "resultado": None,
        "erro": None,
    })

    return tarefa_id


def ler(tarefa_id, pasta=None):

    caminho = _pasta(pasta) / f"{tarefa_id}.json"

    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def listar(pasta=None, limite=100):
    """Mais recentes primeiro."""

    tarefas = []

    for caminho in sorted(_pasta(pasta).glob("*.json"), reverse=True)[:limite]:

        try:
            tarefas.append(json.loads(caminho.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue

    return tarefas


def contar_ativas(pasta=None):

    return sum(1 for t in listar(pasta) if t["status"] in STATUS_ATIVOS)


def ler_log(tarefa_id, pasta=None, linhas=200):

    caminho = _pasta(pasta) / f"{tarefa_id}.log"

    if not caminho.exists():
        return ""

    return "\n".join(caminho.read_text(encoding="utf-8", errors="replace").splitlines()[-linhas:])


def remover(tarefa_id, pasta=None):
    """Apaga uma tarefa finalizada (e seu log). Tarefas ativas não são removidas."""

    pasta = _pasta(pasta)
    tarefa = ler(tarefa_id, pasta)

    if tarefa and tarefa["status"] in STATUS_ATIVOS:
        raise ValueError("Cancele a tarefa antes de removê-la.")

    for sufixo in (".json", ".log", ".cancelar"):
        (pasta / f"{tarefa_id}{sufixo}").unlink(missing_ok=True)


def limpar_finalizadas(pasta=None):
    """Remove todas as tarefas finalizadas. Devolve quantas."""

    total = 0

    for tarefa in listar(pasta, limite=100000):
        if tarefa["status"] in STATUS_FINAIS:
            remover(tarefa["id"], pasta)
            total += 1

    return total


# ------------------------------------------------------------
# CANCELAMENTO
# ------------------------------------------------------------

def pedir_cancelamento(tarefa_id, pasta=None):

    (_pasta(pasta) / f"{tarefa_id}.cancelar").write_text(_agora(), encoding="utf-8")


def cancelamento_pedido(tarefa_id, pasta=None):

    return (_pasta(pasta) / f"{tarefa_id}.cancelar").exists()


# ------------------------------------------------------------
# WORKER: CONTROLE DE VIDA
# ------------------------------------------------------------

def _arquivo_trava(pasta):

    return _pasta(pasta) / "worker.lock"


def _pid_vivo(pid):

    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True

    return True


def worker_ativo(pasta=None):
    """True se há um worker vivo (processo existe e deu sinal recentemente)."""

    trava = _arquivo_trava(pasta)

    try:
        pid = trava.read_text(encoding="utf-8").strip()
        idade = time.time() - trava.stat().st_mtime
    except (FileNotFoundError, OSError):
        return False

    return _pid_vivo(pid) and idade < LIMITE_BATIDA


def adquirir_trava(pasta=None):
    """O worker chama ao iniciar. Devolve False se já existe outro vivo."""

    trava = _arquivo_trava(pasta)

    for _ in range(2):

        try:
            descritor = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:

            if worker_ativo(pasta):
                return False

            trava.unlink(missing_ok=True)      # trava de um worker morto
            continue

        with os.fdopen(descritor, "w") as arquivo:
            arquivo.write(str(os.getpid()))

        return True

    return False


def bater_coracao(pasta=None):

    try:
        os.utime(_arquivo_trava(pasta))
    except OSError:
        pass


def liberar_trava(pasta=None):

    trava = _arquivo_trava(pasta)

    try:
        if trava.read_text(encoding="utf-8").strip() == str(os.getpid()):
            trava.unlink(missing_ok=True)
    except OSError:
        pass


def garantir_worker(pasta=None, comando=None):
    """
    Inicia o worker se houver tarefa na fila e nenhum worker vivo.
    Devolve True quando iniciou um novo.
    """

    if worker_ativo(pasta):
        return False

    if not any(t["status"] == "fila" for t in listar(pasta)):
        return False

    comando = comando or [sys.executable, "-m", "admin.worker"]
    registro = open(_pasta(pasta) / "worker.log", "a", encoding="utf-8")

    env = dict(os.environ)

    if pasta:
        env["TAREFAS_PASTA"] = str(pasta)

    subprocess.Popen(
        comando,
        cwd=str(RAIZ),
        stdout=registro,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,       # sobrevive ao reinício do script do Streamlit
        env=env
    )

    return True
