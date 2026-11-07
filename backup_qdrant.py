import os
import requests

from qdrant_client import QdrantClient


# ============================================================
# CONFIGURAÇÕES
# ============================================================

QDRANT_URL = f"http://{os.getenv('QDRANT_HOST', 'vector_db')}:6333"

PASTA_BACKUPS = os.path.join(
    os.path.dirname(__file__),
    "backups",
    "acervos"
)

qdrant_backup = QdrantClient(
    url=QDRANT_URL,
    timeout=1800
)


# ============================================================
# BACKUP DE UMA COLEÇÃO
# ============================================================

def criar_backup_qdrant(colecao_id):

    print()
    print("=" * 60)
    print("💾 BACKUP DO QDRANT")
    print("=" * 60)

    print(f"📚 Acervo: {colecao_id}")

    # --------------------------------------------------------
    # Verifica se a coleção existe
    # --------------------------------------------------------

    if not qdrant_backup.collection_exists(colecao_id):
        raise ValueError(
            f"A coleção '{colecao_id}' não existe no Qdrant."
        )

    # --------------------------------------------------------
    # Cria a pasta de backups
    # --------------------------------------------------------

    os.makedirs(
        PASTA_BACKUPS,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Cria o snapshot
    # --------------------------------------------------------

    print()
    print("🔎 Criando snapshot...")
    print("⏳ Aguarde...")

    snapshot = qdrant_backup.create_snapshot(
	    collection_name=colecao_id
	)

    print()
    print("✅ Snapshot criado.")
    print(f"   Nome: {snapshot.name}")
    print(f"   Tamanho: {snapshot.size:,} bytes")
    print(f"   Checksum: {snapshot.checksum}")

    # --------------------------------------------------------
    # Baixa o snapshot pela API REST do Qdrant
    # --------------------------------------------------------

    url = (
        f"{QDRANT_URL}/collections/"
        f"{colecao_id}/snapshots/"
        f"{snapshot.name}"
    )

    caminho_destino = os.path.join(
        PASTA_BACKUPS,
        snapshot.name
    )

    print()
    print("⬇️ Baixando snapshot...")
    print(f"   Origem: {url}")
    print(f"   Destino: {caminho_destino}")

    resposta = requests.get(
        url,
        stream=True,
        timeout=None
    )

    resposta.raise_for_status()

    # --------------------------------------------------------
    # Grava em blocos para não carregar 831 MB na memória
    # --------------------------------------------------------

    tamanho_baixado = 0

    with open(caminho_destino, "wb") as arquivo:

        for bloco in resposta.iter_content(
            chunk_size=1024 * 1024
        ):

            if bloco:

                arquivo.write(bloco)

                tamanho_baixado += len(bloco)

                tamanho_mb = (
                    tamanho_baixado / (1024 * 1024)
                )

                print(
                    f"\r   📦 Baixado: "
                    f"{tamanho_mb:,.1f} MB",
                    end="",
                    flush=True
                )

    print()

    # --------------------------------------------------------
    # Verificação básica
    # --------------------------------------------------------

    tamanho_arquivo = os.path.getsize(
        caminho_destino
    )

    print()
    print("🔎 Verificando arquivo...")

    print(
        f"   Tamanho informado pelo Qdrant: "
        f"{snapshot.size:,} bytes"
    )

    print(
        f"   Tamanho baixado: "
        f"{tamanho_arquivo:,} bytes"
    )

    if tamanho_arquivo != snapshot.size:

        os.remove(caminho_destino)

        raise RuntimeError(
            "❌ O tamanho do snapshot baixado "
            "não corresponde ao tamanho informado "
            "pelo Qdrant."
        )

    print()
    print("✅ Backup concluído com sucesso!")
    print()
    print(f"📁 Arquivo: {caminho_destino}")

    return {
        "colecao_id": colecao_id,
        "nome": snapshot.name,
        "caminho": caminho_destino,
        "size": tamanho_arquivo,
        "checksum": snapshot.checksum,
    }


# ============================================================
# TESTE DIRETO
# ============================================================

if __name__ == "__main__":

    resultado = criar_backup_qdrant(
        "acervo_kim_painho"
    )

    print()
    print("=" * 60)
    print("📦 RESULTADO")
    print("=" * 60)

    print(
        f"Acervo: {resultado['colecao_id']}"
    )

    print(
        f"Arquivo: {resultado['nome']}"
    )

    print(
        f"Tamanho: {resultado['size']:,} bytes"
    )

    print(
        f"Checksum: {resultado['checksum']}"
    )

    print(
        f"Caminho: {resultado['caminho']}"
    )