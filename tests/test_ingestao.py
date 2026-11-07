"""
Testes da ingestão, sem Qdrant nem Ollama (clientes falsos em memória).

Uso (dentro de src/):
    LEGENDA_JSON=/caminho/video.json ATLAS_PDF=/caminho/atlas.pdf python tests/test_ingestao.py

Testes que dependem dos arquivos de exemplo são ignorados se não existirem.
"""

import json
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ============================================================
# qdrant_client.models FALSO (só o que a ingestão usa)
# ============================================================

class _Simples:
    def __init__(self, *a, **kw):
        self.__dict__.update(kw)
        self._args = a


class Filter(_Simples):
    pass


class FieldCondition(_Simples):
    pass


class MatchValue(_Simples):
    pass


class Range(_Simples):
    pass


class PointStruct(_Simples):
    pass


class FilterSelector(_Simples):
    pass


class VectorParams(_Simples):
    pass


class TextIndexParams(_Simples):
    pass


class _Enum:
    def __getattr__(self, nome):
        return nome


models = types.ModuleType("qdrant_client.models")
for _nome in ["Filter", "FieldCondition", "MatchValue", "Range", "PointStruct",
              "FilterSelector", "VectorParams", "TextIndexParams"]:
    setattr(models, _nome, globals()[_nome])
for _nome in ["Distance", "PayloadSchemaType", "TextIndexType", "TokenizerType"]:
    setattr(models, _nome, _Enum())

pacote = types.ModuleType("qdrant_client")
pacote.models = models
sys.modules["qdrant_client"] = pacote
sys.modules["qdrant_client.models"] = models


# ============================================================
# QDRANT FALSO
# ============================================================

def _casa(payload, cond):

    if isinstance(cond, Filter):
        return _filtra(payload, cond)

    valor = payload.get(cond.key)

    if getattr(cond, "match", None) is not None:
        return valor == cond.match.value

    if getattr(cond, "range", None) is not None:
        return valor is not None and valor >= cond.range.gte

    raise NotImplementedError(cond)


def _filtra(payload, filtro):

    if filtro is None:
        return True

    must = getattr(filtro, "must", None) or []
    should = getattr(filtro, "should", None) or []

    if not all(_casa(payload, c) for c in must):
        return False

    if should and not any(_casa(payload, c) for c in should):
        return False

    return True


class FakeQdrant:

    def __init__(self):
        self.colecoes = {}      # nome -> {"dim": int, "pontos": {id: (vetor, payload)}}

    def collection_exists(self, collection_name):
        return collection_name in self.colecoes

    def create_collection(self, collection_name, vectors_config):
        self.colecoes[collection_name] = {"dim": vectors_config.size, "pontos": {}}

    def get_collection(self, collection_name):
        c = self.colecoes[collection_name]
        vetores = types.SimpleNamespace(size=c["dim"])
        return types.SimpleNamespace(
            config=types.SimpleNamespace(params=types.SimpleNamespace(vectors=vetores)),
            payload_schema=c.setdefault("indices", {})
        )

    def create_payload_index(self, collection_name, field_name, field_schema, wait=True):
        self.colecoes[collection_name].setdefault("indices", {})[field_name] = field_schema

    def upsert(self, collection_name, points, wait=True):
        for p in points:
            self.colecoes[collection_name]["pontos"][p.id] = (p.vector, dict(p.payload))

    def _filtrados(self, nome, filtro):
        return [
            (pid, v, pl) for pid, (v, pl) in self.colecoes[nome]["pontos"].items()
            if _filtra(pl, filtro)
        ]

    def count(self, collection_name, count_filter=None, exact=True):
        return types.SimpleNamespace(count=len(self._filtrados(collection_name, count_filter)))

    def delete(self, collection_name, points_selector, wait=True):
        for pid, _, _ in self._filtrados(collection_name, points_selector.filter):
            del self.colecoes[collection_name]["pontos"][pid]

    def scroll(self, collection_name, limit=100, offset=None, with_payload=True, with_vectors=False):
        itens = list(self.colecoes[collection_name]["pontos"].items())
        pontos = [types.SimpleNamespace(id=i, payload=pl) for i, (_, pl) in itens]
        return pontos, None

    def set_payload(self, collection_name, payload, points, wait=True):
        for pid, _, _ in self._filtrados(collection_name, points):
            self.colecoes[collection_name]["pontos"][pid][1].update(payload)

    # util dos testes
    def payloads(self, nome):
        return [pl for _, pl in self.colecoes[nome]["pontos"].values()]


class FakeEmbedder:

    modelo = "fake-embed"
    dimensao = 8

    def __init__(self):
        self.textos = []

    def documentos(self, textos, progresso=None):
        self.textos.extend(textos)
        if progresso:
            progresso(len(textos), len(textos))
        return [[0.1] * self.dimensao for _ in textos]


# ============================================================
# TESTES
# ============================================================

from ingestao import pipeline                                  # noqa: E402
from ingestao.armazenamento import Armazenamento, ErroDimensao, gerar_id_chunk   # noqa: E402
from ingestao.limpeza import limpar_segmentos                  # noqa: E402

LEGENDA = os.getenv("LEGENDA_JSON")
ATLAS = os.getenv("ATLAS_PDF")


def seg(texto, inicio, dur=3.0):
    return {"text": texto, "start": inicio, "duration": dur}


def transcricao_sintetica(n_segmentos=200):
    return [
        seg(f"Esta é a frase número {i} sobre política e economia brasileira.", i * 3.0)
        for i in range(n_segmentos)
    ]


def teste_limpeza_e_glossario():

    segs = [
        seg("[música]", 0), seg("[Música] Olá, mundo &amp; amigos", 1),
        seg("Olá, mundo &amp; amigos", 4),                    # repetição consecutiva
        seg("o sabugza falou", 6), seg("   ", 9), seg("FLAVIO DINO caiu", 10),
    ]

    limpos = limpar_segmentos(segs, {"sabugza": "Sabugosa", "flavio dino": "Flávio Dino"})
    textos = [s["text"] for s in limpos]

    assert textos == ["Olá, mundo & amigos", "o Sabugosa falou", "Flávio Dino caiu"], textos


def teste_video_novo_duplicado_e_substituicao():

    q, emb = FakeQdrant(), FakeEmbedder()
    doc = {"video_id": "abc123", "titulo": "Vídeo de Teste", "data_publicacao": "2026-10-01",
           "origem_transcricao": "youtube", "transcript": transcricao_sintetica(300)}

    r1 = pipeline.ingerir_transcricao("acervo_x", doc, qdrant=q, embedder=emb)
    assert r1["status"] == "inserido" and r1["chunks"] > 3, r1

    pls = q.payloads("acervo_x")
    assert len(pls) == r1["chunks"]
    assert all(p["tipo_fonte"] == "video" and p["video_id"] == "abc123" and p["doc_id"] == "abc123" for p in pls)
    assert all(p["url_com_minuto"].startswith("https://youtu.be/abc123?t=") for p in pls)
    assert sorted(p["chunk_index"] for p in pls) == list(range(r1["chunks"]))
    assert all(p["modelo_embedding"] == "fake-embed" for p in pls)

    # cabeçalho no texto embedado, mas não no texto exibido/buscado
    assert emb.textos[0].startswith("Vídeo de Teste — 01/10/2026\n")
    assert not pls[0]["texto_bruto"].startswith("Vídeo")

    # índices criados
    assert {"texto_bruto", "doc_id", "video_id", "tipo_fonte", "timestamp_segundos"} <= \
        set(q.colecoes["acervo_x"]["indices"])

    # segunda vez: já existe
    r2 = pipeline.ingerir_transcricao("acervo_x", doc, qdrant=q, embedder=emb)
    assert r2["status"] == "ja_existe"

    # substituir por transcrição MENOR: sobras antigas são removidas
    doc_curto = dict(doc, transcript=transcricao_sintetica(120))
    r3 = pipeline.ingerir_transcricao("acervo_x", doc_curto, qdrant=q, embedder=emb, substituir=True)
    assert r3["status"] == "inserido" and r3["chunks"] < r1["chunks"]
    assert len(q.payloads("acervo_x")) == r3["chunks"], "sobraram chunks antigos"


def teste_compatibilidade_com_dados_antigos():

    q, emb = FakeQdrant(), FakeEmbedder()
    q.create_collection("acervo_x", types.SimpleNamespace(size=8))

    # pontos no formato antigo: só video_id, ids pela mesma fórmula
    for i in range(40):
        q.upsert("acervo_x", [types.SimpleNamespace(
            id=gerar_id_chunk("velho1", i), vector=[0.0] * 8,
            payload={"tipo_fonte": "video", "video_id": "velho1", "chunk_index": i,
                     "texto_bruto": "x", "data_publicacao": None})])

    arm = Armazenamento(q, "acervo_x")
    assert arm.documento_existe("velho1")
    assert arm.ids_existentes() == {"velho1"}

    doc = {"video_id": "velho1", "titulo": "Velho", "transcript": transcricao_sintetica(120)}
    r = pipeline.ingerir_transcricao("acervo_x", doc, qdrant=q, embedder=emb, substituir=True)
    assert len(q.payloads("acervo_x")) == r["chunks"], "chunks antigos não foram substituídos"


def teste_dimensao_incompativel():

    q, emb = FakeQdrant(), FakeEmbedder()
    q.create_collection("acervo_x", types.SimpleNamespace(size=768))

    try:
        pipeline.ingerir_transcricao(
            "acervo_x", {"video_id": "z", "transcript": transcricao_sintetica(50)},
            qdrant=q, embedder=emb)
    except ErroDimensao as e:
        assert "768" in str(e) and "8" in str(e)
        return

    raise AssertionError("deveria ter recusado a dimensão errada")


def teste_podcast():

    q, emb = FakeQdrant(), FakeEmbedder()
    doc = {"tipo_fonte": "podcast", "doc_id": "true_outspeak_042", "titulo": "True Outspeak 42",
           "data_publicacao": "2004-05-10", "url": "https://exemplo.org/ep42", "episodio": 42,
           "origem_transcricao": "whisper", "transcript": transcricao_sintetica(200)}

    r = pipeline.ingerir_transcricao("acervo_olavo", doc, qdrant=q, embedder=emb)
    pls = q.payloads("acervo_olavo")

    assert r["status"] == "inserido"
    assert all(p["tipo_fonte"] == "podcast" and "video_id" not in p for p in pls)
    assert all("url_com_minuto" not in p and p["url"] == "https://exemplo.org/ep42" for p in pls)
    assert all(p["episodio"] == 42 and p["timestamp_texto"] for p in pls)


def teste_reparar_metadados():

    q, emb = FakeQdrant(), FakeEmbedder()

    for vid, data in [("v1", None), ("v2", "2025-01-02"), ("v3", None)]:
        pipeline.ingerir_transcricao(
            "acervo_x", {"video_id": vid, "titulo": f"Title {vid}", "data_publicacao": data,
                         "transcript": transcricao_sintetica(60)}, qdrant=q, embedder=emb)

    consultas = []

    def falso_youtube(video_id):
        consultas.append(video_id)
        return {"titulo": f"Título {video_id}", "data_publicacao": "2026-03-04"}

    r = pipeline.reparar_metadados("acervo_x", falso_youtube, qdrant=q, atualizar_titulo=True)

    assert sorted(consultas) == ["v1", "v3"], consultas       # v2 já tinha data
    assert r["reparados"] == 2 and not r["falhas"]

    datas = {p["doc_id"]: (p["data_publicacao"], p["titulo_video"]) for p in q.payloads("acervo_x")}
    assert datas["v1"] == ("2026-03-04", "Título v1")
    assert datas["v2"] == ("2025-01-02", "Title v2")


def teste_lista_de_existentes_evita_consulta_por_documento():

    q, emb = FakeQdrant(), FakeEmbedder()
    doc = lambda i: {"video_id": f"v{i}", "titulo": f"T{i}", "transcript": transcricao_sintetica(60)}

    arm, _ = pipeline.preparar_colecao("acervo_x", q, emb)
    pipeline.ingerir_transcricao("acervo_x", doc(1), qdrant=q, embedder=emb)

    existentes = arm.ids_existentes()
    assert existentes == {"v1"}

    chamadas = []
    original = q.count
    q.count = lambda *a, **k: (chamadas.append(1), original(*a, **k))[1]

    r_velho = pipeline.ingerir_transcricao("acervo_x", doc(1), qdrant=q, embedder=emb, existentes=existentes)
    r_novo = pipeline.ingerir_transcricao("acervo_x", doc(2), qdrant=q, embedder=emb, existentes=existentes)

    assert r_velho["status"] == "ja_existe" and r_novo["status"] == "inserido"
    assert "v2" in existentes
    assert not chamadas, "não deveria consultar o Qdrant por documento"


def teste_indices_existem_antes_da_checagem():

    ordem = []
    q, emb = FakeQdrant(), FakeEmbedder()

    original_idx, original_count = q.create_payload_index, q.count
    q.create_payload_index = lambda *a, **k: (ordem.append("indice"), original_idx(*a, **k))[1]
    q.count = lambda *a, **k: (ordem.append("count"), original_count(*a, **k))[1]

    pipeline.ingerir_transcricao(
        "acervo_x", {"video_id": "v1", "transcript": transcricao_sintetica(60)}, qdrant=q, embedder=emb)

    assert "indice" in ordem and "count" in ordem
    assert ordem.index("count") > max(i for i, o in enumerate(ordem) if o == "indice"), ordem
    assert "chunk_index" in q.colecoes["acervo_x"]["indices"]


def teste_numeracao_manual_copia_e_link():

    if not (ATLAS and Path(ATLAS).exists()):
        return "ignorado (defina ATLAS_PDF)"

    import tempfile
    from ingestao import arquivos

    with tempfile.TemporaryDirectory() as pasta:

        # numeração lida do PDF: página 6 do arquivo = 5 impressa
        q1, emb = FakeQdrant(), FakeEmbedder()
        pipeline.ingerir_pdf("a", ATLAS, qdrant=q1, embedder=emb, copiar_para=pasta)
        auto = {p["pagina"]: p["pagina_impressa"] for p in q1.payloads("a")}
        assert auto[6] == 5

        # "a capa não conta": 2 páginas sem número -> página 6 do arquivo = 4
        q2 = FakeQdrant()
        r = pipeline.ingerir_pdf("a", ATLAS, qdrant=q2, embedder=emb, paginas_sem_numero=2)
        manual = {p["pagina"]: p["pagina_impressa"] for p in q2.payloads("a")}
        assert manual[6] == 4 and manual[10] == 8
        # o tema (do Sumário) acompanha a numeração informada: o 1º tema começa
        # na página 4; antes disso (impressa < 4) não há tema
        for pl in q2.payloads("a"):
            esperado = "Carreta Furacão" if pl["pagina_impressa"] >= 4 else None
            assert pl["tema"] == esperado, (pl["pagina"], pl["pagina_impressa"], pl["tema"])

        # cópia feita mesmo quando o documento já está indexado
        doc_id = r["doc_id"]
        assert arquivos.caminho_copia(doc_id, pasta).exists()
        (arquivos.caminho_copia(doc_id, pasta)).unlink()
        pipeline.ingerir_pdf("a", ATLAS, qdrant=q1, embedder=emb, copiar_para=pasta)   # já existe
        assert arquivos.caminho_copia(doc_id, pasta).exists()

        # link: usa a página do ARQUIVO; sem cópia, não há link
        assert arquivos.url_pdf(doc_id, 71, pasta) == f"app/static/pdfs/{doc_id}.pdf#page=71"
        assert arquivos.url_pdf("nao_existe", 3, pasta) is None


def teste_card_do_pdf_mostra_numeracao_do_autor():

    chamadas = []
    st = types.ModuleType("streamlit")
    for nome in ["markdown", "caption", "link_button", "html"]:
        setattr(st, nome, lambda *a, _n=nome, **k: chamadas.append((_n, a)))
    sys.modules["streamlit"] = st

    import importlib
    ui = importlib.import_module("ui")

    ui.exibir_localizacao_pdf({
        "doc_id": "sem_copia", "pagina": 71, "pagina_fim": 72, "pagina_impressa": 70,
        "total_paginas": 347, "edicao": "Abril de 2023", "tema": "Escândalo Master", "subtema": "TCU"})

    textos = " | ".join(str(a[0]) for _, a in chamadas)

    assert "`70–71`" in textos, textos
    assert "arquivo PDF: 71–72 de 347" in textos
    assert "Abril de 2023" in textos and "Escândalo Master › TCU" in textos
    assert not any(n == "link_button" for n, _ in chamadas), "sem cópia local não deve haver botão"


def teste_video_real():

    if not (LEGENDA and Path(LEGENDA).exists()):
        return "ignorado (defina LEGENDA_JSON)"

    q, emb = FakeQdrant(), FakeEmbedder()
    doc = json.loads(Path(LEGENDA).read_text(encoding="utf-8"))

    r = pipeline.ingerir_transcricao("acervo_x", doc, qdrant=q, embedder=emb,
                                     correcoes={"Sabugza": "Sabugosa"})
    pls = q.payloads("acervo_x")

    assert 90 <= r["chunks"] <= 115, r
    assert not any("[" in p["texto_bruto"] for p in pls)
    assert max(p["timestamp_segundos"] for p in pls) > 70 * 60


def teste_pdf_real():

    if not (ATLAS and Path(ATLAS).exists()):
        return "ignorado (defina ATLAS_PDF)"

    q, emb = FakeQdrant(), FakeEmbedder()
    r = pipeline.ingerir_pdf("acervo_atlas", ATLAS, qdrant=q, embedder=emb)
    pls = q.payloads("acervo_atlas")

    assert r["status"] == "inserido" and r["paginas"] == 10 and r["temas_no_sumario"] == 57, r
    assert all(p["tipo_fonte"] == "pdf" and p["total_paginas"] == 10 for p in pls)
    assert all(p["edicao"] == "Janeiro de 2026" and p["data_publicacao"] == "2026-01-01" for p in pls)

    paginas = {p["pagina"] for p in pls} | {p["pagina_fim"] for p in pls}
    assert not paginas & {1, 2, 3, 4}, f"páginas de capa/sumário entraram: {paginas}"
    assert all(5 <= p["pagina"] <= 10 for p in pls)
    assert all(p["pagina_fim"] >= p["pagina"] for p in pls)
    assert all(p["tema"] == "Carreta Furacão" for p in pls)
    assert all(p["pagina_impressa"] == p["pagina"] - 1 for p in pls)

    # ordem de leitura das colunas
    texto = " ".join(p["texto_bruto"] for p in pls)
    assert "Cláudio Dantas trouxe um toque pragmático ao compartilhar" in texto

    assert all(p["titulo"] == "Atlas Brasileiro - Janeiro de 2026" for p in pls), pls[0]["titulo"]
    assert emb.textos[0].startswith("Atlas Brasileiro - Janeiro de 2026 — Carreta Furacão\n")


# ============================================================

if __name__ == "__main__":

    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("teste_")]
    falhas = 0

    for nome, func in testes:
        try:
            extra = func()
            print(f"  ok  {nome}" + (f"  [{extra}]" if extra else ""))
        except Exception as e:
            falhas += 1
            print(f"FALHOU {nome}: {type(e).__name__}: {e}")

    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
