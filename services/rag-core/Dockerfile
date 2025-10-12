FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY services/rag-core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo los directorios necesarios
COPY services/rag-core/ /app

ENV PYTHONPATH="/app/src"

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]