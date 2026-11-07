FROM python:3.11-slim

# 1. Instala dependências do sistema operacional necessárias para renderizar PDFs
RUN apt-get update && apt-get install -y \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Define o diretório de trabalho dentro do container
WORKDIR /app

# 3. Copia o arquivo de requisitos e instala as bibliotecas Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copia o restante do código da sua aplicação para dentro do container
COPY . .

# 5. Expõe a porta padrão que o Streamlit usa
EXPOSE 8501

# 6. EXECUTADO AUTOMATICAMENTE: Ativa o Streamlit assim que o container liga
# Configurado para rodar em modo serverless na porta exposta
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
