"""
Extração de texto de PDFs na ordem certa de leitura.

Usa o pdftotext (poppler), que já está na imagem Docker do projeto, com
coordenadas (-bbox-layout) para reordenar PDFs de duas colunas: a ordem
padrão do pdftotext mistura as colunas quando há imagens no meio do texto.

Também lê o Sumário, quando existir, e associa tema/subtema a cada página.
"""

import html
import re
import subprocess
from dataclasses import dataclass, field

_RE_PAGINA = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
_RE_BLOCO = re.compile(
    r'<block xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</block>', re.S)
_RE_LINHA = re.compile(
    r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', re.S)
_RE_PALAVRA = re.compile(r"<word [^>]*>(.*?)</word>", re.S)

# "Título do capítulo ........ 123"
_RE_SUMARIO = re.compile(r"^(.+?)\s*\.{5,}\s*(\d{1,4})$")

LARGURA_BLOCO_CHEIO = 0.6     # bloco mais largo que 60% da página atravessa as colunas
MARGEM_NUMERO_PAGINA = 45     # pontos do topo/rodapé onde procuramos o nº da página


@dataclass
class Bloco:
    x0: float
    y0: float
    x1: float
    y1: float
    linhas: list = field(default_factory=list)   # [(x0, texto)]

    @property
    def texto(self):
        return " ".join(t for _, t in self.linhas).strip()


@dataclass
class Pagina:
    numero: int                 # página do ARQUIVO (1 = primeira)
    impressa: int = None        # número impresso na página, se existir
    texto: str = ""
    sumario: bool = False
    tema: str = None
    subtema: str = None
    linhas_sumario: list = field(default_factory=list)


class ErroPDF(RuntimeError):
    pass


# ------------------------------------------------------------
# LEITURA
# ------------------------------------------------------------

def titulo_interno(caminho):
    """Título gravado nos metadados do PDF (pdfinfo), ou None."""

    try:
        saida = subprocess.run(
            ["pdfinfo", "-enc", "UTF-8", str(caminho)],
            capture_output=True, check=True, timeout=60
        ).stdout.decode("utf-8", "replace")
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    for linha in saida.splitlines():
        if linha.startswith("Title:"):
            return linha.split(":", 1)[1].strip() or None

    return None


def _rodar_pdftotext(caminho):

    try:
        saida = subprocess.run(
            ["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(caminho), "-"],
            capture_output=True,
            check=True,
            timeout=900
        )
    except FileNotFoundError:
        raise ErroPDF(
            "pdftotext não encontrado. Instale o poppler-utils "
            "(já vem na imagem Docker do projeto)."
        )
    except subprocess.CalledProcessError as e:
        raise ErroPDF(f"Falha ao ler o PDF: {e.stderr.decode('utf-8', 'replace')[:300]}")

    return saida.stdout.decode("utf-8", "replace")


def _blocos_da_pagina(conteudo):

    blocos = []

    for m in _RE_BLOCO.finditer(conteudo):

        x0, y0, x1, y1 = (float(v) for v in m.group(1, 2, 3, 4))
        bloco = Bloco(x0, y0, x1, y1)

        for linha in _RE_LINHA.finditer(m.group(5)):

            palavras = [html.unescape(p) for p in _RE_PALAVRA.findall(linha.group(5))]

            if palavras:
                bloco.linhas.append((float(linha.group(1)), " ".join(palavras)))

        if bloco.linhas:
            blocos.append(bloco)

    return blocos


def ordenar_blocos(blocos, largura):
    """
    Ordem de leitura: blocos de largura total dividem a página em faixas;
    dentro de cada faixa lê-se a coluna esquerda inteira e depois a direita.
    """

    cheios = sorted(
        (b for b in blocos if (b.x1 - b.x0) > LARGURA_BLOCO_CHEIO * largura),
        key=lambda b: b.y0
    )

    cheios_ids = {id(b) for b in cheios}
    resto = [b for b in blocos if id(b) not in cheios_ids]

    def colunas(lista):
        esq = sorted((b for b in lista if (b.x0 + b.x1) / 2 < largura / 2), key=lambda b: b.y0)
        dir_ = sorted((b for b in lista if (b.x0 + b.x1) / 2 >= largura / 2), key=lambda b: b.y0)
        return esq + dir_

    ordenados = []
    cursor = float("-inf")

    for cheio in cheios:
        acima = [b for b in resto if cursor <= b.y0 < cheio.y0]
        ordenados += colunas(acima) + [cheio]
        cursor = cheio.y0

    ordenados += colunas([b for b in resto if b.y0 >= cursor])

    return ordenados


def _juntar_hifenizacao(texto):
    # "pala- vra" no fim de linha -> "palavra"
    return re.sub(r"(\w)- (?=[a-zà-ú])", r"\1", texto)


def extrair_paginas(caminho):
    """Devolve a lista de Pagina com texto na ordem de leitura."""

    bruto = _rodar_pdftotext(caminho)
    paginas = []

    for numero, m in enumerate(_RE_PAGINA.finditer(bruto), start=1):

        largura, altura = float(m.group(1)), float(m.group(2))
        blocos = _blocos_da_pagina(m.group(3))

        pagina = Pagina(numero=numero)

        # número impresso: bloco só com dígitos no topo ou no rodapé
        conteudo = []

        for bloco in blocos:

            if (
                re.fullmatch(r"\d{1,4}", bloco.texto)
                and (bloco.y1 < MARGEM_NUMERO_PAGINA or bloco.y0 > altura - MARGEM_NUMERO_PAGINA)
            ):
                pagina.impressa = int(bloco.texto)
                continue

            conteudo.append(bloco)

        ordenados = ordenar_blocos(conteudo, largura)

        # linhas candidatas a Sumário (com indentação) na ordem de leitura
        for bloco in ordenados:
            for x0, texto in bloco.linhas:
                achou = _RE_SUMARIO.match(texto.strip())
                if achou:
                    pagina.linhas_sumario.append(
                        (x0, achou.group(1).strip(), int(achou.group(2)))
                    )

        pagina.texto = _juntar_hifenizacao(
            "\n".join(b.texto for b in ordenados)
        )

        paginas.append(pagina)

    return paginas


# ------------------------------------------------------------
# NUMERAÇÃO E SUMÁRIO
# ------------------------------------------------------------

def preencher_numeracao(paginas):
    """Páginas sem número detectado herdam 'anterior + 1', quando possível."""

    anterior = None

    for pagina in paginas:

        if pagina.impressa is not None:
            anterior = pagina.impressa
        elif anterior is not None and pagina.texto.strip():
            anterior += 1
            pagina.impressa = anterior


def extrair_sumario(paginas, minimo_linhas=5):
    """
    Marca as páginas de Sumário e devolve
    [{"tema", "subtema", "pagina_impressa"}] em ordem de página.

    Linhas menos indentadas = tema; mais indentadas = subtema.
    """

    candidatas = [p for p in paginas if len(p.linhas_sumario) >= minimo_linhas]

    if not candidatas:
        return []

    for pagina in candidatas:
        pagina.sumario = True

    todas = [linha for p in candidatas for linha in p.linhas_sumario]
    recuo_tema = min(x0 for x0, _, _ in todas)

    entradas = []
    tema_atual = None

    for x0, titulo, pag in todas:

        if x0 - recuo_tema < 5:
            tema_atual = titulo
            entradas.append({"tema": titulo, "subtema": None, "pagina_impressa": pag})
        else:
            entradas.append({"tema": tema_atual, "subtema": titulo, "pagina_impressa": pag})

    return entradas


def aplicar_sumario(paginas, entradas):
    """Preenche tema/subtema de cada página pelo último item do Sumário que já começou."""

    if not entradas:
        return

    ordenadas = sorted(entradas, key=lambda e: e["pagina_impressa"])

    for pagina in paginas:

        if pagina.sumario or pagina.impressa is None:
            continue

        atual = None

        for entrada in ordenadas:
            if entrada["pagina_impressa"] <= pagina.impressa:
                atual = entrada
            else:
                break

        if atual:
            pagina.tema = atual["tema"]
            pagina.subtema = atual["subtema"]


def extrair_documento(caminho, paginas_sem_numero=None):
    """
    Pipeline completo: páginas ordenadas, numeração e Sumário.

    paginas_sem_numero: quantas páginas do início (capa etc.) não entram na
    numeração impressa. Se None, a numeração é lida do próprio PDF; se
    informado (ex.: 1), a página N+1 do arquivo passa a ser a página 1.
    """

    paginas = extrair_paginas(caminho)

    if paginas_sem_numero is None:
        preencher_numeracao(paginas)
    else:
        for pagina in paginas:
            pagina.impressa = (
                pagina.numero - paginas_sem_numero
                if pagina.numero > paginas_sem_numero
                else None
            )

    entradas = extrair_sumario(paginas)

    aplicar_sumario(paginas, entradas)

    return paginas, entradas
