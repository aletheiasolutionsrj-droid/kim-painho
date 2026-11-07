"""
Streamlit de mentira para testar as telas sem navegador.

Executa o código de verdade (então erros de nome, de argumento e de fluxo aparecem),
devolve valores padrão para cada widget e deixa o teste "clicar" em botões e
"digitar" em campos pelo parâmetro key.
"""

import sys
import types


class Parar(Exception):
    """st.stop() / st.rerun()"""


class _Contexto:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, nome):
        return getattr(FakeSt.atual, nome)


class FakeSt(types.ModuleType):

    atual = None

    def __init__(self):
        super().__init__("streamlit")
        FakeSt.atual = self
        self.session_state = _Estado()
        self.cliques = set()          # keys de botões "pressionados"
        self.valores = {}             # key -> valor devolvido pelo widget
        self.saidas = []              # (tipo, texto) de tudo que foi mostrado
        self.reruns = 0
        self.hook_editor = None
        self.sidebar = _Contexto()

    # ---- utilitários do teste ----
    def reset(self):
        self.saidas.clear()
        self.cliques.clear()
        self.valores.clear()
        self.reruns = 0
        self.hook_editor = None

    def textos(self, tipo=None):
        return [t for k, t in self.saidas if tipo is None or k == tipo]

    def _registrar(self, tipo, *args):
        if args:
            self.saidas.append((tipo, str(args[0])))

    def _valor(self, key, padrao):
        return self.valores.get(key, padrao) if key is not None else padrao

    # ---- decoradores / controle ----
    def cache_resource(self, f=None, **kw):
        return f if f else (lambda g: g)

    cache_data = cache_resource

    def fragment(self, f=None, **kw):
        return f if f else (lambda g: g)

    def set_page_config(self, **kw):
        pass

    def stop(self):
        raise Parar("stop")

    def rerun(self):
        self.reruns += 1
        raise Parar("rerun")

    def toast(self, texto, **kw):
        self._registrar("toast", texto)

    # ---- layout ----
    def tabs(self, nomes):
        return [_Contexto() for _ in nomes]

    column_config = types.SimpleNamespace(DateColumn=lambda *a, **kw: ("DateColumn", a, kw))

    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Contexto() for _ in range(n)]

    def container(self, **kw):
        return _Contexto()

    def expander(self, *a, **kw):
        self._registrar("expander", *a)
        return _Contexto()

    def form(self, *a, **kw):
        return _Contexto()

    def spinner(self, *a, **kw):
        return _Contexto()

    # ---- texto ----
    def _texto(tipo):
        def f(self, *a, **kw):
            self._registrar(tipo, *a)
        return f

    title = _texto("title")
    header = _texto("header")
    subheader = _texto("subheader")
    markdown = _texto("markdown")
    write = _texto("write")
    caption = _texto("caption")
    info = _texto("info")
    success = _texto("success")
    warning = _texto("warning")
    error = _texto("error")
    code = _texto("code")
    divider = _texto("divider")

    def metric(self, rotulo, valor=None, **kw):
        self.saidas.append(("metric", f"{rotulo}: {valor}"))

    def progress(self, valor, text=None, **kw):
        assert 0.0 <= valor <= 1.0, valor
        self._registrar("progress", text or "")
        return _Barra()

    def switch_page(self, destino):
        self._registrar("switch_page", destino)
        raise Parar("switch_page")

    def html(self, corpo, **kw):
        self._registrar("html", corpo)

    def link_button(self, rotulo, url, **kw):
        self._registrar("link_button", f"{rotulo}|{url}")

    def date_input(self, rotulo, value=None, key=None, **kw):
        return self._valor(key, value)

    def page_link(self, destino, label=None, **kw):
        self._registrar("page_link", f"{destino}|{label}")

    # ---- widgets ----
    def button(self, rotulo, key=None, disabled=False, **kw):
        self._registrar("button", rotulo)
        return (key in self.cliques or rotulo in self.cliques) and not disabled

    form_submit_button = button

    def text_input(self, rotulo, value="", key=None, **kw):
        return self._valor(key, value)

    text_area = text_input

    def number_input(self, rotulo, min_value=None, max_value=None, value=None, key=None, **kw):
        return self._valor(key, value if value is not None else (min_value or 0))

    def checkbox(self, rotulo, value=False, key=None, **kw):
        return self._valor(key, value)

    def radio(self, rotulo, options, key=None, index=0, **kw):
        return self._valor(key, list(options)[index])

    def selectbox(self, rotulo, options=(), index=0, key=None, **kw):
        opcoes = list(options)
        return self._valor(key, opcoes[index] if opcoes else None)

    def multiselect(self, rotulo, options=(), key=None, **kw):
        return self._valor(key, [])

    def file_uploader(self, rotulo, key=None, accept_multiple_files=False, **kw):
        return self._valor(key, [] if accept_multiple_files else None)

    hook_editor = None

    def data_editor(self, df, key=None, **kw):
        assert "column_config" not in kw or isinstance(kw["column_config"], dict)
        if self.hook_editor:
            return self.hook_editor(df, key)
        return self._valor(key, df)

    def dataframe(self, df, **kw):
        pass


class _Barra:
    def progress(self, valor, **kw):
        assert 0.0 <= valor <= 1.0, valor


class _Estado(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class ArquivoEnviado:
    """Imita o objeto devolvido por st.file_uploader."""

    def __init__(self, nome, conteudo):
        self.name = nome
        self._c = conteudo
        self.size = len(conteudo)

    def getbuffer(self):
        return memoryview(self._c)


def instalar():
    st = FakeSt()
    sys.modules["streamlit"] = st
    return st
