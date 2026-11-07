"""
Worker da fila de tarefas:  python -m admin.worker

Executa uma tarefa por vez (o Ollama e o Whisper já usam a máquina inteira) e
encerra sozinho depois de alguns segundos sem trabalho.
"""

import os
import threading
import time
import traceback
from pathlib import Path

from . import tarefas
from .tarefas import Cancelado


ROTULO_FASE = {
    "chunking": "dividindo em trechos",
    "lendo_pdf": "lendo o PDF",
    "embeddings": "gerando vetores",
    "gravando": "gravando no banco",
    "reparando": "reparando",
    "whisper": "transcrevendo áudio",
}


class Contexto:
    """O que o executor usa para informar progresso, escrever no log e checar cancelamento."""

    def __init__(self, tarefa, pasta):

        self.tarefa = tarefa
        self.pasta = pasta
        self._ultimo = 0.0
        self._cancelado = False
        self._geral = None

    # --- progresso -------------------------------------------------
    def progresso(self, fase, atual, total, mensagem=None, forcar=False):
        """Grava no máximo duas vezes por segundo (evita escrever a cada chunk)."""

        agora = time.time()
        final = total and atual >= total

        if not (forcar or final or agora - self._ultimo >= 0.5):
            return

        self._ultimo = agora

        anterior = self.tarefa["progresso"]

        self.tarefa["progresso"] = {
            "fase": fase,
            "atual": atual,
            "total": total,
            "mensagem": mensagem if mensagem is not None else anterior.get("mensagem", ""),
        }

        self._salvar()

    def geral(self, fase, atual, total, mensagem):
        """
        Progresso do conjunto ("Arquivo 3 de 40"). Enquanto estiver definido, os avisos
        de cada etapa interna (sub) aparecem junto dele, sem apagar a contagem.
        """

        self._geral = {"fase": fase, "atual": atual, "total": total, "mensagem": mensagem}
        self.progresso(fase, atual, total, mensagem, forcar=True)

    def sub(self, fase, atual, total, texto=None):
        """Etapa interna do item atual (gerando vetores, gravando, transcrevendo...)."""

        rotulo = texto or ROTULO_FASE.get(fase, fase)

        if total and total > 1 and not texto:
            rotulo += f" ({atual}/{total})"

        fim = bool(total) and atual >= total

        if self._geral is None:
            self.progresso(fase, atual, total, rotulo[:1].upper() + rotulo[1:], forcar=fim)
            return

        g = self._geral
        fracao = min(atual / total, 1.0) if total else 0.0

        self.progresso(
            g["fase"], g["atual"] + fracao, g["total"], f"{g['mensagem']} — {rotulo}", forcar=fim
        )

    def mensagem(self, texto):
        """Muda só a mensagem (ex.: 'Vídeo 3 de 40: título')."""

        p = self.tarefa["progresso"]
        self.progresso(p["fase"], p["atual"], p["total"], texto, forcar=True)

    def callback_pipeline(self):
        """Adapta (fase, atual, total) do pipeline de ingestão."""

        return lambda fase, atual, total: (self.verificar(), self.sub(fase, atual, total))

    # --- log -------------------------------------------------------
    def log(self, texto):

        caminho = Path(self.pasta) / f"{self.tarefa['id']}.log"

        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"{time.strftime('%H:%M:%S')}  {texto}\n")

    # --- cancelamento ----------------------------------------------
    def cancelado(self):

        if not self._cancelado:
            self._cancelado = tarefas.cancelamento_pedido(self.tarefa["id"], self.pasta)

        return self._cancelado

    def verificar(self):
        """Levanta Cancelado se o usuário pediu para parar."""

        if self.cancelado():
            raise Cancelado()

    # --- interno ---------------------------------------------------
    def _salvar(self):

        tarefas._gravar_json(Path(self.pasta) / f"{self.tarefa['id']}.json", self.tarefa)


def _finalizar(ctx, status, resultado=None, erro=None):

    ctx.tarefa["status"] = status
    ctx.tarefa["finalizada_em"] = tarefas._agora()
    ctx.tarefa["resultado"] = resultado
    ctx.tarefa["erro"] = erro

    ctx._salvar()


def executar_tarefa(tarefa, pasta, executores):
    """Roda uma tarefa e grava o desfecho. Nunca levanta exceção."""

    ctx = Contexto(tarefa, pasta)

    if ctx.cancelado():
        _finalizar(ctx, "cancelada")
        return

    executor = executores.get(tarefa["tipo"])

    tarefa["status"] = "executando"
    tarefa["iniciada_em"] = tarefas._agora()
    ctx._salvar()

    if executor is None:
        ctx.log(f"Tipo de tarefa desconhecido: {tarefa['tipo']}")
        _finalizar(ctx, "erro", erro=f"Tipo de tarefa desconhecido: {tarefa['tipo']}")
        return

    try:
        resultado = executor(tarefa["params"], ctx)

    except Cancelado:
        ctx.log("Cancelada pelo usuário.")
        _finalizar(ctx, "cancelada")

    except Exception as e:

        # o Whisper tem a sua própria exceção de cancelamento
        if type(e).__name__ == "Cancelado":
            ctx.log("Cancelada pelo usuário.")
            _finalizar(ctx, "cancelada")
            return

        ctx.log(traceback.format_exc())
        _finalizar(ctx, "erro", erro=f"{type(e).__name__}: {e}")

    else:
        _finalizar(ctx, "concluida", resultado=resultado)


def recuperar_orfas(pasta):
    """Quem estava 'executando' quando o worker anterior morreu não vai terminar."""

    for t in tarefas.listar(pasta, limite=100000):

        if t["status"] == "executando":

            t["status"] = "erro"
            t["erro"] = "Interrompida (o processo foi encerrado antes do fim). Pode ser repetida."
            t["finalizada_em"] = tarefas._agora()

            tarefas._gravar_json(Path(pasta) / f"{t['id']}.json", t)


def _proxima(pasta):

    na_fila = [t for t in tarefas.listar(pasta, limite=100000) if t["status"] == "fila"]

    return min(na_fila, key=lambda t: t["id"]) if na_fila else None


def executar_fila(pasta=None, executores=None, ocioso_max=30, espera=1.0):
    """Processa a fila até ficar ocioso por 'ocioso_max' segundos. Devolve quantas rodou."""

    pasta = tarefas._pasta(pasta)

    if executores is None:
        from .executores import EXECUTORES as executores

    if not tarefas.adquirir_trava(pasta):
        return 0

    parar = threading.Event()

    def batimento():
        while not parar.wait(tarefas.INTERVALO_BATIDA):
            tarefas.bater_coracao(pasta)

    threading.Thread(target=batimento, daemon=True).start()

    rodadas = 0

    try:
        recuperar_orfas(pasta)

        ocioso_desde = time.time()

        while True:

            tarefa = _proxima(pasta)

            if tarefa:
                executar_tarefa(tarefa, pasta, executores)
                rodadas += 1
                ocioso_desde = time.time()
                continue

            if time.time() - ocioso_desde >= ocioso_max:
                break

            time.sleep(espera)

    finally:
        parar.set()
        tarefas.liberar_trava(pasta)

    # uma tarefa pode ter entrado entre a última checagem e a liberação da trava
    if _proxima(pasta):
        rodadas += executar_fila(pasta, executores, ocioso_max, espera)

    return rodadas


if __name__ == "__main__":

    executar_fila(
        os.getenv("TAREFAS_PASTA") or None,
        ocioso_max=float(os.getenv("WORKER_OCIOSO", "30"))
    )
