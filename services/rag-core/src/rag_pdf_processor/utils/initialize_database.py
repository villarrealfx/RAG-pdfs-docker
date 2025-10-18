import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import logging
import os
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

load_dotenv()

# Configurar logging al inicio

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def is_running_in_docker():
    """
    Detecta si el código se está ejecutando dentro de un contenedor Docker.
    Retorna True si se detecta Docker, False en caso contrario (por ejemplo, desarrollo local).
    """
    # Método 1: Archivo mágico creado por Docker
    if os.path.exists('/.dockerenv'):
        return True
    # Método 2: Variable de entorno explícita (opcional, para control manual)
    # Puedes añadir DOCKER_ENV=true en docker-compose.yml
    if os.environ.get('DOCKER_ENV') == 'true':
        return True
    # Se puede añadir más heurísticas si fuera necesario (ej: buscar cgroup de Docker)
    return False

def get_superuser_config():
    """Configuración del superusuario (postgres) - solo para administración"""
    return {
        'dbname': 'postgres',
        'user': os.getenv('SUPERUSER_NAME', 'postgres'),
        'password': os.getenv('SUPERUSER_PASSWORD', 'postgres'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432')
    }

def get_appuser_config():
    """Configuración del usuario de aplicación - para uso normal"""
    return {
        'dbname': os.getenv('APP_DB_NAME'),  # Valor por defecto, se sobreescribe después
        'user': os.getenv('APP_DB_USER'),
        'password': os.getenv('APP_DB_PASSWORD'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432')
    }

def create_user_and_db():
    """Crear usuario y base de datos específicos (como superusuario)"""
    try:
        # Conectar como superusuario

        conn = psycopg2.connect(**get_superuser_config())
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # 1. Crear usuario si no existe
        usuario = os.getenv('APP_DB_USER')
        password = os.getenv('APP_DB_PASSWORD')

        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (usuario,))
        if not cursor.fetchone():
            cursor.execute(sql.SQL("CREATE USER {} WITH PASSWORD %s").format(
                sql.Identifier(usuario)), (password,))
            logger.info(f"Usuario '{usuario}' creado clave")
        else:
            logger.info(f"Usuario '{usuario}' ya existe")
        
        # 2. Crear base de datos si no existe
        bd_nombre = os.getenv('APP_DB_NAME')
        cursor.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s"), (bd_nombre,))
        if not cursor.fetchone():
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(bd_nombre), sql.Identifier(usuario)))
            logger.info(f"Base de datos '{bd_nombre}' creada con dueño '{usuario}'")
        else:
            logger.info(f"Base de datos '{bd_nombre}' ya existe")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error al crear usuario/BD: {e}")
        raise

def configure_permissions():
    
    """Configurar permisos específicos para el usuario de aplicación"""
    try:
        # Conectar como superusuario a la nueva BD
        config = get_superuser_config().copy()
        config['dbname'] = os.getenv('APP_DB_NAME')
        
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        user = os.getenv('APP_DB_USER')
        
        # Dar todos los privilegios al usuario en esta BD
        permits = [
            f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {user}",
            f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {user}",
            f"GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO {user}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {user}"
        ]
        
        for permit in permits:
            cursor.execute(permit)
        
        conn.commit()
        logger.info(f"Permisos configurados para usuario '{user}'")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error al configurar permisos: {e}")
        raise

def create_documents_table():
    """Crear la tabla processed_documents usando el usuario de aplicación"""
    
    # ✅ CAMBIO CLAVE: Usar get_appuser_config()
    config = get_appuser_config().copy()
    config['dbname'] = os.getenv('APP_DB_NAME')

    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Crear la tabla
        create_table_query = """
        CREATE TABLE IF NOT EXISTS processed_documents (
            id SERIAL PRIMARY KEY,
            path VARCHAR(255) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            hash_md5 VARCHAR(32),
            state BOOLEAN DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            successfully_processed BOOLEAN DEFAULT NULL,
            error_message TEXT
        );
        """
        
        # Crear índices
        create_index_query = """
        CREATE INDEX IF NOT EXISTS idx_documentos_hash ON processed_documents(hash_md5);
        CREATE INDEX IF NOT EXISTS idx_documentos_estado ON processed_documents(state);
        CREATE INDEX IF NOT EXISTS idx_documentos_nombre ON processed_documents(file_name);
        """
        
        cursor.execute(create_table_query)
        cursor.execute(create_index_query)
        conn.commit()
        
        logger.info("Tabla 'processed_documents' creada/verificada exitosamente")
        logger.info(f"Conectado como: {config['user']}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error al crear la tabla: {e}")
        raise

def verify_table_structure():
    """Verificar estructura de la tabla usando el usuario de aplicación"""
    
    # ✅ CAMBIO CLAVE: Usar get_appuser_config()
    config = get_appuser_config().copy()
    config['dbname'] = os.getenv('APP_DB_NAME')
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'processed_documents'
        ORDER BY ordinal_position;
        """)
        
        columns = cursor.fetchall()
        logger.info("=== ESTRUCTURA DE LA TABLA ===")
        logger.info(f"Usuario conectado: {config['user']}")
        
        for column in columns:
            logger.info(f"  {column[0]} ({column[1]}) - Nullable: {column[2]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error al verificar estructura: {e}")

def create_feedback_table():
    """Crear la tabla para almacenar el feedback del usuario."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS user_feedback (
        id SERIAL PRIMARY KEY,
        feedback_id TEXT UNIQUE NOT NULL, -- ID único para cada feedback
        query TEXT NOT NULL,                    -- La pregunta original del usuario
        llm_response TEXT NOT NULL,             -- La respuesta generada por el LLM
        chunk_ids TEXT,                         -- IDs de retrieval_context como cadena separada por comas
        rating INTEGER CHECK (rating >= 1 AND rating <= 5), -- Puntuación del usuario (1-5 estrellas)
        comment TEXT,                           -- Comentario adicional del usuario
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Fecha y hora del feedback
    );
    """
    # Crear índices para consultas eficientes
    create_index_query = """
    CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON user_feedback(timestamp);
    CREATE INDEX IF NOT EXISTS idx_feedback_rating ON user_feedback(rating);
    CREATE INDEX IF NOT EXISTS idx_feedback_query ON user_feedback(query);
    -- No es eficiente indexar directamente una cadena separada por comas como array sin conversión,
    -- pero puedes buscar usando LIKE si es necesario.
    -- CREATE INDEX IF NOT EXISTS idx_feedback_chunk_ids ON user_feedback(chunk_ids); -- Índice general, no específico para array
    """
    try:
        conn = psycopg2.connect(**get_appuser_config().copy())
        cursor = conn.cursor()

        cursor.execute(create_table_query)
        cursor.execute(create_index_query)
        conn.commit()

        logger.info("✅ Tabla 'user_feedback' creada/verificada exitosamente (chunk_ids como TEXT)")
        logger.info(f"Conectado como: {conn.get_dsn_parameters().get('user')}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ Error al crear la tabla de feedback: {e}")
        raise

def verify_feedback_table_structure():
    """Verificar estructura de la tabla de feedback."""
    config = get_appuser_config().copy()
    config['dbname'] = os.getenv('APP_DB_NAME')
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'user_feedback'
        ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        logger.info("=== ESTRUCTURA DE LA TABLA user_feedback ===")
        for column in columns:
            logger.info(f"  {column[0]} ({column[1]}) - Nullable: {column[2]}")

        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error al verificar estructura de feedback: {e}")

#### -------------------------------------------------------------------- ####

# --- NUEVAS FUNCIONES PARA EVALUATION RESULTS ---
def create_evaluation_results_table():
    """Crear la tabla para almacenar los resultados de las evaluaciones de DeepEval."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS evaluation_results (
        id SERIAL PRIMARY KEY,
        run_id TEXT NOT NULL, -- UUID o timestamp para identificar la ejecución
        run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Fecha y hora de la ejecución
        query_text TEXT NOT NULL, -- La pregunta evaluada (puede venir de user_feedback o de un dataset)
        metric_name TEXT NOT NULL, -- Nombre de la métrica (e.g., 'AnswerRelevancy', 'SCADA_Faithfulness')
        metric_value NUMERIC, -- Valor del score (e.g., 0.85)
        evaluation_suite TEXT, -- Nombre del conjunto de tests (e.g., 'deepeval_01', 'geval')
        model_name TEXT, -- Nombre del modelo evaluado (opcional, útil para comparaciones)
        feedback_id TEXT -- ID del feedback original en user_feedback (opcional, para trazar origen)
    );
    """
    # Crear índices para consultas eficientes
    create_indexes_queries = [
        "CREATE INDEX IF NOT EXISTS idx_eval_run_timestamp ON evaluation_results(run_timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_eval_metric_name ON evaluation_results(metric_name);",
        "CREATE INDEX IF NOT EXISTS idx_eval_evaluation_suite ON evaluation_results(evaluation_suite);",
        "CREATE INDEX IF NOT EXISTS idx_eval_feedback_id ON evaluation_results(feedback_id);",
        # Opcional: índice compuesto para consultas frecuentes
        "CREATE INDEX IF NOT EXISTS idx_eval_run_metric ON evaluation_results(run_timestamp, metric_name);",
    ]
    try:
        conn = psycopg2.connect(**get_appuser_config().copy())
        cursor = conn.cursor()

        cursor.execute(create_table_query)
        for query in create_indexes_queries:
            cursor.execute(query)
        conn.commit()

        logger.info("✅ Tabla 'evaluation_results' creada/verificada exitosamente")
        logger.info(f"Conectado como: {conn.get_dsn_parameters().get('user')}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ Error al crear la tabla de evaluación: {e}")
        raise

def verify_evaluation_results_table_structure():
    """Verificar estructura de la tabla de evaluación."""
    config = get_appuser_config().copy()
    config['dbname'] = os.getenv('APP_DB_NAME')
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'evaluation_results'
        ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        logger.info("=== ESTRUCTURA DE LA TABLA evaluation_results ===")
        for column in columns:
            logger.info(f"  {column[0]} ({column[1]}) - Nullable: {column[2]}")

        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error al verificar estructura de evaluación: {e}")

def create_expert_annotations_table():
    create_table_query = """
    CREATE TABLE IF NOT EXISTS expert_annotations (
        id SERIAL PRIMARY KEY,
        feedback_id TEXT UNIQUE, -- FK opcional a user_feedback.feedback_id
        query TEXT NOT NULL, -- La pregunta original
        actual_output TEXT, -- La respuesta generada por el LLM (opcional, para contexto)
        expected_output TEXT NOT NULL, -- La respuesta esperada según el experto
        annotated_by TEXT, -- Quién realizó la anotación
        annotation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Fecha y hora de la anotación
        original_feedback_rating INTEGER, -- Rating original del feedback (para contexto histórico)
        evaluated BOOLEAN DEFAULT FALSE -- Indica si ya fue usada en una evaluación
    );
    """
    # Crear índices para consultas eficientes
    create_indexes_queries = [
        "CREATE INDEX IF NOT EXISTS idx_exp_ann_feedback_id ON expert_annotations(feedback_id);",
        "CREATE INDEX IF NOT EXISTS idx_exp_ann_timestamp ON expert_annotations(annotation_timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_exp_ann_evaluated ON expert_annotations(evaluated);",
    ]
    try:
        conn = psycopg2.connect(**get_appuser_config().copy())
        cursor = conn.cursor()

        cursor.execute(create_table_query)
        for query in create_indexes_queries:
            cursor.execute(query)
        conn.commit()

        logger.info("✅ Tabla 'expert_annotations' creada/verificada exitosamente")
        logger.info(f"Conectado como: {conn.get_dsn_parameters().get('user')}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ Error al crear la tabla de anotaciones de experto: {e}")
        raise

def verify_expert_annotations_table_structure():
    """Verificar estructura de la tabla de anotaciones de experto."""
    config = get_appuser_config().copy()
    config['dbname'] = os.getenv('APP_DB_NAME')
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'expert_annotations'
        ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        logger.info("=== ESTRUCTURA DE LA TABLA expert_annotations ===")
        for column in columns:
            logger.info(f"  {column[0]} ({column[1]}) - Nullable: {column[2]}")

        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error al verificar estructura de anotaciones de experto: {e}")

#### -------------------------------------------------------------------- ####

def initialize_full_database():
    """Función principal para inicializar toda la base de datos"""
    try:
        logger.info("🚀 Iniciando inicialización de la base de datos...")
        logger.info(f"📍 Entorno detectado: {'Docker' if is_running_in_docker() else 'Desarrollo Local'}")

        # --- Gestión de Infraestructura (Usuario y BD) ---
        # Solo se ejecuta en desarrollo local, ya que en Docker se crea via docker-compose.yml
        
        if not is_running_in_docker():
            logger.info("⚠️ Modo Desarrollo local: Creando usuario y base de datos (si no existen)")
            # 1. Crear usuario y BD (como superusuario)
            create_user_and_db()
            
            # 2. Configurar permisos (como superusuario)
            configure_permissions()
        else:
            logger.info("🐳 Modo Docker: Usuario y BD fueron creados por docker-compose.yml.")
        
        # 3. Crear tabla (como usuario de aplicación) ✅
        logger.info("📂 Creando/verificando tabla 'processed_documents'...")
        create_documents_table()

        # 4. Crear tabla de feedback del usuario (como usuario de aplicación)
        logger.info("📊 Creando/verificando tabla 'user_feedback'...")
        create_feedback_table()

        #### ------------------------------------------------------------ ####
        # 5. Crear tabla de resultados de evaluación (como usuario de aplicación) <- NUEVO
        logger.info("📊 Creando/verificando tabla 'evaluation_results'...")
        create_evaluation_results_table()

        # 6. Crear tabla de anotaciones de experto (como usuario de aplicación) <- NUEVO
        logger.info("📊 Creando/verificando tabla 'expert_annotations'...")
        create_expert_annotations_table()

        #### ------------------------------------------------------------ ####

        # 7. Verificar estructura (como usuario de aplicación) ✅
        logger.info("🔍 Verificando estructura de las tablas...")
        verify_table_structure()
        
        # 8. Verificar estructura de feedback
        verify_feedback_table_structure()

        #### ------------------------------------------------------------ ####
        # 9. Verificar estructura de evaluación <- NUEVO
        verify_evaluation_results_table_structure()

        # 10. Verificar estructura de anotaciones <- NUEVO
        verify_expert_annotations_table_structure()

        #### ------------------------------------------------------------ ####
        
        logger.info("✅ Inicialización completada exitosamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en la inicialización: {e}")
        raise

def initialize_vector_store():
    logger.info("Inicializando Qdrant y creando colección si no existe...")
    
    # Configuración de Qdrant (ajusta según tu configuración)
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    
    try:
        # Conectar a Qdrant
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        # Nombre de la colección
        collection_name = "retrieval_context-hybrid"
        
        # Verificar si la colección existe
        collections = client.get_collections().collections
        collection_exists = any(col.name == collection_name for col in collections)
        
        if not collection_exists:
            logger.info(f"Creando colección: {collection_name}")
            # Crear la colección (ajusta los parámetros según necesites)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)  # Ajusta el tamaño según tu modelo
            )
            logger.info(f"Colección '{collection_name}' creada exitosamente")
        else:
            logger.info(f"Colección '{collection_name}' ya existe")
            
        logger.info("Qdrant inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando Qdrant: {e}")
        return False

if __name__ == "__main__":
    try:
        db_success = initialize_full_database()
        # qd_success = initialize_vector_store()
        if db_success:  # and qd_success:
            logger.info("✅ Base de datos inicializados correctamente")
            sys.exit(0)
        else:
            logger.error("❌ Hubo errores en la inicialización")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error crítico en la inicialización: {e}")
        sys.exit(1)