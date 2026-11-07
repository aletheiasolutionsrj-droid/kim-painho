"""
Cópias locais dos PDFs, para abrir o documento na página exata.

Os PDFs ficam em  static/pdfs/<doc_id>.pdf  (ao lado do app.py). Com o
serviço de arquivos estáticos do Streamlit ligado, eles abrem em
  /app/static/pdfs/<doc_id>.pdf#page=N
no leitor de PDF do próprio navegador. O "#page=N" usa a página do ARQUIVO,
não a numeração impressa no rodapé.

As cópias NÃO fazem parte do backup do Qdrant: cada pessoa guarda o seu PDF.
"""

import shutil
from pathlib import Path
from urllib.parse import quote

PASTA_PDFS = Path(__file__).resolve().parents[1] / "static" / "pdfs"


def caminho_copia(doc_id, pasta=None):

    return Path(pasta or PASTA_PDFS) / f"{doc_id}.pdf"


def copiar_pdf(origem, doc_id, pasta=None):
    """Copia o PDF para a pasta servida pelo app. Devolve o caminho da cópia."""

    destino = caminho_copia(doc_id, pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)

    origem = Path(origem).resolve()

    if origem != destino.resolve():
        shutil.copyfile(origem, destino)

    return destino


def url_pdf(doc_id, pagina, pasta=None):
    """URL relativa que abre o PDF na página do arquivo, ou None se não houver cópia."""

    if not doc_id or not caminho_copia(doc_id, pasta).exists():
        return None

    pagina = int(pagina) if pagina else 1

    return f"app/static/pdfs/{quote(str(doc_id))}.pdf#page={pagina}"
