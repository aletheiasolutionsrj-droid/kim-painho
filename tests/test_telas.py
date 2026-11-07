"""
Testes das telas de administração com um Streamlit de mentira (tests/fake_streamlit.py).

Uso (dentro de src/):   python tests/test_telas.py
"""

import runpy
import sys
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(AQUI))

import fake_streamlit                                              # noqa: E402

st = fake_streamlit.instalar()

import test_admin as ta                                            # noqa: E402
from fake_streamlit import ArquivoEnviado, Parar                   # noqa: E402

from admin import atualizacoes, catalogo, executores, pendencias, tarefas, worker    # noqa: E402
from admin.telas import (                                          # noqa: E402
    acervos, adicionar, atualizacao_ui, backup_ui, comum, documentos, saude_ui, tarefas_ui
)
from ingestao import glossario                                     # noqa: E402
from ingestao.armazenamento import Armazenamento                   # noqa: E402


class QdrantDaTela(ta.FakeQdrant):
    """FakeQdrant com o que as telas usam além da ingestão."""

    def get_collections(self):
        return types.SimpleNamespace(collections=[types.SimpleNamespace(name=n) for n in self.colecoes])

    def delete_collection(self, collection_name):
        del self.colecoes[collection_name]


def montar():
    """Ambiente isolado: catálogo, tarefas, uploads, deps falsas. Devolve (dir, deps)."""

    d, falsas = ta.ambiente()

    falsas.q = QdrantDaTela()
    comum.qdrant = lambda: falsas.q

    catalogo.ARQUIVO_PADRAO = d / "colecoes.json"
    atualizacoes.ARQUIVO_PADRAO = d / "atualizacoes.json"
    tarefas.PASTA_PADRAO = d / "tarefas"
    comum.PASTA_UPLOADS = d / "uploads"
    comum.PASTA_ENTRADA = d / "entrada"

    catalogo.criar("acervo_kim", "Kim Paim", "vídeos", embedding_model="nomic-embed-text")
    catalogo.criar("acervo_atlas", "Atlas", autor="Kim Paim")

    # os testes não dependem de o faster-whisper estar instalado na máquina
    adicionar.whisper.disponivel = lambda: False

    iniciados = []
    tarefas.garantir_worker = lambda *a, **k: iniciados.append(1) or False
    falsas.iniciados = iniciados

    st.reset()
    st.session_state.clear()

    return d, falsas


def tela(pagina):
    """Renderiza uma página (módulo com render() ou função); st.rerun()/st.stop() só interrompem."""

    try:
        (pagina.render if hasattr(pagina, "render") else pagina)()
    except Parar:
        pass


def rodar_fila():

    worker.executar_fila(tarefas.PASTA_PADRAO, executores.EXECUTORES, ocioso_max=0, espera=0.01)


def tarefas_criadas():

    return sorted(tarefas.listar(), key=lambda t: t["id"])


def srt(n=80):

    return "\n".join(
        f"{i + 1}\n00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900\n"
        f"Fala número {i} sobre geopolítica e história do Brasil contemporâneo.\n"
        for i in range(n)
    ).encode()


# ============================================================

def teste_pagina_inteira_abre_sem_erro():

    d, f = montar()

    runpy.run_path(str(RAIZ / "pages" / "1_Administracao.py"))

    titulos = st.textos("title")
    assert any("Acervos cadastrados" in t for t in titulos), titulos
    assert "Voltar ao Oráculo" in st.textos("button")


def teste_senha_de_administrador():

    import os

    d, f = montar()
    os.environ["ADMIN_PASSWORD"] = "segredo"

    try:
        try:
            comum.exigir_senha()
            raise AssertionError("deveria parar")
        except Parar:
            pass

        st.session_state["admin_liberado"] = True
        comum.exigir_senha()            # liberado: segue
    finally:
        del os.environ["ADMIN_PASSWORD"]


def teste_criar_editar_padrao_e_excluir_acervo():

    d, f = montar()

    st.valores.update({"novo_nome": "Olavo de Carvalho", "novo_modelo": "bge-m3", "novo_autor": ""})
    st.cliques.add("Criar acervo")
    tela(acervos.pagina_novo)

    novo = catalogo.obter("acervo_olavo_de_carvalho")
    assert novo and novo["embedding_model"] == "bge-m3" and novo["autor"] == "Olavo de Carvalho"
    assert f.q.colecoes["acervo_olavo_de_carvalho"]["dim"] == 1024
    assert "video_id" in f.q.colecoes["acervo_olavo_de_carvalho"]["indices"]

    # erro: nome repetido gera o mesmo ID
    st.reset()
    st.valores.update({"novo_nome": "Olavo de Carvalho"})
    st.cliques.add("Criar acervo")
    tela(acervos.pagina_novo)
    assert any("Já existe" in e for e in st.textos("error"))

    # editar (acervo índice 1 = Atlas)
    st.reset()
    st.valores.update({"gerenciar_acervo": 1, "ed_nome_acervo_atlas": "Atlas Brasileiro", "ed_autor_acervo_atlas": "Kim"})
    st.cliques.add("Salvar alterações")
    tela(acervos.pagina_gerenciar)
    assert catalogo.obter("acervo_atlas")["nome"] == "Atlas Brasileiro"
    assert catalogo.obter("acervo_atlas")["autor"] == "Kim"

    # tornar padrão
    st.reset()
    st.valores["gerenciar_acervo"] = 1
    st.cliques.add("padrao_acervo_atlas")
    tela(acervos.pagina_gerenciar)
    assert catalogo.padrao()["id"] == "acervo_atlas"

    # excluir: o padrão é protegido; um acervo comum só com o ID digitado
    st.reset()
    st.valores["gerenciar_acervo"] = 1
    st.cliques.add("del_acervo_atlas")
    tela(acervos.pagina_gerenciar)
    assert catalogo.obter("acervo_atlas")

    f.q.create_collection("acervo_kim", types.SimpleNamespace(size=768))
    st.reset()
    st.valores.update({"gerenciar_acervo": 0, "conf_del_acervo_kim": "errado"})
    st.cliques.add("del_acervo_kim")
    tela(acervos.pagina_gerenciar)
    assert catalogo.obter("acervo_kim") and "acervo_kim" in f.q.colecoes

    st.reset()
    st.valores.update({"gerenciar_acervo": 0, "conf_del_acervo_kim": "acervo_kim"})
    st.cliques.add("del_acervo_kim")
    tela(acervos.pagina_gerenciar)
    assert catalogo.obter("acervo_kim") is None and "acervo_kim" not in f.q.colecoes


def teste_colecao_orfa_e_glossario():

    d, f = montar()

    f.q.create_collection("NOME_ATLAS", types.SimpleNamespace(size=1024))

    st.cliques.add("orfa_cad_NOME_ATLAS")
    tela(acervos.pagina_lista)

    c = catalogo.obter("NOME_ATLAS") or {}
    assert c.get("embedding_model") == "bge-m3", c          # modelo deduzido pela dimensão

    # glossário
    import pandas as pd

    st.reset()
    st.valores["gl_nomes_acervo_kim"] = "Kim Paim\nOlavo de Carvalho"
    st.hook_editor = lambda df, key: pd.DataFrame(
        [{"Grafia errada": "kim pain", "Grafia certa": "Kim Paim"}, {"Grafia errada": "", "Grafia certa": ""}]
    ) if key and key.startswith("gl_corr") else df
    st.cliques.add("gl_salvar_acervo_kim")
    tela(acervos.pagina_glossario)

    g = glossario.carregar("acervo_kim")
    assert g["nomes"] == ["Kim Paim", "Olavo de Carvalho"]
    assert g["correcoes"] == {"kim pain": "Kim Paim"}


def teste_youtube_pela_tela_ate_o_resultado():

    d, f = montar()

    st.valores["yt_links"] = (
        "https://youtu.be/AAAAAAAAAAA\nBBBBBBBBBBB\nhttps://www.youtube.com/@umcanal\nlixo qualquer"
    )
    st.valores["yt_lives"] = True
    f.canal = [{"video_id": "CANAL000001", "titulo": "do canal"}]
    st.cliques.add("yt_go")
    tela(adicionar.pagina_youtube)

    assert any("Não reconheci" in w for w in st.textos("warning"))

    criadas = tarefas_criadas()
    assert [t["tipo"] for t in criadas] == ["legendas_youtube", "legendas_youtube"]
    assert [i["video_id"] for i in criadas[0]["params"]["itens"]] == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
    assert criadas[1]["params"]["canal_url"].endswith("@umcanal")
    assert criadas[1]["params"]["incluir_lives"] is True and criadas[1]["params"]["incluir_shorts"] is False
    assert f.iniciados, "o worker deveria ter sido acionado"

    rodar_fila()

    assert len(f.q.payloads("acervo_kim")) > 0

    st.reset()
    tela(tarefas_ui)
    texto = " ".join(st.textos("markdown"))
    assert "vídeo(s) incluído(s)" in texto and "2" in texto


def teste_pdf_pela_tela():

    d, f = montar()

    arq = ArquivoEnviado("Atlas Brasileiro - Janeiro de 2026 final.pdf", b"%PDF-1.4 fake")
    st.valores.update({"pdf_up": [arq], "pdf_modo": "A capa (e outras páginas iniciais) não têm número", "pdf_capa": 2})
    st.cliques.add("pdf_go")
    tela(adicionar.pagina_pdf)

    t = tarefas_criadas()[0]
    p = t["params"]

    assert t["tipo"] == "pdf" and Path(p["caminho"]).read_bytes() == b"%PDF-1.4 fake"
    assert p["edicao"] == "Janeiro de 2026" and p["data_publicacao"] == "2026-01-01"
    assert p["paginas_sem_numero"] == 2 and p["guardar_copia"] and p["apagar_origem"]

    # data digitada errada: nada é enfileirado
    st.reset()
    import shutil
    shutil.rmtree(tarefas.PASTA_PADRAO)
    st.valores.update({"pdf_up": [arq], "pdf_d_0_" + arq.name: "01/01/2026"})
    st.cliques.add("pdf_go")
    tela(adicionar.pagina_pdf)
    assert tarefas_criadas() == [] and any("Data inválida" in e for e in st.textos("error"))


def teste_podcast_transcricao_pronta_e_audio_sem_whisper():

    d, f = montar()

    st.valores["pod_up"] = [ArquivoEnviado("true_outspeak_12.srt", srt())]
    st.cliques.add("pod_go")
    tela(adicionar.pagina_podcast)

    t = tarefas_criadas()[0]
    assert t["tipo"] == "transcricao_arquivo"
    assert t["params"]["titulo"] == "true outspeak 12" and t["params"]["episodio"] == 12

    rodar_fila()
    assert tarefas.ler(t["id"])["status"] == "concluida", tarefas.ler(t["id"])
    assert f.q.payloads("acervo_kim")[0]["tipo_fonte"] == "podcast"

    # áudio sem Whisper instalado: avisa e não enfileira
    st.reset()
    antes = len(tarefas_criadas())
    st.valores["pod_up"] = [ArquivoEnviado("ep.mp3", b"mp3")]
    st.cliques.add("pod_go")
    tela(adicionar.pagina_podcast)
    assert len(tarefas_criadas()) == antes
    assert any("Whisper não está instalado" in w for w in st.textos("warning"))


def teste_audio_com_whisper_disponivel_vai_para_a_fila():

    d, f = montar()
    adicionar.whisper.disponivel = lambda: True

    st.valores["pod_up"] = [ArquivoEnviado("ep9.mp3", b"mp3")]
    st.valores["pod_modelo"] = "small"
    st.cliques.add("pod_go")
    tela(adicionar.pagina_podcast)

    t = tarefas_criadas()[0]
    assert t["tipo"] == "transcrever_audio" and t["params"]["modelo_whisper"] == "small"
    assert t["params"]["episodio"] == 9 and Path(t["params"]["caminho_audio"]).read_bytes() == b"mp3"


def teste_podcast_pasta_de_entrada_nao_apaga_originais():

    d, f = montar()

    (d / "entrada").mkdir()
    arquivo = d / "entrada" / "ep3.srt"
    arquivo.write_bytes(srt())

    st.valores["pod_origem"] = "Pasta data/entrada"
    st.valores["pod_pasta"] = [arquivo]
    st.cliques.add("pod_go")
    tela(adicionar.pagina_podcast)

    t = tarefas_criadas()[0]
    assert t["params"]["apagar_origem"] is False and t["params"]["caminho"] == str(arquivo)

    rodar_fila()
    assert arquivo.exists()


def teste_videos_sem_legenda_pela_tela():

    d, f = montar()

    pendencias.registrar("acervo_kim", "CCCCCCCCCCC", "Sem legenda")

    st.valores["pend_sel"] = ["CCCCCCCCCCC"]
    st.cliques.add("pend_retry")
    tela(adicionar.pagina_sem_legenda)

    t = tarefas_criadas()[0]
    assert t["params"]["reavaliar_pendentes"] is True and t["params"]["itens"] == [{"video_id": "CCCCCCCCCCC"}]


def teste_documentos_listar_editar_e_excluir():

    d, f = montar()

    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [
        {"video_id": "AAAAAAAAAAA"}, {"video_id": "BBBBBBBBBBB"}]})

    def marcar(ids):
        def hook(df, key):
            df = df.copy()
            df["Selecionar"] = df["ID"].isin(ids)
            return df
        return hook

    # editar um
    st.hook_editor = marcar({"AAAAAAAAAAA"})
    st.valores.update({"doc_titulo_AAAAAAAAAAA": "Novo título", "doc_data_AAAAAAAAAAA": "2020-01-02"})
    st.cliques.add("Salvar")
    tela(documentos)

    pls = [p for p in f.q.payloads("acervo_kim") if p["doc_id"] == "AAAAAAAAAAA"]
    assert all(p["titulo"] == "Novo título" and p["data_publicacao"] == "2020-01-02" for p in pls)

    # data inválida é recusada
    st.reset()
    st.hook_editor = marcar({"AAAAAAAAAAA"})
    st.valores.update({"doc_data_AAAAAAAAAAA": "ontem"})
    st.cliques.add("Salvar")
    tela(documentos)
    assert any("Data inválida" in e for e in st.textos("error"))

    # excluir sem confirmação não apaga; com "APAGAR" apaga só o selecionado
    st.reset()
    st.hook_editor = marcar({"BBBBBBBBBBB"})
    st.cliques.add("docs_del")
    tela(documentos)
    assert any(p["doc_id"] == "BBBBBBBBBBB" for p in f.q.payloads("acervo_kim"))

    st.reset()
    st.hook_editor = marcar({"BBBBBBBBBBB"})
    st.valores["docs_conf_0"] = "APAGAR"
    st.cliques.add("docs_del")
    tela(documentos)

    restantes = {p["doc_id"] for p in f.q.payloads("acervo_kim")}
    assert restantes == {"AAAAAAAAAAA"}

    # filtro por título
    st.reset()
    st.hook_editor = None
    st.valores["docs_busca"] = "nada disso"
    tela(documentos)
    assert any("Nenhum documento" in i for i in st.textos("info"))


def teste_documentos_datas_filtros_selecao_em_lote_e_exclusao():

    from datetime import date

    d, f = montar()

    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [
        {"video_id": "AAAAAAAAAAA"}, {"video_id": "BBBBBBBBBBB"}]})

    # documentos "antigos": indexados antes de existir a data de processamento (ex.: conteúdo do Olavo por engano)
    pontos = f.q.colecoes["acervo_kim"]["pontos"]

    for i in range(3):
        pontos[1000 + i] = ([0.1] * 8, {"doc_id": f"olavo{i}", "tipo_fonte": "video", "titulo": f"Olavo aula {i}",
                                         "data_publicacao": "2015-01-01", "texto_bruto": "x", "chunk_index": 0})
        pontos[2000 + i] = ([0.1] * 8, {"doc_id": f"olavo{i}", "tipo_fonte": "video", "titulo": f"Olavo aula {i}",
                                         "data_publicacao": "2015-01-01", "texto_bruto": "y", "chunk_index": 1})

    visto = {}

    def espia(df, key):
        visto["df"] = df
        return df

    # colunas novas e datas
    st.hook_editor = espia
    tela(documentos)

    df = visto["df"]
    assert list(df.columns) == documentos.COLUNAS
    novo = df[df["ID"] == "AAAAAAAAAAA"].iloc[0]
    assert novo["Processado em"].startswith(date.today().isoformat()) and len(novo["Processado em"]) == 16
    assert df[df["ID"] == "olavo0"].iloc[0]["Processado em"] == ""

    # filtros por data de processamento
    for filtro, esperado in (("Hoje", {"AAAAAAAAAAA", "BBBBBBBBBBB"}),
                             ("Últimos 7 dias", {"AAAAAAAAAAA", "BBBBBBBBBBB"}),
                             ("Sem data de processamento", {"olavo0", "olavo1", "olavo2"})):
        st.reset()
        st.hook_editor = espia
        st.valores["docs_processado"] = filtro
        tela(documentos)
        assert set(visto["df"]["ID"]) == esperado, (filtro, set(visto["df"]["ID"]))

    # busca + "Selecionar todos os listados" (pede rerun com a seleção marcada)
    st.reset()
    st.hook_editor = espia
    st.valores["docs_busca"] = "olavo"
    st.cliques.add("docs_sel_todos")
    tela(documentos)

    assert st.session_state["docs_marcar_todos"] is True

    # sem a confirmação, nada é apagado
    st.reset()
    st.hook_editor = espia
    st.valores["docs_busca"] = "olavo"
    st.cliques.add("docs_del")
    tela(documentos)
    assert bool(visto["df"]["Selecionar"].all()) and len(visto["df"]) == 3
    assert len([p for p in f.q.payloads("acervo_kim") if p["doc_id"].startswith("olavo")]) == 6

    # com APAGAR: some só o filtrado, com todos os trechos
    st.reset()
    st.hook_editor = espia
    st.valores.update({"docs_busca": "olavo", "docs_conf_0": "APAGAR"})
    st.cliques.add("docs_del")
    tela(documentos)

    assert {p["doc_id"] for p in f.q.payloads("acervo_kim")} == {"AAAAAAAAAAA", "BBBBBBBBBBB"}
    assert "3 documento(s) e 6 trecho(s)" in st.session_state["docs_aviso"]
    assert st.session_state["docs_exclusoes"] == 1 and st.session_state["docs_marcar_todos"] is False

    # a próxima tela mostra o aviso uma vez e a confirmação recomeça vazia (chave nova)
    st.reset()
    st.hook_editor = espia
    tela(documentos)
    assert any("3 documento(s) e 6 trecho(s)" in s for s in st.textos("success"))
    assert "docs_aviso" not in st.session_state
    assert not visto["df"]["Selecionar"].any()


def teste_documentos_lista_atualiza_sozinha_quando_uma_tarefa_termina():

    d, f = montar()

    visto = {}

    def espia(df, key):
        visto["ids"] = set(df["ID"])
        return df

    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [{"video_id": "AAAAAAAAAAA"}]})

    st.hook_editor = espia
    tela(documentos)
    assert visto["ids"] == {"AAAAAAAAAAA"}
    assert any("Lista lida do banco às" in c for c in st.textos("caption"))

    # nova tarefa termina: a lista acompanha, sem clicar em Recarregar (o defeito do "só 30 documentos")
    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [{"video_id": "BBBBBBBBBBB"}]})

    st.reset()
    st.hook_editor = espia
    tela(documentos)
    assert visto["ids"] == {"AAAAAAAAAAA", "BBBBBBBBBBB"}

    # mudança no banco SEM tarefa continua em cache até o botão ser usado
    f.q.colecoes["acervo_kim"]["pontos"][9999] = ([0.1] * 8, {"doc_id": "extra", "tipo_fonte": "video",
                                                           "titulo": "x", "texto_bruto": "x", "chunk_index": 0})
    st.reset()
    st.hook_editor = espia
    tela(documentos)
    assert "extra" not in visto["ids"]

    st.reset()
    st.hook_editor = espia
    st.cliques.add("docs_reload")
    tela(documentos)                                         # pede rerun
    st.reset()
    st.hook_editor = espia
    tela(documentos)
    assert "extra" in visto["ids"]


def teste_reparar_datas_pela_tela():

    d, f = montar()

    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [{"video_id": "AAAAAAAAAAA"}]})
    for pl in f.q.payloads("acervo_kim"):
        pl["data_publicacao"] = None

    st.cliques.add("docs_reparar")
    tela(documentos)

    assert tarefas_criadas()[-1]["tipo"] == "reparar_metadados"


def teste_painel_de_tarefas():

    d, f = montar()

    ids = {
        s: tarefas.criar("backup", f"tarefa {s}", {"colecao_id": "acervo_kim"}, colecao_id="acervo_kim")
        for s in ("fila", "executando", "concluida", "erro", "cancelada")
    }

    for s in ("executando", "concluida", "erro", "cancelada"):
        dados = tarefas.ler(ids[s])
        dados["status"] = s
        dados["progresso"] = {"fase": "x", "atual": 3, "total": 10, "mensagem": "Vídeo 3 de 10"}
        if s == "concluida":
            dados["resultado"] = {"nome": "a.snapshot", "size": 5 * 1024 * 1024, "caminho": "/x/a.snapshot"}
        if s == "erro":
            dados["erro"] = "RuntimeError: x"
        tarefas._gravar_json(tarefas.PASTA_PADRAO / f"{ids[s]}.json", dados)

    tela(tarefas_ui)

    assert "Vídeo 3 de 10" in st.textos("progress")
    assert any("a.snapshot" in m for m in st.textos("markdown"))
    assert any("RuntimeError" in e for e in st.textos("error"))
    assert f.iniciados                      # há fila e nenhum worker: a tela pede para iniciar

    # cancelar uma ativa
    st.reset()
    st.cliques.add(f"cancelar_{ids['executando']}")
    tela(tarefas_ui)
    assert tarefas.cancelamento_pedido(ids["executando"])

    # repetir a que deu erro
    st.reset()
    st.cliques.add(f"repetir_{ids['erro']}")
    tela(tarefas_ui)
    assert len(tarefas.listar()) == 6

    # remover a concluída
    st.reset()
    st.cliques.add(f"remover_{ids['concluida']}")
    tela(tarefas_ui)
    assert tarefas.ler(ids["concluida"]) is None

    # limpar finalizadas
    st.reset()
    st.cliques.add("limpar_tarefas")
    tela(tarefas_ui)
    assert all(t["status"] in tarefas.STATUS_ATIVOS for t in tarefas.listar())


def teste_saude_e_indices():

    d, f = montar()

    Armazenamento(f.q, "acervo_kim").garantir_colecao(8)      # coleção sem índices

    st.cliques.add("saude_go")
    tela(saude_ui)

    assert any("Faltam índices" in w for w in st.textos("warning")), st.saidas

    # clique REAL no botão de correção: só ele é pressionado (o diagnóstico já está na sessão)
    st.reset()
    st.cliques.add("saude_indices")
    tela(saude_ui)
    assert "texto_bruto" in f.q.colecoes["acervo_kim"]["indices"], "o botão de correção não agiu"
    assert "Índices criados" in st.session_state["saude_aviso"]

    st.reset()
    tela(saude_ui)                                           # a recarga mostra o aviso e o novo diagnóstico
    assert any("Índices criados" in s for s in st.textos("success"))
    assert any("Todos os índices" in s for s in st.textos("success"))

    # com dados: contadores
    ta.rodar(d, "legendas_youtube", {"colecao_id": "acervo_kim", "itens": [{"video_id": "AAAAAAAAAAA"}]})
    st.reset()
    st.cliques.add("saude_go")
    tela(saude_ui)
    assert any("Todos os índices" in s for s in st.textos("success"))
    assert any("Trechos sem texto: 0" in s for s in st.textos("success"))


def teste_backup_e_restauracao_pela_tela():

    d, f = montar()

    st.cliques.add("backup_go")
    tela(backup_ui.pagina_backup)
    assert tarefas_criadas()[0]["tipo"] == "backup"

    # restauração: só em acervo vazio
    Armazenamento(f.q, "acervo_atlas").garantir_colecao(8)

    st.reset()
    st.valores.update({
        "restore_arq": ArquivoEnviado("atlas.snapshot", b"snap"),
        "restore_conf": True,
        "restore_destino": 0,
    })
    st.cliques.add("restore_go")
    tela(backup_ui.pagina_restore)

    t = [x for x in tarefas_criadas() if x["tipo"] == "restaurar_snapshot"][0]
    assert t["params"]["colecao_id"] == "acervo_atlas" and Path(t["params"]["caminho"]).read_bytes() == b"snap"

    # sem confirmação, não enfileira
    st.reset()
    antes = len(tarefas_criadas())
    st.valores.update({"restore_arq": ArquivoEnviado("atlas.snapshot", b"snap"), "restore_conf": False})
    st.cliques.add("restore_go")
    tela(backup_ui.pagina_restore)
    assert len(tarefas_criadas()) == antes


def teste_app_so_tem_o_link():

    texto = (RAIZ / "app.py").read_text(encoding="utf-8")

    assert "pages/1_Administracao.py" in texto
    for sumiu in ("renderizar_modal_manutencao", "renderizar_modal_ingestao", "Alimentar o Oráculo",
                  "ferramenta_manutencao", "criar_backup_qdrant"):
        assert sumiu not in texto, sumiu


def teste_menu_percorre_todas_as_paginas():

    d, f = montar()
    pagina = str(RAIZ / "pages" / "1_Administracao.py")

    menu = runpy.run_path(pagina)["MENU"]

    visitadas = []

    for grupo, conteudo in menu:

        itens = [(grupo, None, grupo)] if callable(conteudo) else [(grupo, i, f"{grupo}_{i}") for i, _ in conteudo]

        for g, item, sufixo in itens:

            st.cliques = {f"menu_{sufixo}" if item else f"menu_{g}"}

            try:
                runpy.run_path(pagina)
            except Parar:
                pass                                   # a troca de página pede um rerun

            st.cliques = set()
            st.saidas.clear()
            runpy.run_path(pagina)

            assert any((item or g) in t for t in st.textos("title")), (g, item, st.textos("title"))
            visitadas.append(item or g)

    assert len(visitadas) == 14 and "Atualização automática" in " ".join(visitadas) and "Restore" in " ".join(visitadas) and "Podcast e áudio" in visitadas

    # os 4 itens de Acervos e os 4 de Adicionar aparecem como botões do menu
    botoes = " | ".join(st.textos("button"))
    for esperado in ("Novo acervo", "Glossário de nomes", "Vídeos do YouTube", "Vídeos sem legenda", "Documentos"):
        assert esperado in botoes, esperado


def teste_pagina_de_atualizacao_automatica():

    d, f = montar()

    # link que não é de canal: recusado
    st.valores.update({"atu_canal": "https://youtu.be/AAAAAAAAAAA"})
    st.cliques.add("atu_criar")
    tela(atualizacao_ui.render)
    assert atualizacoes.ler() == [] and any("canal" in e for e in st.textos("error"))

    # cadastro
    st.reset()
    st.valores.update({"atu_canal": "https://www.youtube.com/@MundoAKV", "atu_nome": "Mundo AKV",
                       "atu_limite": 40, "atu_traduzir": True, "atu_idiomas": ["en"]})
    st.cliques.add("atu_criar")
    tela(atualizacao_ui.render)

    [a] = atualizacoes.ler()
    assert a["colecao_id"] == "acervo_kim" and a["limite"] == 40 and a["ativa"]
    assert a["traduzir_de"] == ["en"] and a["traduzir_titulo"]
    assert "Canal cadastrado" in st.session_state["atu_aviso"]

    # a lista mostra o canal; abrir o site cria a tarefa do dia
    st.reset()
    tela(atualizacao_ui.render)
    assert any("Mundo AKV" in t for t in st.textos("markdown"))

    assert len(atualizacoes.verificar_na_sessao(st.session_state)) == 1
    assert tarefas_criadas()[-1]["params"]["atualizacao_id"] == a["id"]

    # desativar, reativar
    st.reset()
    st.cliques.add(f"atu_alt_{a['id']}")
    tela(atualizacao_ui.render)
    assert atualizacoes.ler()[0]["ativa"] is False

    st.reset()
    st.cliques.add(f"atu_alt_{a['id']}")
    tela(atualizacao_ui.render)
    assert atualizacoes.ler()[0]["ativa"] is True

    # "atualizar agora" não empilha enquanto há tarefa em andamento
    antes = len(tarefas_criadas())
    st.reset()
    st.cliques.add(f"atu_agora_{a['id']}")
    tela(atualizacao_ui.render)
    assert len(tarefas_criadas()) == antes and "em andamento" in st.session_state["atu_aviso"]

    # excluir pede confirmação
    st.reset()
    st.cliques.add(f"atu_del_{a['id']}")
    tela(atualizacao_ui.render)
    assert st.session_state["atu_confirmar"] == a["id"] and len(atualizacoes.ler()) == 1

    st.reset()
    st.cliques.add(f"atu_del_ok_{a['id']}")
    tela(atualizacao_ui.render)
    assert atualizacoes.ler() == []


def teste_opcao_de_traduzir_chega_na_tarefa():

    d, f = montar()

    st.valores.update({"yt_links": "https://youtu.be/AAAAAAAAAAA", "yt_traduzir": True, "yt_idiomas": ["en", "es"]})
    st.cliques.add("yt_go")
    tela(adicionar.pagina_youtube)
    assert tarefas_criadas()[-1]["params"]["traduzir_de"] == ["en", "es"]
    assert tarefas_criadas()[-1]["params"]["traduzir_titulo"] is True      # marcado por padrão

    st.reset()
    st.valores.update({"yt_links": "https://youtu.be/AAAAAAAAAAA", "yt_traduzir": True, "yt_traduzir_titulo": False})
    st.cliques.add("yt_go")
    tela(adicionar.pagina_youtube)
    assert tarefas_criadas()[-1]["params"]["traduzir_titulo"] is False

    st.reset()
    st.valores.update({"yt_links": "https://youtu.be/BBBBBBBBBBB"})
    st.cliques.add("yt_go")
    tela(adicionar.pagina_youtube)
    assert tarefas_criadas()[-1]["params"]["traduzir_de"] is None
    assert tarefas_criadas()[-1]["params"]["traduzir_titulo"] is False


def teste_aviso_de_bloqueio_do_youtube_e_botao_retomar():

    d, f = montar()

    # link de vídeo avulso: sem aviso; link de canal: aviso
    st.valores["yt_links"] = "https://youtu.be/AAAAAAAAAAA"
    tela(adicionar.pagina_youtube)
    assert not any("bloquear" in w for w in st.textos("warning"))

    st.reset()
    st.valores["yt_links"] = "https://www.youtube.com/@MundoAKV"
    tela(adicionar.pagina_youtube)
    aviso = " ".join(st.textos("warning"))
    assert "bloquear" in aviso and "6 horas" in aviso and "Retomar" in aviso

    # tarefa que terminou bloqueada: aparece o botão Retomar, que recria a tarefa com os mesmos dados
    tid = tarefas.criar("legendas_youtube", "Canal: MundoAKV", {"colecao_id": "acervo_kim", "canal_url": "x"},
                        colecao_id="acervo_kim")
    dados = tarefas.ler(tid)
    dados["status"] = "concluida"
    dados["resultado"] = {"na_lista": 100, "inseridos": 40, "chunks": 1, "ja_existiam": 0, "sem_legenda": [],
                          "whisper": 0, "falhas": [], "bloqueado": True, "restantes": 60}
    tarefas._gravar_json(tarefas.PASTA_PADRAO / f"{tid}.json", dados)

    st.reset()
    st.cliques.add(f"retomar_{tid}")
    tela(tarefas_ui)

    novas = [x for x in tarefas.listar() if x["id"] != tid]
    assert len(novas) == 1 and novas[0]["params"]["canal_url"] == "x" and novas[0]["status"] == "fila"

    st.reset()
    tela(tarefas_ui)
    assert any("6 horas" in m for m in st.textos("markdown"))


def teste_clicar_no_grupo_abre_o_primeiro_item():

    d, f = montar()
    pagina = str(RAIZ / "pages" / "1_Administracao.py")

    for grupo, primeiro in (("📚 Acervos", "Acervos cadastrados"), ("➕ Adicionar conteúdo", "Vídeos do YouTube")):

        st.session_state.clear()
        st.cliques = {f"menugrupo_{grupo}"}

        try:
            runpy.run_path(pagina)
        except Parar:
            pass

        st.cliques = set()
        st.saidas.clear()
        runpy.run_path(pagina)

        assert any(primeiro in t for t in st.textos("title")), (grupo, st.textos("title"))

    # subitens recuados; itens de topo em negrito e sem recuo
    botoes = st.textos("button")
    assert any(b.startswith("\u00a0") and "Novo acervo" in b for b in botoes)
    assert any(b == "**🗂️ Documentos**" for b in botoes)


def teste_acervo_escolhido_e_lembrado_entre_paginas():

    d, f = montar()

    st.valores["adicionar_acervo"] = 1
    tela(adicionar.pagina_pdf)
    assert st.session_state["acervo_escolhido"] == "acervo_atlas"

    st.reset()
    tela(adicionar.pagina_podcast)                    # sem escolher de novo: continua no Atlas
    assert st.session_state["acervo_escolhido"] == "acervo_atlas"


def teste_documentos_mostra_todos_os_registros():

    d, f = montar()

    f.q.colecoes["acervo_kim"] = {"dim": 8, "indices": {}, "pontos": {
        i: ([0.1] * 8, {"doc_id": f"d{i:03d}", "tipo_fonte": "video", "titulo": f"T{i}",
                         "data_publicacao": "2024-01-01", "texto_bruto": "x", "chunk_index": 0})
        for i in range(2494)
    }}

    visto = []

    def espia(df, key):
        visto.append(len(df))
        return df

    st.hook_editor = espia
    tela(documentos)

    assert visto[-1] == 2494
    assert any("todos os 2.494" in m for m in st.textos("markdown")), st.textos("markdown")
    assert any("2.494" in m for m in st.textos("metric"))

    # filtro reduz a lista e a contagem acompanha
    st.reset()
    st.hook_editor = espia
    st.valores["docs_busca"] = "T10"
    tela(documentos)
    esperado = sum(1 for i in range(2494) if "t10" in f"T{i} d{i:03d}".lower())
    assert visto[-1] == esperado == 111


def teste_id_no_nome_do_arquivo():

    assert adicionar._id_no_nome("Aula sobre Brasileiros.srt") == ""
    assert adicionar._id_no_nome("Programa [Zz9-Yy8_Xw7].srt") == "Zz9-Yy8_Xw7"
    assert adicionar._id_no_nome("VpNM8BqK4Mk.json") == "VpNM8BqK4Mk"


def teste_importar_legendas_json_srt_vtt_com_formulario_e_conversao():

    import json
    import pandas as pd

    d, f = montar()
    comum.RAIZ = d                                     # a "pasta do projeto" passa a ser a temporária
    pasta = d / "legendas_json"
    pasta.mkdir()

    segs = ta.transcricao_sintetica(60)

    (pasta / "AAAAAAAAAAA.json").write_text(json.dumps(
        {"video_id": "AAAAAAAAAAA", "titulo": "Do arquivo", "data_publicacao": "2021-06-07",
         "origem_transcricao": "youtube", "transcript": segs}), encoding="utf-8")
    (pasta / "sem_id.json").write_text(json.dumps({"transcript": segs}), encoding="utf-8")
    (pasta / "programa [Zz9-Yy8_Xw7].srt").write_bytes(srt())
    (pasta / "outro.vtt").write_bytes(b"WEBVTT\n\n" + srt().replace(b",", b"."))
    (pasta / "leia.txt").write_text("ignorado")

    def preencher(df, key):
        if not (key or "").startswith("leg_tabela"):
            return df
        df = df.copy()
        for i, nome in enumerate(df["Arquivo"]):
            if nome == "sem_id.json":
                df.loc[i, "Link ou ID do vídeo"] = "https://youtu.be/BBBBBBBBBBB"
            if nome == "outro.vtt":
                df.loc[i, "Link ou ID do vídeo"] = "CCCCCCCCCCC"
                df.loc[i, "Título"] = "Aula digitada"
                df.loc[i, "Data"] = "2022-02-02"
        return df

    # 1) com linhas incompletas, nada é enfileirado
    st.hook_editor = None
    st.cliques.add("leg_go")
    tela(adicionar.pagina_youtube)
    assert tarefas_criadas() == []
    assert any("informe o link" in e for e in st.textos("error")), st.textos("error")
    assert "Precisam de dados (formulário): 3" in st.textos("metric")
    assert "Prontos para importar (.json com ID): 1" in st.textos("metric")

    # 2) formulário preenchido
    st.reset()
    st.hook_editor = preencher
    st.cliques.add("leg_go")
    tela(adicionar.pagina_youtube)

    t = tarefas_criadas()[0]
    assert t["tipo"] == "importar_legendas" and len(t["params"]["itens"]) == 4
    assert t["params"]["salvar_json"] == str(pasta.resolve()) and t["params"]["buscar_metadados"] is True

    rodar_fila()

    r = tarefas.ler(t["id"])
    assert r["status"] == "concluida", r
    assert r["resultado"]["inseridos"] == 4 and r["resultado"]["json_salvos"] == 3 and not r["resultado"]["falhas"]

    por_doc = {p["doc_id"]: p for p in f.q.payloads("acervo_kim")}
    assert set(por_doc) == {"AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "Zz9-Yy8_Xw7"}
    assert por_doc["AAAAAAAAAAA"]["titulo"] == "Do arquivo" and por_doc["AAAAAAAAAAA"]["data_publicacao"] == "2021-06-07"
    assert por_doc["CCCCCCCCCCC"]["titulo"] == "Aula digitada" and por_doc["CCCCCCCCCCC"]["data_publicacao"] == "2022-02-02"
    assert por_doc["BBBBBBBBBBB"]["titulo"] == "Título BBBBBBBBBBB"            # buscado no YouTube (falso)
    assert por_doc["Zz9-Yy8_Xw7"]["tipo_fonte"] == "video"

    convertido = json.loads((pasta / "CCCCCCCCCCC.json").read_text(encoding="utf-8"))
    assert convertido["video_id"] == "CCCCCCCCCCC" and convertido["titulo"] == "Aula digitada"
    assert len(convertido["transcript"]) == 80 and (pasta / "Zz9-Yy8_Xw7.json").exists()

    # 3) reimportar: tudo já existe
    st.reset()
    st.hook_editor = preencher
    st.cliques.add("leg_go")
    tela(adicionar.pagina_youtube)
    novo = tarefas_criadas()[-1]
    rodar_fila()
    r2 = tarefas.ler(novo["id"])["resultado"]
    # 4 originais + 3 .json convertidos que agora também estão na pasta: todos já existem
    assert r2["ja_existiam"] == 7 and r2["inseridos"] == 0 and not r2["falhas"]

    # 4) envio pelo navegador (apaga o arquivo temporário depois)
    st.reset()
    st.hook_editor = None
    st.valores["leg_origem"] = "Enviar pelo navegador"
    st.valores["leg_up"] = [ArquivoEnviado("[DDDDDDDDDDD].srt", srt())]
    st.cliques.add("leg_go")
    tela(adicionar.pagina_youtube)
    ultimo = tarefas_criadas()[-1]
    item = ultimo["params"]["itens"][0]
    assert item["video_id"] == "DDDDDDDDDDD" and item["apagar_origem"] is True and Path(item["caminho"]).exists()
    rodar_fila()
    assert not Path(item["caminho"]).exists()


def teste_importar_pasta_fora_do_projeto_e_recusada():

    d, f = montar()
    comum.RAIZ = d

    st.valores["leg_pasta"] = "../.."
    tela(adicionar.pagina_youtube)

    assert any("não encontrada" in w for w in st.textos("warning"))


# ============================================================

if __name__ == "__main__":

    testes = [(n, fn) for n, fn in sorted(globals().items()) if n.startswith("teste_")]
    falhas = 0

    for nome, func in testes:
        try:
            extra = func()
            print(f"  ok  {nome}" + (f"  [{extra}]" if extra else ""))
        except Exception as e:
            import traceback
            falhas += 1
            print(f"FALHOU {nome}: {type(e).__name__}: {e}")
            traceback.print_exc()

    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
