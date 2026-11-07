from qdrant_client import QdrantClient
from groq import Groq
import ollama

from config import (
    QDRANT_HOST,
    QDRANT_PORT,
    GROQ_API_KEY
)


# ============================================================
# QDRANT
# ============================================================

client_qdrant = QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT
)


# ============================================================
# GROQ
# ============================================================

client_groq = Groq(
    api_key=GROQ_API_KEY
)