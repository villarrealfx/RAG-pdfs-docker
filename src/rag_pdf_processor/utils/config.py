import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
load_dotenv()

# Detectar si estamos en Docker (verificando si existe un archivo específico de Docker)
def is_running_in_docker():
    """Detecta si el código se está ejecutando dentro de un contenedor Docker"""
    return os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV', False)

# Configuración Desarrollo vs Producción según entorno
DEV_MODE = not is_running_in_docker() # True si NO está en Docker (desarrollo local)

# Directorio raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()

# Rutas comunes
DATA_DIR = PROJECT_ROOT / 'data'
CHUNKS_DATA_DIR = PROJECT_ROOT / 'chunks'
UTILS_FILES = PROJECT_ROOT / 'utils'
MODEL_CACHE_DIR = PROJECT_ROOT / 'models'
# Rutas data
RAW_DATA_DIR = DATA_DIR / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / 'processed'
CLEAN_DATA_DIR = DATA_DIR / 'clean'

# Conexión Base de Datos Postgres
APP_USER = os.getenv('APP_DB_USER')
APP_PASSWORD = os.getenv('APP_DB_PASSWORD', 'password_seguro_123')
DB_NAME = os.getenv('APP_DB_NAME', 'scada_rag')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
encoded_password = quote_plus(APP_PASSWORD)
PG_CONNECTION = f"postgresql://{APP_USER}:{encoded_password}@{DB_HOST}/{DB_NAME}"