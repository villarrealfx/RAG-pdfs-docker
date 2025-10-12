FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY services/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/frontend/app.py /app/app.py

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]