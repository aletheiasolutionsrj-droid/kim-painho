"""
Testes da página de Administração (sem Qdrant, Ollama, YouTube nem Whisper).

Uso (dentro de src/):   python tests/test_admin.py
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))

# reaproveita o Qdrant/embedder falsos (e instala o qdrant_client falso)
import test_ingestao as base                                       # noqa: E402
from test_ingestao import FakeEmbedder, FakeQdrant, transcricao_sintetica   # noqa: E402

from admin import catalogo, executores, pendencias, tarefas, worker   # noqa: E402
from ingestao import arquivos, fontes_texto, glossario, youtube       # noqa: E402
from ingestao.armazenamento import Armazenamento                      # noqa: E402


def pasta_temp():
    return Path(tempfile.mkdtemp(prefix="kim_admin_"))


# ============================================================
# CATÁLOGO
# ============================================================

def teste_catalogo_ciclo_completo():

    arq = pasta_temp() / "colecoes.json"

    a = catalogo.criar("acervo_kim", "Kim Paim", "vídeos", embedding_model="bge-m3", arquivo=arq)
    assert a["default"] is True and a["autor"] == "Kim Paim" and a["embedding_model"] == "bge-m3"

    b = catalogo.criar("acervo_olavo", "Olavo", autor="Olavo de Carvalho", arquivo=arq)
    assert b["default"] is False and b["embedding_model"] == "nomic-embed-text"

    for erro in [
        lambda: catalogo.criar("acervo_kim", "Outro", arquivo=arq),            # duplicado
        lambda: catalogo.criar("Ac Ervo", "x", arquivo=arq),                   # id inválido
        lambda: catalogo.criar("acervo_x", "", arquivo=arq),                   # sem nome
        lambda: catalogo.criar("acervo_x", "x", embedding_model="zzz", arquivo=arq),
        lambda: catalogo.remover("acervo_kim", arquivo=arq),                   # padrão protegido
        lambda: catalogo.remover("nao_existe", arquivo=arq),
    ]:
        try:
            erro()
        except ValueError:
            continue
        raise AssertionError("deveria ter recusado")

    catalogo.editar("acervo_olavo", nome="Olavo de Carvalho", descricao="palestras", arquivo=arq)
    assert catalogo.obter("acervo_olavo", arq)["nome"] == "Olavo de Carvalho"
    assert catalogo.obter("acervo_olavo", arq)["embedding_model"] == "nomic-embed-text"

    catalogo.definir_padrao("acervo_olavo", arq)
    assert catalogo.padrao(arq)["id"] == "acervo_olavo"
    assert sum(c["default"] for c in catalogo.ler(arq)) == 1

    catalogo.remover("acervo_kim", arq)
    assert [c["id"] for c in catalogo.ler(arq)] == ["acervo_olavo"]

    assert catalogo.orfas(["acervo_olavo", "NOME_ATLAS"], arq) == ["NOME_ATLAS"]
    assert catalogo.sugerir_id("Geografia em Foco!") == "acervo_geografia_em_foco"


def teste_pendencias_e_glossario():

    d = pasta_temp()
    arq = d / "pend.json"

    pendencias.registrar("c1", "AAAAAAAAAAA", "Título A", arquivo=arq)
    pendencias.registrar("c1", "BBBBBBBBBBB", "Título B", arquivo=arq)
    assert [p["video_id"] for p in pendencias.listar("c1", arq)] == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
    pendencias.remover("c1", "AAAAAAAAAAA", arq)
    assert [p["video_id"] for p in pendencias.listar("c1", arq)] == ["BBBBBBBBBBB"]
    assert pendencias.listar("outra", arq) == []

    g = d / "gl.json"
    glossario.salvar("c1", ["Olavo", " ", "Kim Paim"], {"olavo de cavalho": "Olavo de Carvalho", "": "x"}, g)
    lido = glossario.carregar("c1", g)
    assert lido["nomes"] == ["Olavo", "Kim Paim"]
    assert lido["correcoes"] == {"olavo de cavalho": "Olavo de Carvalho"}
    assert glossario.carregar("zzz", g) == {"nomes": [], "correcoes": {}}
    assert glossario.prompt_whisper(lido["nomes"]) == "Nomes citados: Olavo, Kim Paim."
    assert glossario.prompt_whisper([]) is None


# ============================================================
# LEITURA DE TRANSCRIÇÕES
# ============================================================

SRT = """1
00:00:01,000 --> 00:00:04,500
Olá, <i>bem-vindos</i>

2
00:01:05,250 --> 00:01:08,000
segunda linha
continuação
"""

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Primeira fala &amp; mais

01:02:03.500 --> 01:02:06.000 align:start
Depois de uma hora
"""


def teste_leitura_srt_vtt_json_txt():

    segs, tempo = fontes_texto.ler_transcricao("a.srt", SRT.encode())
    assert tempo and len(segs) == 2
    assert segs[0] == {"text": "Olá, bem-vindos", "start": 1.0, "duration": 3.5}
    assert segs[1]["start"] == 65.25 and segs[1]["text"] == "segunda linha continuação"

    segs, tempo = fontes_texto.ler_transcricao("a.vtt", VTT.encode())
    assert segs[0]["text"] == "Primeira fala & mais"
    assert segs[1]["start"] == 3723.5

    projeto = json.dumps({"video_id": "x", "transcript": [{"text": "a", "start": 2, "duration": 1}]})
    segs, tempo = fontes_texto.ler_transcricao("a.json", projeto.encode())
    assert tempo and segs[0]["start"] == 2

    whisper = json.dumps([{"text": " oi ", "start": 5.0, "end": 7.5}])
    segs, _ = fontes_texto.ler_transcricao("w.json", whisper.encode())
    assert segs[0]["duration"] == 2.5

    segs, tempo = fontes_texto.ler_transcricao("a.txt", "um\n\ndois".encode())
    assert not tempo and len(segs) == 2

    for nome, conteudo in [("a.doc", b"x"), ("a.srt", b"sem tempos aqui")]:
        try:
            fontes_texto.ler_transcricao(nome, conteudo)
        except ValueError:
            continue
        raise AssertionError(nome)


# ============================================================
# FILA DE TAREFAS
# ============================================================

def teste_fila_ordem_progresso_erro_e_cancelamento():

    pasta = pasta_temp()
    ordem = []

    def ok(params, ctx):
        ordem.append(params["n"])
        ctx.progresso("fase", 1, 2, "meio", forcar=True)
        ctx.log("fez algo")
        return {"n": params["n"]}

    def quebra(params, ctx):
        raise RuntimeError("deu ruim")

    def longa(params, ctx):
        for i in range(1000):
            ctx.verificar()
            time.sleep(0.01)
        return {}

    t1 = tarefas.criar("ok", "um", {"n": 1}, pasta=pasta)
    time.sleep(0.01)
    t2 = tarefas.criar("quebra", "dois", {}, pasta=pasta)
    time.sleep(0.01)
    t3 = tarefas.criar("ok", "três", {"n": 3}, pasta=pasta)
    time.sleep(0.01)
    t4 = tarefas.criar("longa", "quatro", {}, pasta=pasta)
    t5 = tarefas.criar("ok", "cancelada na fila", {"n": 5}, pasta=pasta)
    tarefas.pedir_cancelamento(t5, pasta)
    t6 = tarefas.criar("nao_existe", "tipo errado", {}, pasta=pasta)

    # cancela a "longa" enquanto roda
    threading.Timer(0.3, tarefas.pedir_cancelamento, args=(t4, pasta)).start()

    rodou = worker.executar_fila(
        pasta, {"ok": ok, "quebra": quebra, "longa": longa}, ocioso_max=0.2, espera=0.05
    )

    assert rodou == 6 and ordem == [1, 3], ordem

    r = {t: tarefas.ler(t, pasta) for t in (t1, t2, t3, t4, t5, t6)}
    assert r[t1]["status"] == "concluida" and r[t1]["resultado"] == {"n": 1}
    assert r[t1]["progresso"]["mensagem"] == "meio"
    assert "fez algo" in tarefas.ler_log(t1, pasta)
    assert r[t2]["status"] == "erro" and "deu ruim" in r[t2]["erro"]
    assert "Traceback" in tarefas.ler_log(t2, pasta)
    assert r[t4]["status"] == "cancelada"
    assert r[t5]["status"] == "cancelada"
    assert r[t6]["status"] == "erro" and "desconhecido" in r[t6]["erro"]

    assert not tarefas.worker_ativo(pasta)            # trava liberada
    assert tarefas.contar_ativas(pasta) == 0

    tarefas.remover(t1, pasta)
    assert tarefas.ler(t1, pasta) is None
    assert tarefas.limpar_finalizadas(pasta) == 5
    assert tarefas.listar(pasta) == []


def teste_trava_do_worker():

    pasta = pasta_temp()

    assert tarefas.adquirir_trava(pasta) is True
    assert tarefas.worker_ativo(pasta)
    assert tarefas.adquirir_trava(pasta) is False     # já existe um vivo (este processo)

    tarefas.liberar_trava(pasta)
    assert not tarefas.worker_ativo(pasta)

    # trava de worker morto é descartada
    (pasta / "worker.lock").write_text("999999")
    assert not tarefas.worker_ativo(pasta)
    assert tarefas.adquirir_trava(pasta) is True
    tarefas.liberar_trava(pasta)


def teste_tarefa_interrompida_e_marcada_como_erro():

    pasta = pasta_temp()
    t = tarefas.criar("ok", "x", {}, pasta=pasta)
    dados = tarefas.ler(t, pasta)
    dados["status"] = "executando"
    tarefas._gravar_json(pasta / f"{t}.json", dados)

    worker.executar_fila(pasta, {}, ocioso_max=0, espera=0.01)

    assert tarefas.ler(t, pasta)["status"] == "erro"
    assert "Interrompida" in tarefas.ler(t, pasta)["erro"]


def teste_worker_em_processo_separado():

    pasta = pasta_temp()
    t = tarefas.criar("tipo_inexistente", "x", {}, pasta=pasta)

    env = dict(os.environ, TAREFAS_PASTA=str(pasta), WORKER_OCIOSO="1")
    r = subprocess.run(
        [sys.executable, "-m", "admin.worker"],
        cwd=str(AQUI.parent), env=env, capture_output=True, text=True, timeout=60
    )

    assert r.returncode == 0, r.stderr
    assert tarefas.ler(t, pasta)["status"] == "erro"
    assert not tarefas.worker_ativo(pasta)

    # garantir_worker: só inicia se há fila, e usa a pasta informada
    assert tarefas.garantir_worker(pasta) is False          # nada na fila
    t2 = tarefas.criar("tipo_inexistente", "y", {}, pasta=pasta)
    assert tarefas.garantir_worker(pasta, [sys.executable, "-c", "import time; time.sleep(0)"]) is True
    assert tarefas.ler(t2, pasta)["status"] == "fila"


# ============================================================
# EXECUTORES
# ============================================================

class DepsFalsas:

    def __init__(self):
        self.q = FakeQdrant()
        self.emb = FakeEmbedder()
        self.sem_legenda = set()
        self.so_ingles = set()
        self.erro_legenda = {}
        self.metas = {}
        self.canal = []
        self.whisper_chamadas = []
        self.audios = []

    def qdrant(self): return self.q
    def embedder(self, colecao_id): return self.emb
    def pausa(self): pass

    def metadados(self, video_id):
        if video_id in self.erro_legenda and self.erro_legenda[video_id] == "meta":
            raise RuntimeError("falha de metadados")
        return self.metas.get(video_id, {"titulo": f"Título {video_id}", "data_publicacao": "2024-05-01"})

    def legenda(self, video_id, traduzir_de=None):
        if video_id in self.sem_legenda:
            raise youtube.LegendaIndisponivel(video_id)
        if video_id in self.so_ingles:
            if not traduzir_de:
                raise youtube.LegendaIndisponivel(video_id)
            self.traduzir_pedido = traduzir_de
            return transcricao_sintetica(60), "youtube:traduzido(en→pt)"
        erro = self.erro_legenda.get(video_id)
        if erro and erro != "meta":
            raise RuntimeError(erro)
        return transcricao_sintetica(60), "youtube"

    def listar_canal(self, url, abas=("videos",)):
        self.abas_pedidas = abas
        return list(self.canal)

    def traduzir_titulo(self, titulo):
        return "PT: " + titulo

    def audio(self, video_id, pasta):
        Path(pasta).mkdir(parents=True, exist_ok=True)
        caminho = Path(pasta) / f"{video_id}.webm"
        caminho.write_bytes(b"audio")
        self.audios.append(caminho)
        return caminho

    def transcrever(self, caminho, **kw):
        self.whisper_chamadas.append(kw)
        kw["progresso"](30, 60)
        return transcricao_sintetica(60)


def ambiente():
    """Isola todos os caminhos de dados e instala as dependências falsas."""

    d = pasta_temp()
    glossario.ARQUIVO_PADRAO = d / "glossarios.json"
    pendencias.ARQUIVO_PADRAO = d / "pendencias.json"
    executores.PASTA_TRANSCRICOES = d / "transcricoes"
    executores.PASTA_AUDIO_TEMP = d / "audio"
    arquivos.PASTA_PDFS = d / "pdfs"

    from admin import atualizacoes
    atualizacoes.ARQUIVO_PADRAO = d / "atualizacoes.json"

    falsas = DepsFalsas()
    executores.deps = falsas

    return d, falsas


def rodar(d, tipo, params):

    pasta = d / "tarefas"
    t = tarefas.criar(tipo, tipo, params, pasta=pasta)
    worker.executar_tarefa(tarefas.ler(t, pasta), pasta, executores.EXECUTORES)

    return tarefas.ler(t, pasta)


def teste_youtube_lote_pendencias_e_existentes():

    d, f = ambiente()
    f.sem_legenda = {"CCCCCCCCCCC"}
    f.erro_legenda = {"DDDDDDDDDDD": "erro qualquer"}

    itens = [{"video_id": v, "titulo": f"t{v}"} for v in
             ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD")]

    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": itens})
    r = t["resultado"]

    assert t["status"] == "concluida", t
    assert r["inseridos"] == 2 and r["sem_legenda"] == ["CCCCCCCCCCC"]
    assert r["falhas"][0][0] == "DDDDDDDDDDD"
    assert [p["video_id"] for p in pendencias.listar("c1")] == ["CCCCCCCCCCC"]

    pl = [p for p in f.q.payloads("c1") if p["doc_id"] == "AAAAAAAAAAA"][0]
    assert pl["titulo"] == "Título AAAAAAAAAAA" and pl["data_publicacao"] == "2024-05-01"

    # segunda rodada: os 2 existentes são ignorados; o sem legenda não é reprocessado
    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": itens})
    r = t["resultado"]
    assert r["ja_existiam"] == 2 and r["inseridos"] == 0
    assert "CCCCCCCCCCC" in r["sem_legenda"] and len(f.whisper_chamadas) == 0


def teste_youtube_canal_limite_e_bloqueio_de_ip():

    d, f = ambiente()
    f.canal = [{"video_id": f"V{i:010d}", "titulo": f"v{i}"} for i in range(5)]

    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "canal_url": "https://youtube.com/@x", "limite": 3})
    assert t["resultado"]["inseridos"] == 3 and t["resultado"]["na_lista"] == 5

    # agora o YouTube bloqueia
    def bloqueia(video_id):
        raise RuntimeError("YouTube is blocking requests from your IP")
    f.metadados = bloqueia

    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "canal_url": "https://youtube.com/@x"})
    r = t["resultado"]
    assert r["bloqueado"] is True and r["restantes"] == 2 and r["inseridos"] == 0


def teste_youtube_sem_legenda_com_whisper():

    d, f = ambiente()
    f.sem_legenda = {"CCCCCCCCCCC"}
    glossario.salvar("c1", ["Kim Paim"], {})

    t = rodar(d, "legendas_youtube", {
        "colecao_id": "c1", "itens": [{"video_id": "CCCCCCCCCCC", "titulo": "x"}],
        "whisper_se_faltar": True, "modelo_whisper": "small",
    })
    r = t["resultado"]

    assert r["whisper"] == 1 and r["inseridos"] == 1 and r["sem_legenda"] == []
    kw = f.whisper_chamadas[0]
    assert kw["modelo"] == "small" and "Kim Paim" in kw["prompt"] and kw["hotwords"] == "Kim Paim"
    assert not f.audios[0].exists()                                  # áudio temporário apagado
    assert (executores.PASTA_TRANSCRICOES / "CCCCCCCCCCC.json").exists()
    pl = f.q.payloads("c1")[0]
    assert pl["origem_transcricao"] == "whisper:small" and pl["tipo_fonte"] == "video"


def teste_youtube_cancelamento_no_meio():

    d, f = ambiente()
    itens = [{"video_id": f"V{i:010d}", "titulo": "x"} for i in range(4)]

    pasta = d / "tarefas"
    t = tarefas.criar("legendas_youtube", "x", {"colecao_id": "c1", "itens": itens}, pasta=pasta)

    original = f.legenda
    chamadas = []

    def legenda(video_id, traduzir_de=None):
        chamadas.append(video_id)
        if len(chamadas) == 2:
            tarefas.pedir_cancelamento(t, pasta)
        return original(video_id, traduzir_de)

    f.legenda = legenda
    worker.executar_tarefa(tarefas.ler(t, pasta), pasta, executores.EXECUTORES)

    r = tarefas.ler(t, pasta)
    assert r["status"] == "cancelada"
    assert len(f.q.payloads("c1")) > 0 and len(chamadas) < 4


def teste_transcricao_pronta_podcast_e_sem_tempo():

    d, f = ambiente()
    srt = d / "ep.srt"
    srt.write_text(SRT * 1, encoding="utf-8")

    # SRT curto demais vira 'vazio' (menos de 5 palavras por chunk não ocorre aqui); usa texto maior
    linhas = []
    for i in range(80):
        linhas.append(f"{i + 1}\n00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900\n"
                      f"Fala número {i} sobre geopolítica e história do Brasil contemporâneo.\n")
    srt.write_text("\n".join(linhas), encoding="utf-8")

    t = rodar(d, "transcricao_arquivo", {
        "colecao_id": "c1", "caminho": str(srt), "nome_original": "ep.srt", "tipo_fonte": "podcast",
        "titulo": "True Outspeak 12", "data_publicacao": "2021-03-04", "episodio": 12,
        "url": "https://exemplo.org/ep12", "apagar_origem": True,
    })

    assert t["status"] == "concluida" and t["resultado"]["status"] == "inserido", t
    assert not srt.exists()
    pl = f.q.payloads("c1")[0]
    assert pl["tipo_fonte"] == "podcast" and pl["doc_id"] == "true_outspeak_12"
    assert pl["episodio"] == 12 and pl["url"] == "https://exemplo.org/ep12"
    assert "video_id" not in pl and pl["timestamp_texto"]

    # sem marcação de tempo: recusa com explicação
    txt = d / "ep.txt"
    txt.write_text("só texto\n\nsem tempo", encoding="utf-8")
    t = rodar(d, "transcricao_arquivo", {
        "colecao_id": "c1", "caminho": str(txt), "nome_original": "ep.txt", "titulo": "Outro",
    })
    assert t["status"] == "erro" and "marcação de tempo" in t["erro"]

    # título vazio e sem doc_id: recusa
    srt.write_text("\n".join(linhas), encoding="utf-8")
    t = rodar(d, "transcricao_arquivo", {
        "colecao_id": "c1", "caminho": str(srt), "nome_original": "ep.srt", "titulo": "",
    })
    assert t["status"] == "erro"


def teste_audio_mp3_e_video_do_youtube_com_whisper():

    d, f = ambiente()
    mp3 = d / "ep.mp3"
    mp3.write_bytes(b"mp3")

    t = rodar(d, "transcrever_audio", {
        "colecao_id": "c1", "caminho_audio": str(mp3), "tipo_fonte": "podcast",
        "titulo": "Episódio 7", "episodio": 7, "modelo_whisper": "medium", "apagar_origem": True,
    })

    assert t["status"] == "concluida" and t["resultado"]["status"] == "inserido"
    assert t["resultado"]["segmentos"] == 60
    assert not mp3.exists()
    assert (executores.PASTA_TRANSCRICOES / "episodio_7.json").exists()
    assert t["progresso"]["fase"] in ("whisper", "gravando", "chunking", "embedding")

    # vídeo sem legenda: baixa o áudio, usa título/data do YouTube e tira da lista de pendências
    pendencias.registrar("c1", "CCCCCCCCCCC", "Sem legenda")
    t = rodar(d, "transcrever_audio", {"colecao_id": "c1", "video_id": "CCCCCCCCCCC"})

    assert t["status"] == "concluida", t
    pl = [p for p in f.q.payloads("c1") if p.get("doc_id") == "CCCCCCCCCCC"][0]
    assert pl["tipo_fonte"] == "video" and pl["video_id"] == "CCCCCCCCCCC"
    assert pl["titulo"] == "Título CCCCCCCCCCC" and pl["data_publicacao"] == "2024-05-01"
    assert pendencias.listar("c1") == []
    assert not f.audios[-1].exists()


def teste_pdf_pela_tarefa():

    atlas = os.getenv("ATLAS_PDF")

    if not atlas or not Path(atlas).exists():
        return "ignorado (defina ATLAS_PDF)"

    d, f = ambiente()
    copia = d / "up.pdf"
    copia.write_bytes(Path(atlas).read_bytes())

    t = rodar(d, "pdf", {
        "colecao_id": "c1", "caminho": str(copia), "titulo": "Atlas teste", "edicao": "Janeiro de 2026",
        "doc_id": "atlas_teste", "guardar_copia": True, "apagar_origem": True,
    })

    assert t["status"] == "concluida" and t["resultado"]["status"] == "inserido", t
    assert not copia.exists() and arquivos.caminho_copia("atlas_teste").exists()
    assert all(p["tipo_fonte"] == "pdf" for p in f.q.payloads("c1"))


def teste_reparar_metadados_pela_tarefa():

    d, f = ambiente()
    rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": [{"video_id": "AAAAAAAAAAA"}]})

    for pl in f.q.payloads("c1"):
        pl["data_publicacao"] = None

    f.metas["AAAAAAAAAAA"] = {"titulo": "Novo título", "data_publicacao": "2023-02-02"}

    t = rodar(d, "reparar_metadados", {"colecao_id": "c1", "atualizar_titulo": True})

    assert t["status"] == "concluida" and t["resultado"]["reparados"] == 1
    assert all(p["data_publicacao"] == "2023-02-02" and p["titulo"] == "Novo título"
               for p in f.q.payloads("c1"))


def teste_progresso_em_dois_niveis_mantem_a_mensagem_do_arquivo():

    pasta = pasta_temp()
    t = tarefas.criar("x", "x", {}, pasta=pasta)
    ctx = worker.Contexto(tarefas.ler(t, pasta), pasta)

    # sem contagem geral (ex.: um PDF): a etapa vira a mensagem
    ctx.sub("gravando", 1, 3)
    p = ctx.tarefa["progresso"]
    assert p["mensagem"] == "Gravando no banco (1/3)" and p["fase"] == "gravando"

    # com contagem geral: a etapa aparece junto, sem apagar "Arquivo 3 de 6"
    ctx._ultimo = 0
    ctx.geral("arquivos", 2, 6, "Arquivo 3 de 6: a.json")
    ctx.sub("embeddings", 2, 2)
    p = ctx.tarefa["progresso"]
    assert p["fase"] == "arquivos" and p["total"] == 6 and p["atual"] == 3.0
    assert p["mensagem"] == "Arquivo 3 de 6: a.json — gerando vetores (2/2)", p


def teste_importacao_mostra_arquivo_atual_e_grava_datas():

    import json
    from datetime import date

    d, f = ambiente()
    pasta_arqs = d / "legendas"
    pasta_arqs.mkdir()

    itens = []

    for i in range(3):
        caminho = pasta_arqs / f"V{i:010d}.json"
        caminho.write_text(json.dumps({"video_id": f"V{i:010d}", "titulo": f"t{i}",
                                       "data_publicacao": "2020-01-01",
                                       "transcript": transcricao_sintetica(60)}), encoding="utf-8")
        itens.append({"caminho": str(caminho), "nome_original": caminho.name, "apagar_origem": i == 2})

    mensagens = []
    original = worker.Contexto._salvar

    def espia(self):
        mensagens.append(self.tarefa["progresso"]["mensagem"])
        return original(self)

    worker.Contexto._salvar = espia

    try:
        t = rodar(d, "importar_legendas", {"colecao_id": "c1", "itens": itens})
    finally:
        worker.Contexto._salvar = original

    assert t["status"] == "concluida" and t["resultado"]["inseridos"] == 3, t

    for n in (1, 2, 3):
        assert any(m.startswith(f"Arquivo {n} de 3") for m in mensagens), (n, mensagens)

    assert any("Arquivo 2 de 3" in m and " — " in m for m in mensagens), "etapas internas junto da contagem"
    assert mensagens[-1] == "Concluído"

    por_doc = {p["doc_id"]: p for p in f.q.payloads("c1")}
    hoje = date.today().isoformat()

    assert all(p["data_processamento"].startswith(hoje) for p in por_doc.values())
    assert por_doc["V0000000000"]["data_arquivo"] == hoje          # veio de pasta: data do arquivo
    assert por_doc["V0000000002"]["data_arquivo"] is None          # enviado pelo navegador: sem data


def teste_apagar_varios_documentos_de_uma_vez():

    d, f = ambiente()

    rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": [
        {"video_id": v} for v in ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC")]})

    resumo = base_resumo = Armazenamento(f.q, "c1").resumo_documentos()
    assert set(resumo) == {"AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"}
    assert all(r["data_processamento"] for r in resumo.values())

    progresso = []
    Armazenamento(f.q, "c1").apagar_documentos(["AAAAAAAAAAA", "BBBBBBBBBBB"], lote=1,
                                               progresso=lambda a, t: progresso.append((a, t)))

    assert set(Armazenamento(f.q, "c1").resumo_documentos()) == {"CCCCCCCCCCC"}
    assert progresso == [(1, 2), (2, 2)]


def teste_canal_usa_a_aba_videos_e_ignora_ids_que_nao_sao_de_video():

    import types

    pedidos = []

    CANAL = "UC1234567890abcdefghijkl"          # ID de canal (24 caracteres), não de vídeo

    respostas = {
        # a RAIZ do canal devolve as abas (todas com o ID do canal): foi o que quebrou a ingestão
        "https://www.youtube.com/@MundoAKV": {"entries": [
            {"id": CANAL, "title": "Mundo AKV - Videos"}, {"id": CANAL, "title": "Mundo AKV - Shorts"}]},
        "https://www.youtube.com/@MundoAKV/videos": {"entries": [
            {"id": "AAAAAAAAAAA", "title": "um"},
            {"entries": [{"id": "BBBBBBBBBBB", "title": "dois (dentro de outra lista)"}]},
            {"id": CANAL, "title": "lixo"}, None]},
        "https://www.youtube.com/@MundoAKV/streams": {"entries": [
            {"id": "CCCCCCCCCCC", "title": "live"}, {"id": "AAAAAAAAAAA", "title": "repetido"}]},
    }

    class YoutubeDLFalso:
        def __init__(self, opcoes): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def extract_info(self, url, download=False):
            pedidos.append(url)
            if url not in respostas:
                raise RuntimeError("This channel does not have a shorts tab")
            return respostas[url]

    sys.modules["yt_dlp"] = types.SimpleNamespace(YoutubeDL=YoutubeDLFalso)

    try:
        ids = lambda r: [v["video_id"] for v in r]

        # link da raiz: lê a aba /videos, nunca a raiz
        r = youtube.listar_videos_canal("https://www.youtube.com/@MundoAKV")
        assert ids(r) == ["AAAAAAAAAAA", "BBBBBBBBBBB"] and pedidos == ["https://www.youtube.com/@MundoAKV/videos"]

        # já com /videos, ou com barra final / parâmetros: mesmo resultado
        for url in ("https://www.youtube.com/@MundoAKV/videos", "https://www.youtube.com/@MundoAKV/?si=abc"):
            pedidos.clear()
            assert ids(youtube.listar_videos_canal(url)) == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
            assert pedidos == ["https://www.youtube.com/@MundoAKV/videos"]

        # lives e shorts (esta aba não existe no canal: é ignorada, sem erro; repetidos não duplicam)
        pedidos.clear()
        r = youtube.listar_videos_canal("https://www.youtube.com/@MundoAKV", ("videos", "streams", "shorts"))
        assert ids(r) == ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"] and len(pedidos) == 3

        # playlist: usada como está
        pedidos.clear()
        respostas["https://www.youtube.com/playlist?list=PLx"] = {"entries": [{"id": "DDDDDDDDDDD"}]}
        assert ids(youtube.listar_videos_canal("https://www.youtube.com/playlist?list=PLx")) == ["DDDDDDDDDDD"]
        assert pedidos == ["https://www.youtube.com/playlist?list=PLx"]

        # erro na aba principal não é engolido
        try:
            youtube.listar_videos_canal("https://www.youtube.com/@Outro")
            raise AssertionError("deveria propagar")
        except RuntimeError:
            pass

    finally:
        del sys.modules["yt_dlp"]

    assert youtube.url_da_aba("https://www.youtube.com/@x/featured", "videos") == "https://www.youtube.com/@x/videos"


def teste_canal_sem_videos_e_erro_claro_e_flags_de_lives_e_shorts():

    d, f = ambiente()

    f.canal = []
    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "canal_url": "https://www.youtube.com/@vazio"})
    assert t["status"] == "erro" and "Não encontrei vídeos" in t["erro"], t

    f.canal = [{"video_id": "AAAAAAAAAAA", "titulo": "x"}]
    rodar(d, "legendas_youtube", {"colecao_id": "c1", "canal_url": "https://www.youtube.com/@a"})
    assert f.abas_pedidas == ("videos",)

    rodar(d, "legendas_youtube", {"colecao_id": "c1", "canal_url": "https://www.youtube.com/@a",
                                  "incluir_lives": True, "incluir_shorts": True, "substituir": True})
    assert f.abas_pedidas == ("videos", "streams", "shorts")


def teste_pendencias_ignora_ids_invalidos():

    arq = pasta_temp() / "p.json"

    pendencias.registrar("c1", "UC1234567890abcdefghijkl", "canal, não vídeo", arquivo=arq)
    pendencias.registrar("c1", "AAAAAAAAAAA", "vídeo", arquivo=arq)

    assert [p["video_id"] for p in pendencias.listar("c1", arq)] == ["AAAAAAAAAAA"]


def teste_traducao_de_legenda_do_youtube_na_biblioteca():

    import types

    class NoTranscriptFound(Exception): pass
    class TranscriptsDisabled(Exception): pass
    class VideoUnavailable(Exception): pass

    def snippets(textos):
        return [types.SimpleNamespace(text=x, start=float(i), duration=1.0) for i, x in enumerate(textos)]

    class Transcricao:
        def __init__(self, codigo, traduzivel=True):
            self.language_code, self.is_translatable, self.pedido = codigo, traduzivel, None

        def translate(self, destino):
            self.pedido = destino
            return types.SimpleNamespace(fetch=lambda: snippets([f"traduzido para {destino}"]))

    catalogo_de_videos = {}

    class Lista:
        def __init__(self, transcricoes): self.t = transcricoes
        def find_transcript(self, codigos):
            for c in codigos:
                if c in self.t:
                    return self.t[c]
            raise NoTranscriptFound()

    class API:
        def fetch(self, video_id, languages):
            ts = catalogo_de_videos[video_id]
            if video_id == "DESATIVADA":
                raise TranscriptsDisabled()
            for c in languages:
                if c in ts and ts[c] == "nativa":
                    return snippets(["texto em português"])
            raise NoTranscriptFound()

        def list(self, video_id):
            return Lista({c: v for c, v in catalogo_de_videos[video_id].items() if v != "nativa"})

    modulo = types.SimpleNamespace(NoTranscriptFound=NoTranscriptFound, TranscriptsDisabled=TranscriptsDisabled,
                                   VideoUnavailable=VideoUnavailable, YouTubeTranscriptApi=API)
    sys.modules["youtube_transcript_api"] = modulo

    try:
        en = Transcricao("en")
        catalogo_de_videos.update({
            "PORTUGUES": {"pt": "nativa"},
            "SOINGLES": {"en": en},
            "NAOTRAD": {"en": Transcricao("en", traduzivel=False)},
            "SOALEMAO": {"de": Transcricao("de")},
            "DESATIVADA": {},
        })

        segs, origem = youtube.baixar_legenda_com_origem("PORTUGUES", traduzir_de=["en"])
        assert origem == "youtube" and segs[0]["text"] == "texto em português"        # português tem prioridade

        segs, origem = youtube.baixar_legenda_com_origem("SOINGLES", traduzir_de=["en"])
        assert origem == "youtube:traduzido(en→pt)" and segs[0]["text"] == "traduzido para pt" and en.pedido == "pt"

        for video, de in (("SOINGLES", None), ("NAOTRAD", ["en"]), ("SOALEMAO", ["en"]), ("DESATIVADA", ["en"])):
            try:
                youtube.baixar_legenda_com_origem(video, traduzir_de=de)
                raise AssertionError((video, de))
            except youtube.LegendaIndisponivel:
                pass

        # compatibilidade: baixar_legenda continua devolvendo só os segmentos
        assert youtube.baixar_legenda("PORTUGUES")[0]["text"] == "texto em português"

    finally:
        del sys.modules["youtube_transcript_api"]


def teste_traducao_pela_tarefa_e_pela_tela():

    d, f = ambiente()
    f.so_ingles = {"EEEEEEEEEEE"}

    itens = [{"video_id": "EEEEEEEEEEE"}, {"video_id": "AAAAAAAAAAA"}]

    # sem a opção: o vídeo em inglês vira pendência
    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": itens})
    assert t["resultado"]["sem_legenda"] == ["EEEEEEEEEEE"] and t["resultado"]["traduzidos"] == 0

    # com a opção: entra traduzido, marcado na origem, e sai da lista de pendências
    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": itens, "traduzir_de": ["en"],
                                      "reavaliar_pendentes": True})
    r = t["resultado"]
    assert r["traduzidos"] == 1 and r["inseridos"] == 1 and r["sem_legenda"] == []
    assert f.traduzir_pedido == ["en"]
    pl = [p for p in f.q.payloads("c1") if p["doc_id"] == "EEEEEEEEEEE"][0]
    assert pl["origem_transcricao"] == "youtube:traduzido(en→pt)"
    assert pendencias.listar("c1") == []


def teste_titulo_traduzido_junto_com_a_legenda():

    d, f = ambiente()
    f.so_ingles = {"EEEEEEEEEEE"}

    itens = [{"video_id": "EEEEEEEEEEE"}, {"video_id": "AAAAAAAAAAA"}]

    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": itens, "traduzir_de": ["en"],
                                      "traduzir_titulo": True})
    r = t["resultado"]
    assert r["traduzidos"] == 1 and r["titulos_traduzidos"] == 1

    en = [p for p in f.q.payloads("c1") if p["doc_id"] == "EEEEEEEEEEE"][0]
    assert en["titulo"] == "PT: Título EEEEEEEEEEE" and en["titulo_video"] == en["titulo"]
    assert en["titulo_original"] == "Título EEEEEEEEEEE"

    # vídeo que já tinha legenda em português não tem o título mexido
    pt = [p for p in f.q.payloads("c1") if p["doc_id"] == "AAAAAAAAAAA"][0]
    assert pt["titulo"] == "Título AAAAAAAAAAA" and "titulo_original" not in pt

    # sem a opção, o título original é mantido mesmo na legenda traduzida
    d, f = ambiente()
    f.so_ingles = {"EEEEEEEEEEE"}
    t = rodar(d, "legendas_youtube", {"colecao_id": "c1", "itens": [{"video_id": "EEEEEEEEEEE"}],
                                      "traduzir_de": ["en"]})
    assert t["resultado"]["titulos_traduzidos"] == 0
    assert f.q.payloads("c1")[0]["titulo"] == "Título EEEEEEEEEEE"


def teste_traducao_de_titulo_pela_groq_nunca_derruba_a_ingestao():

    import types
    from ingestao import traducao

    def cliente(resposta=None, erro=None):
        def criar(**kw):
            if erro:
                raise erro
            assert kw["temperature"] == 0 and kw["messages"][1]["content"]
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=resposta))])
        return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=criar)))

    assert traducao.traduzir_titulo("The map", cliente('"O mapa"\nexplicação'), "m") == "O mapa"
    assert traducao.traduzir_titulo("The map", cliente(erro=RuntimeError("rate limit")), "m") == "The map"
    assert traducao.traduzir_titulo("The map", cliente("  "), "m") == "The map"
    assert traducao.traduzir_titulo("Hi", cliente("x" * 500), "m") == "Hi"
    assert traducao.traduzir_titulo("", cliente("algo"), "m") == ""


def teste_atualizacao_automatica_diaria():

    from datetime import date, timedelta
    from admin import atualizacoes

    d, f = ambiente()

    pasta, arq = d / "tarefas", d / "atu.json"

    original = tarefas.garantir_worker
    tarefas.garantir_worker = lambda *a, **k: False
    try:
        _atualizacao_diaria(d, f, pasta, arq)
    finally:
        tarefas.garantir_worker = original


def _atualizacao_diaria(d, f, pasta, arq):

    from datetime import date, timedelta
    from admin import atualizacoes

    hoje = date(2026, 11, 7)

    try:
        atualizacoes.criar("c1", "https://youtu.be/AAAAAAAAAAA", arquivo=arq)
        assert False, "link de vídeo não é canal"
    except ValueError:
        pass

    a = atualizacoes.criar("c1", "https://www.youtube.com/@MundoAKV", nome="Mundo AKV", limite=50,
                           traduzir_de=["en"], traduzir_titulo=True, arquivo=arq)

    try:
        atualizacoes.criar("c1", "https://www.youtube.com/@MundoAKV", arquivo=arq)
        assert False, "duplicado"
    except ValueError:
        pass

    # 1º acesso do dia cria a tarefa, com os dados do cadastro
    ids = atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=hoje)
    assert len(ids) == 1
    t = tarefas.ler(ids[0], pasta)
    p = t["params"]
    assert t["tipo"] == "legendas_youtube" and p["canal_url"] == "https://www.youtube.com/@MundoAKV"
    assert p["limite"] == 50 and p["traduzir_de"] == ["en"] and p["traduzir_titulo"] and p["atualizacao_id"] == a["id"]
    assert atualizacoes.obter(a["id"], arq)["ultima_data"] == "2026-11-07"

    # mais acessos no mesmo dia: nada novo
    assert atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=hoje) == []

    # dia seguinte, mas a tarefa de ontem ainda está na fila: não empilha outra
    amanha = hoje + timedelta(days=1)
    assert atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=amanha) == []

    # tarefa terminou: no dia seguinte roda de novo
    import json
    # (a tarefa criada é marcada como concluída à mão)
    caminho = pasta / f"{ids[0]}.json"
    dados = json.loads(caminho.read_text(encoding="utf-8")); dados["status"] = "concluida"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    assert len(atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=amanha)) == 1

    # desativada: não roda; reativada: roda
    depois = amanha + timedelta(days=1)
    for t in tarefas.listar(pasta):
        caminho = pasta / f"{t['id']}.json"
        t["status"] = "concluida"
        caminho.write_text(json.dumps(t), encoding="utf-8")

    atualizacoes.definir_ativa(a["id"], False, arq)
    assert atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=depois) == []
    atualizacoes.definir_ativa(a["id"], True, arq)
    assert len(atualizacoes.executar_pendentes(pasta=pasta, arquivo=arq, hoje=depois)) == 1

    # verificação por sessão: confere uma vez por dia e nunca levanta erro
    for t in tarefas.listar(pasta):
        t["status"] = "concluida"
        (pasta / f"{t['id']}.json").write_text(json.dumps(t), encoding="utf-8")

    estado = {}
    assert atualizacoes.verificar_na_sessao(estado, hoje=date(2026, 12, 1), pasta=pasta, arquivo=arq)
    assert atualizacoes.verificar_na_sessao(estado, hoje=date(2026, 12, 1), pasta=pasta, arquivo=arq) == []
    assert atualizacoes.verificar_na_sessao({}, hoje=date(2026, 12, 1), pasta=pasta, arquivo=d / "x" / "\0") == []

    # excluir
    atualizacoes.remover(a["id"], arq)
    assert atualizacoes.ler(arq) == []


def teste_whisper_escolhe_cpu_int8_sem_gpu_e_reaproveita_o_modelo():

    import types

    from ingestao import whisper

    antigos = {k: os.environ.pop(k, None) for k in ("WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE")}

    try:
        sem_gpu = types.SimpleNamespace(get_cuda_device_count=lambda: 0)
        com_gpu = types.SimpleNamespace(get_cuda_device_count=lambda: 1)

        sys.modules["ctranslate2"] = sem_gpu
        assert whisper.configuracao() == ("cpu", "int8")

        sys.modules["ctranslate2"] = com_gpu
        assert whisper.configuracao() == ("cuda", "float16")

        del sys.modules["ctranslate2"]                      # biblioteca ausente: cai para CPU
        assert whisper.configuracao() == ("cpu", "int8")

        os.environ["WHISPER_DEVICE"] = "cpu"
        os.environ["WHISPER_COMPUTE_TYPE"] = "float32"      # o usuário manda no .env
        assert whisper.configuracao() == ("cpu", "float32")

        # o modelo é carregado uma vez só enquanto nome/dispositivo/tipo não mudam
        carregados = []

        class ModeloFalso:
            def __init__(self, nome, device, compute_type, download_root):
                carregados.append((nome, device, compute_type))

        sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=ModeloFalso)
        whisper._carregado.update(chave=None, modelo=None)

        os.environ["WHISPER_COMPUTE_TYPE"] = "int8"
        a = whisper._modelo("medium")
        assert whisper._modelo("medium") is a and carregados == [("medium", "cpu", "int8")]

        whisper._modelo("small")
        assert carregados[-1] == ("small", "cpu", "int8") and len(carregados) == 2

    finally:
        sys.modules.pop("faster_whisper", None)
        sys.modules.pop("ctranslate2", None)
        whisper._carregado.update(chave=None, modelo=None)

        for k, v in antigos.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ============================================================

if __name__ == "__main__":

    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("teste_")]
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
