FROM apache/airflow:3.1.0

# Cambia al usuario root para instalar dependencias del sistema
USER root

# Instalar dependencias del sistema necesarias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Cambia de vuelta al usuario airflow
USER airflow

# --- Instalación de dependencias de Airflow ---
# Copia el requirements.txt específico de Airflow y lo instala
WORKDIR /opt/airflow
COPY services/airflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Copia DAGs, plugins, etc. ---
COPY services/airflow/dags/ /opt/airflow/dags/
COPY services/airflow/plugins/ /opt/airflow/plugins/

# Configura los permisos para asegurar que airflow puede leer los archivos
USER root
RUN chown -R airflow:0 /opt/airflow
USER airflow