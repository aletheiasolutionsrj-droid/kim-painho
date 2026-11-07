#!/bin/sh

echo "=========================================="
echo " INICIANDO OLLAMA"
echo "=========================================="

ollama serve &

echo "Aguardando Ollama iniciar..."

until ollama list >/dev/null 2>&1; do
    sleep 2
done

echo "Ollama iniciado."

# Modelos de embedding que devem existir. Configure em MODELOS_OLLAMA (docker-compose, serviço ollama);
# sem a variável, baixa os dois suportados. Ao abandonar um modelo, tire-o desta lista, senão ele
# volta a ser baixado a cada inicialização.
for modelo in ${MODELOS_OLLAMA:-nomic-embed-text bge-m3}; do

    echo "Verificando modelo $modelo..."

    if ! ollama list | grep -q "$modelo"; then
        echo "Modelo não encontrado. Baixando $modelo..."
        ollama pull "$modelo" && echo "Modelo $modelo baixado com sucesso."
    else
        echo "Modelo $modelo já está disponível."
    fi

done

echo "=========================================="
echo " OLLAMA PRONTO"
echo "=========================================="

wait
