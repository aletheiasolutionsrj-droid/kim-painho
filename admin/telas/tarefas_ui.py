"""Aba Tarefas: fila, progresso, cancelamento e resultados."""

import streamlit as st

from admin import tarefas
from admin.executores import ROTULOS

ICONES = {"fila": "⏳", "executando": "⚙️", "concluida": "✅", "erro": "❌", "cancelada": "⛔"}
NOMES = {"fila": "Na fila", "executando": "Em andamento", "concluida": "Concluída",
         "erro": "Com erro", "cancelada": "Cancelada"}


def descrever_resultado(tipo, r):
    """Texto (markdown) com o resumo do que a tarefa fez."""

    if not r:
        return ""

    linhas = []

    if tipo == "legendas_youtube":
        linhas.append(f"{r['na_lista']} vídeo(s) na lista (links e canal).")
        linhas.append(
            f"**{r['inseridos']}** vídeo(s) incluído(s) ({r['chunks']} trechos) · "
            f"{r['ja_existiam']} já estavam no acervo · {r['whisper']} transcrito(s) pelo Whisper"
            + (f" · {r['traduzidos']} traduzido(s) para o português" if r.get("traduzidos") else "")
            + (f" ({r['titulos_traduzidos']} título(s) também)" if r.get("titulos_traduzidos") else "")
        )
        if r["sem_legenda"]:
            linhas.append(
                f"**{len(r['sem_legenda'])}** sem legenda no YouTube — veja *Adicionar conteúdo → Vídeos sem legenda*."
            )
        if r["bloqueado"]:
            linhas.append(
                f"⚠️ O YouTube bloqueou este IP; faltaram **{r['restantes']}** vídeo(s). "
                "Espere cerca de 6 horas e clique em **Retomar**: os já incluídos são ignorados."
            )
        for video_id, erro in r["falhas"][:20]:
            linhas.append(f"- falha em `{video_id}`: {erro}")

    elif tipo == "importar_legendas":
        linhas.append(
            f"**{r['inseridos']}** de {r['total']} arquivo(s) incluído(s) ({r['chunks']} trechos) · "
            f"{r['ja_existiam']} já estavam no acervo"
            + (f" · {r['json_salvos']} convertido(s) para JSON" if r["json_salvos"] else "")
        )
        for nome, erro in r["falhas"][:30]:
            linhas.append(f"- `{nome}`: {erro}")

    elif tipo in ("pdf", "transcricao_arquivo", "transcrever_audio"):
        estado = {"inserido": "incluído", "ja_existe": "já existia (marque 'substituir' para reprocessar)",
                  "vazio": "sem texto aproveitável"}.get(r.get("status"), r.get("status"))
        linhas.append(f"Documento `{r.get('doc_id')}`: {estado} — {r.get('chunks', 0)} trechos.")

    elif tipo == "reparar_metadados":
        linhas.append(f"{r['reparados']} de {r['pendentes']} vídeo(s) reparado(s).")
        for video_id, erro in r["falhas"][:20]:
            linhas.append(f"- falha em `{video_id}`: {erro}")

    elif tipo == "backup":
        linhas.append(f"Arquivo `{r['nome']}` ({r['size'] / (1024 * 1024):.1f} MB) em `{r['caminho']}`.")

    elif tipo == "restaurar_snapshot":
        linhas.append(f"{r['pontos']:,} pontos restaurados.".replace(",", "."))

    else:
        linhas.append(f"`{r}`")

    return "\n\n".join(linhas)


def _cartao(t):

    status = t["status"]
    prog = t["progresso"]
    rotulo = ROTULOS.get(t["tipo"], t["tipo"])

    with st.container(border=True):

        topo, botoes = st.columns([5, 2])

        topo.markdown(
            f"{ICONES[status]} **{t['titulo']}**  \n"
            f"<small>{rotulo} · {NOMES[status]} · criada {t['criada_em'].replace('T', ' ')}"
            f"{' · acervo ' + t['colecao_id'] if t.get('colecao_id') else ''}</small>",
            unsafe_allow_html=True
        )

        if status in tarefas.STATUS_ATIVOS:
            if botoes.button("Cancelar", key=f"cancelar_{t['id']}"):
                tarefas.pedir_cancelamento(t["id"])
                st.toast("Cancelamento pedido. A tarefa para no próximo ponto seguro.")
        else:
            c1, c2 = botoes.columns(2)

            bloqueada = status == "concluida" and bool((t.get("resultado") or {}).get("bloqueado"))

            if (status in ("erro", "cancelada") or bloqueada) and c1.button(
                "▶️ Retomar" if bloqueada else "Repetir", key=f"{'retomar' if bloqueada else 'repetir'}_{t['id']}"
            ):
                tarefas.criar(t["tipo"], t["titulo"], t["params"], colecao_id=t.get("colecao_id"))
                tarefas.garantir_worker()
                st.rerun()

            if c2.button("Remover", key=f"remover_{t['id']}"):
                tarefas.remover(t["id"])
                st.rerun()

        if status == "executando":
            total = prog.get("total") or 0
            fracao = min(prog.get("atual", 0) / total, 1.0) if total else 0.0
            st.progress(min(fracao, 1.0), text=prog.get("mensagem") or prog.get("fase") or "Trabalhando...")

        if status == "fila" and tarefas.cancelamento_pedido(t["id"]):
            st.caption("Cancelamento pedido; será descartada ao chegar a vez.")

        if status == "concluida":
            texto = descrever_resultado(t["tipo"], t.get("resultado"))
            if texto:
                st.markdown(texto)

        if status == "erro":
            st.error(t.get("erro") or "Erro desconhecido.")

        log = tarefas.ler_log(t["id"])

        if log:
            with st.expander("Registro detalhado"):
                st.code(log, language=None)


def _painel():

    tarefas.garantir_worker()          # se algo ficou na fila e o worker morreu, reinicia

    lista = tarefas.listar(limite=60)

    ativas = sum(1 for t in lista if t["status"] in tarefas.STATUS_ATIVOS)

    if not lista:
        st.info("Nenhuma tarefa ainda. As ingestões que você iniciar aparecem aqui.")
        return

    st.caption(
        f"{ativas} em andamento ou na fila · "
        + ("processador ativo" if tarefas.worker_ativo() else "processador parado (inicia sozinho quando há fila)")
    )

    for t in lista:
        _cartao(t)


def render():

    c1, c2 = st.columns([1, 1])

    if c1.button("🔄 Atualizar", key="atualizar_tarefas"):
        st.rerun()

    if c2.button("🧹 Remover tarefas finalizadas", key="limpar_tarefas"):
        st.toast(f"{tarefas.limpar_finalizadas()} tarefa(s) removida(s).")
        st.rerun()

    # Com tarefa ativa, atualiza sozinho a cada 2 s (só este bloco recarrega, não a página inteira).
    try:
        st.fragment(run_every=2 if tarefas.contar_ativas() else None)(_painel)()
    except TypeError:
        _painel()
