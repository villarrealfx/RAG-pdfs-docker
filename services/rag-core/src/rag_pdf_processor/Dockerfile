FROM python:3.11-slim

WORKDIR /app

# Copiar dependencias
COPY pyproject.toml uv.lock ./
RUN pip install uv
RUN uv pip install -r uv.lock

# Copiar código del servicio
COPY services/pdf-processor/ ./
COPY models/ /app/models/
COPY data/ /app/data/

# Directorios de trabajo
VOLUME ["/app/data", "/app/logs"]

CMD ["python", "main.py"]