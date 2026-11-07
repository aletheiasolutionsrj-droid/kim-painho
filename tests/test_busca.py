"""
Testes da busca, do contexto enviado à IA e do cartão de resultado para podcast/áudio.

As bibliotecas externas (Qdrant, Ollama, Groq) são trocadas por dublês simples.

Uso (dentro de src/):   python tests/test_busca.py
"""

import sys
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(AQUI))

import fake_streamlit                                              # noqa: E402

st = fake_streamlit.instalar()


# ---- dublês dos módulos externos ----
class _Modelo:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"{type(self).__name__}({self.__dict__})"


def _classe(nome):
    return type(nome, (_Modelo,), {})


modelos = types.ModuleType("qdrant_client.models")
for _n in ("Filter", "FieldCondition", "MatchValue", "MatchPhrase", "Range"):
    setattr(modelos, _n, _classe(_n))

pacote = types.ModuleType("qdrant_client")
pacote.models = modelos
sys.modules["qdrant_client"] = pacote
sys.modules["qdrant_client.models"] = modelos
sys.modules["ollama"] = types.ModuleType("ollama")


class ClienteQdrant:
    """Guarda o último filtro e devolve os pontos cadastrados que obedecem a ele."""

    def __init__(self):
        self.pontos = []
        self.filtro = None

    def _passa(self, ponto, filtro):
        for c in (getattr(filtro, "must", None) or []):
            if isinstance(c, modelos.FieldCondition) and hasattr(c.match, "value"):
                if ponto.payload.get(c.key) != c.match.value:
                    return False
        return True

    def query_points(self, collection_name, query, limit, query_filter=None):
        self.filtro = query_filter
        achados = [p for p in self.pontos if self._passa(p, query_filter)]
        return types.SimpleNamespace(points=achados[:limit])

    def scroll(self, **kw):
        return [], None


cliente = ClienteQdrant()

clientes = types.ModuleType("clientes")
clientes.client_qdrant = cliente
clientes.client_groq = None
sys.modules["clientes"] = clientes

emb = types.ModuleType("ingestao.embeddings")
emb.embed_consulta = lambda pergunta, modelo=None: [0.1] * 8
emb.modelo_da_colecao = lambda colecao_id: "nomic-embed-text"
sys.modules["ingestao.embeddings"] = emb

config = types.ModuleType("config")
config.MODELO_LLM = "x"
sys.modules["config"] = config

import busca                                                       # noqa: E402
import geracao                                                     # noqa: E402
import ui                                                          # noqa: E402


def ponto(i, tipo, **extra):
    pl = {"tipo_fonte": tipo, "doc_id": f"d{i}", "titulo": f"T{i}", "titulo_video": f"T{i}",
          "data_publicacao": "2006-12-11", "timestamp_texto": "01:30", "timestamp_segundos": 90,
          "texto_bruto": f"texto {i}"}
    pl.update(extra)
    return types.SimpleNamespace(id=i, payload=pl)


def acervo():
    cliente.pontos = [
        ponto(1, "video", url_com_minuto="https://youtu.be/x?t=90"),
        ponto(2, "pdf", arquivo_nome="atlas.pdf", pagina=3),
        ponto(3, "podcast", episodio=2, titulo="TOS-002", titulo_video="TOS-002"),
    ]


# ============================================================

def teste_filtro_por_tipo_de_fonte():

    acervo()

    def tipos(opcao, **kw):
        r = busca.buscar_contexto_qdrant("pergunta", opcao, 10, "c", **kw)
        return sorted(p.payload["tipo_fonte"] for p in r)

    assert tipos("Todo o acervo") == ["pdf", "podcast", "video"]
    assert tipos("Apenas Vídeos") == ["video"]
    assert tipos("Apenas PDFs") == ["pdf"]
    assert tipos("Apenas Áudio/Podcast") == ["podcast"]


def teste_ignorar_inicio_nao_exclui_podcast():

    acervo()

    busca.buscar_contexto_qdrant("p", "Todo o acervo", 10, "c", ignorar_segundos=180)

    # o filtro de "ignorar início" só restringe vídeos: PDF e podcast passam direto
    texto = repr(cliente.filtro)
    assert "timestamp_segundos" in texto and "must_not" in texto and "'video'" in texto

    busca.buscar_contexto_qdrant("p", "Apenas Áudio/Podcast", 10, "c", ignorar_segundos=180)
    assert "timestamp_segundos" not in repr(cliente.filtro)


def teste_contexto_enviado_a_ia_identifica_o_podcast():

    acervo()

    contexto, fontes = geracao.montar_contexto(cliente.pontos)

    assert '[Fonte 3] Podcast/áudio: "TOS-002" (episódio 2)' in contexto
    assert "Publicado em: 11/12/2006" in contexto and "Trecho a partir de 01:30" in contexto
    assert "texto 3" in contexto
    assert '[Fonte 1] Vídeo: "T1"' in contexto and "[Fonte 2] PDF" in contexto
    assert [f["tipo_fonte"] for f in fontes] == ["video", "pdf", "podcast"]


def teste_cartao_de_podcast_aparece_na_tela():

    st.reset()

    ui.exibir_fonte(ponto(3, "podcast", episodio=2, url="https://exemplo.com/ep2").payload)

    assert any("TOS-002" in t or "T3" in t for t in st.textos("html"))
    assert any("Episódio 2" in t for t in st.textos("caption"))
    assert any("Falado aos 01:30 do áudio" in t for t in st.textos("caption"))
    assert any("exemplo.com/ep2" in t for t in st.textos("link_button"))


def teste_cartao_de_trecho_sem_tipo_nao_some_nem_quebra():

    st.reset()

    ui.exibir_fonte({"titulo": "Antigo", "texto_bruto": "x", "timestamp_texto": "00:10"})   # sem link

    assert any("Antigo" in t for t in st.textos("html"))
    assert st.textos("link_button") == []

    st.reset()
    ui.exibir_fonte(ponto(1, "video", url_com_minuto="https://youtu.be/x?t=90").payload)
    assert any("Assistir" in t for t in st.textos("link_button"))

    st.reset()
    ui.exibir_fonte(ponto(2, "pdf", arquivo_nome="atlas.pdf", pagina=3).payload)
    assert any("Página" in t for t in st.textos("markdown"))


def teste_rotulo_da_fonte_e_titulo_completo_no_popup():

    st.reset()

    titulo = "Um título bem comprido que o cartão corta com reticências no meio da frase"
    ui.exibir_fonte(ponto(1, "video", titulo=titulo, titulo_video=titulo,
                          url_com_minuto="https://youtu.be/x?t=90").payload, "Fonte 4:")

    marcados = st.textos("markdown")
    assert marcados[0] == "**Fonte 4:**"                         # o rótulo vem antes do título

    html = st.textos("html")[0]
    assert html.count(titulo) >= 2                               # no cartão e inteiro no popup (title="...")
    assert 'title="' + titulo + "&#10;&#10;texto 1" in html      # popup: título, linha em branco, trecho

    st.reset()
    ui.exibir_fonte(ponto(3, "podcast").payload)
    assert not [m for m in st.textos("markdown") if m.startswith("**Fonte")]    # sem rótulo, sem linha


# ============================================================

if __name__ == "__main__":

    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("teste_")]
    falhas = 0

    for nome, func in testes:
        try:
            func()
            print(f"  ok  {nome}")
        except Exception as e:
            import traceback
            falhas += 1
            print(f"FALHOU {nome}: {type(e).__name__}: {e}")
            traceback.print_exc()

    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
