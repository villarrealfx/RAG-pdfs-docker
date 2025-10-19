FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY services/rag-core/requirements.txt .

# Configuración de pip
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_RETRIES=5

RUN pip install --upgrade pip
RUN pip install --no-cache-dir --retries 5 --timeout 120 -r requirements.txt

# Copiar solo los directorios necesarios
COPY services/rag-core/ /app

ENV PYTHONPATH="/app/src"

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]