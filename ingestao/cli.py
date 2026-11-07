"""
Linha de comando da ingestão (dentro do container do app):

  python -m ingestao.cli legendas --colecao acervo_kim_paim --pasta ./legendas_json
  python -m ingestao.cli pdf --colecao acervo_atlas ./documentos_pdf/Atlas_Janeiro_2026.pdf
  python -m ingestao.cli reparar-metadados --colecao acervo_kim_paim --titulos
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

from . import arquivos, pipeline


def _barra(fase, atual, total):

    sys.stdout.write(f"\r   {fase:<11} {atual}/{total}   ")
    sys.stdout.flush()

    if atual >= total:
        sys.stdout.write("\n")


def _carregar_glossario(caminho):

    if not caminho:
        return None

    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def cmd_legendas(args):

    pasta = Path(args.pasta)
    arquivos = sorted(pasta.glob("*.json"))

    if not arquivos:
        sys.exit(f"Nenhum JSON encontrado em {pasta}")

    correcoes = _carregar_glossario(args.glossario)

    qdrant = pipeline.criar_cliente_qdrant()

    print("Preparando a coleção e os índices "
          "(na primeira vez, em coleções grandes, pode levar alguns minutos)...")

    armazenamento, embedder = pipeline.preparar_colecao(args.colecao, qdrant)

    existentes = None

    if not args.substituir:
        print("Lendo a lista de documentos já cadastrados...")
        existentes = armazenamento.ids_existentes()
        print(f"{len(existentes)} documentos já cadastrados.\n")

    totais = {"inserido": 0, "ja_existe": 0, "vazio": 0, "erro": 0, "chunks": 0}

    for numero, arquivo in enumerate(arquivos, start=1):

        print(f"[{numero}/{len(arquivos)}] {arquivo.name}")

        try:
            doc = json.loads(arquivo.read_text(encoding="utf-8"))

            resultado = pipeline.ingerir_transcricao(
                args.colecao,
                doc,
                qdrant=qdrant,
                embedder=embedder,
                existentes=existentes,
                substituir=args.substituir,
                correcoes=correcoes,
                progresso=_barra
            )

            totais[resultado["status"]] += 1
            totais["chunks"] += resultado["chunks"]

            if resultado["status"] == "ja_existe":
                print("   já cadastrado, ignorado (use --substituir para reprocessar)")

        except Exception as e:
            totais["erro"] += 1
            print(f"   ERRO: {type(e).__name__}: {e}")

    print("\nResumo:", totais)


def cmd_pdf(args):

    resultado = pipeline.ingerir_pdf(
        args.colecao,
        args.arquivo,
        titulo=args.titulo,
        edicao=args.edicao,
        data_publicacao=args.data,
        substituir=args.substituir,
        paginas_sem_numero=args.capa_nao_conta,
        copiar_para=None if args.sem_copia else arquivos.PASTA_PDFS,
        progresso=_barra
    )

    print("Resultado:", resultado)

    if not args.sem_copia:
        print(f"Cópia para abrir na página exata: {arquivos.caminho_copia(resultado['doc_id'])}")


def cmd_reparar(args):

    from . import youtube

    resultado = pipeline.reparar_metadados(
        args.colecao,
        youtube.obter_metadados,
        atualizar_titulo=args.titulos,
        limite=args.limite,
        pausa=lambda: time.sleep(random.uniform(3, 7)),
        progresso=_barra
    )

    print("Resultado:", resultado)


def main(argv=None):

    parser = argparse.ArgumentParser(prog="ingestao")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("legendas", help="ingere JSONs de transcrição (vídeo ou podcast)")
    p.add_argument("--colecao", required=True)
    p.add_argument("--pasta", default="./legendas_json")
    p.add_argument("--substituir", action="store_true", help="reprocessa documentos já cadastrados")
    p.add_argument("--glossario", help="JSON {\"grafia errada\": \"grafia certa\"}")
    p.set_defaults(func=cmd_legendas)

    p = sub.add_parser("pdf", help="ingere um PDF")
    p.add_argument("--colecao", required=True)
    p.add_argument("arquivo")
    p.add_argument("--titulo")
    p.add_argument("--edicao", help='ex.: "Janeiro de 2026" (padrão: lida do nome do arquivo)')
    p.add_argument("--data", help="AAAA-MM-DD (padrão: deduzida da edição)")
    p.add_argument("--substituir", action="store_true")
    p.add_argument("--capa-nao-conta", type=int, metavar="N",
                   help="N páginas iniciais (capa etc.) não têm número; a página N+1 do arquivo é a 1. "
                        "Padrão: ler a numeração impressa no PDF")
    p.add_argument("--sem-copia", action="store_true",
                   help="não guarda cópia do PDF (sem o botão 'Abrir PDF nesta página')")
    p.set_defaults(func=cmd_pdf)

    p = sub.add_parser("reparar-metadados", help="preenche datas (e títulos) que estão faltando")
    p.add_argument("--colecao", required=True)
    p.add_argument("--titulos", action="store_true", help="também substitui o título pelo do YouTube (pt-BR)")
    p.add_argument("--limite", type=int)
    p.set_defaults(func=cmd_reparar)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
