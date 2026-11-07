"""
Módulo de ingestão compartilhado.

Usado tanto pela linha de comando (python -m ingestao.cli ...) quanto,
mais adiante, pela página de Administração do app.

Nada aqui importa qdrant_client, ollama ou streamlit no nível do módulo:
os clientes são injetados (ou criados sob demanda), o que permite testar
tudo sem os serviços no ar.
"""
