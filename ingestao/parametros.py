"""Parâmetros da ingestão. Mudou algo que afeta os chunks? Aumente VERSAO_CHUNKING."""

# ------------------------------------------------------------
# CHUNKING
# ------------------------------------------------------------

VERSAO_CHUNKING = 2

CHUNK_PALAVRAS = 160          # tamanho alvo de cada chunk
CHUNK_SOBREPOSICAO = 40       # palavras repetidas entre chunks vizinhos
CHUNK_BUSCA_FIM_FRASE = 30    # quantas palavras olhar para trás procurando fim de frase
CHUNK_MIN_PALAVRAS = 5        # chunks menores que isso são descartados
CHUNK_MIN_RESTO = 20          # sobra final menor que isso é anexada ao último chunk

# Prefixa o título/data (ou edição/tema) ao texto que vai para o embedding.
# O texto exibido e usado na busca exata continua sendo só o trecho.
USAR_CABECALHO = True

# ------------------------------------------------------------
# EMBEDDINGS
# ------------------------------------------------------------

# Acervos antigos não têm "embedding_model" no colecoes.json: usam este.
MODELO_PADRAO = "bge-m3"

MODELOS_EMBEDDING = {
    # Modelo original do projeto. Sem prefixos, para continuar compatível
    # com o que já está indexado.
    "nomic-embed-text": {"dim": 768, "prefixo_documento": "", "prefixo_consulta": ""},
    # Multilíngue (inclui português), 1024 dimensões. ollama pull bge-m3
    "bge-m3": {"dim": 1024, "prefixo_documento": "", "prefixo_consulta": ""},
}

LOTE_EMBEDDING = 32
LOTE_UPSERT = 64

# ------------------------------------------------------------
# ÍNDICES DE PAYLOAD
# ------------------------------------------------------------

INDICES_PAYLOAD = {
    "texto_bruto": "text",
    "tipo_fonte": "keyword",
    "video_id": "keyword",
    "doc_id": "keyword",
    "timestamp_segundos": "integer",
    "chunk_index": "integer",
}
