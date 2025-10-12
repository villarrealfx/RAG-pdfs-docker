#!/usr/bin/env python3
"""
Script para resetear completamente el sistema:
- Eliminar y recrear base de datos PostgreSQL (estructura completa)
- Limpiar colección Qdrant 
- Limpiar directorios de datos
"""

import os
import sys
import logging
from pathlib import Path
import psycopg2
from psycopg2 import sql
from qdrant_client import QdrantClient
from dotenv import load_dotenv

from rag_pdf_processor.utils.config import DEV_MODE
from rag_pdf_processor.utils.logging_config import setup_logging_docker

# Cargar variables de entorno
load_dotenv()

# Configurar logging al inicio
setup_logging_docker(service_name="pdf-processor", 
                     development_mode=DEV_MODE) 
logger = logging.getLogger(__name__)

def confirm_reset():
    """Pedir confirmación antes de resetear"""
    print("\n⚠️  ADVERTENCIA: Esta operación eliminará:")
    print("   - Base de datos PostgreSQL (estructura y datos)")
    print("   - Colección Qdrant (estructura y datos)")
    print("   - Todo el contenido de los directorios de datos")
    print("   - La app se quedará como nueva (como primera ejecución)")
    print()
    
    response = input("¿Estás seguro de continuar? (escribe 'RESET' para confirmar): ")
    if response.upper() != 'RESET':
        logger.info("❌ Reset cancelado por el usuario")
        sys.exit(0)
    
    print()

def reset_postgresql():
    """Eliminar base de datos y usuario - COMPLETO"""
    logger.info("🔄 Eliminando base de datos PostgreSQL...")
    
    try:
        # Configuración de conexión como superusuario
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'user': os.getenv('SUPERUSER_NAME', 'postgres'),
            'password': os.getenv('SUPERUSER_PASSWORD', 'postgres'),
            'database': 'postgres'  # Conectar a base por defecto
        }
        
        # Conectar como superusuario
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Nombre de la base de datos y usuario a eliminar
        target_db = os.getenv('APP_DB_NAME', 'pdf_procesados')
        target_user = os.getenv('APP_DB_USER', 'usuario_pdf_app')
        
        # Terminar conexiones activas
        cursor.execute(sql.SQL("""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = %s AND pid <> pg_backend_pid();
        """), (target_db,))
        
        # Eliminar base de datos
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
            sql.Identifier(target_db)
        ))
        logger.info(f"✅ Base de datos '{target_db}' eliminada")
        
        # Eliminar usuario
        cursor.execute(sql.SQL("DROP USER IF EXISTS {}").format(
            sql.Identifier(target_user)
        ))
        logger.info(f"✅ Usuario '{target_user}' eliminado")
        
        cursor.close()
        conn.close()
        
        logger.info("✅ PostgreSQL reiniciado completamente")
        
    except Exception as e:
        logger.error(f"❌ Error reiniciando PostgreSQL: {e}")
        raise

def reset_qdrant():
    """Resetear colección Qdrant - COMPLETO"""
    logger.info("🔄 Eliminando colecciones Qdrant...")
    
    try:
        # Conectar a Qdrant
        client = QdrantClient(
            host=os.getenv('QDRANT_HOST', 'localhost'),
            port=int(os.getenv('QDRANT_PORT', 6333)),
            timeout=10.0
        )
        
        # Eliminar ambas colecciones (antigua y nueva)
        collections_to_delete = ["chunks", "chunks-hybrid"]  # Eliminar ambas
        
        for collection_name in collections_to_delete:
            try:
                client.get_collection(collection_name)
                client.delete_collection(collection_name)
                logger.info(f"✅ Colección '{collection_name}' eliminada")
            except Exception:
                logger.info(f"ℹ️  Colección '{collection_name}' no existía")
        
        logger.info("✅ Qdrant reiniciado completamente")
        
    except Exception as e:
        logger.error(f"❌ Error reiniciando Qdrant: {e}")
        raise

def reset_data_directories():
    """Limpiar directorios de datos"""
    logger.info("🔄 Reiniciando directorios de datos...")
    
    data_dirs = [
        "data/raw",
        "data/clean", 
        "data/processed",
        "data/chunks"
    ]
    
    for dir_path in data_dirs:
        dir_obj = Path(dir_path)
        if dir_obj.exists():
            # Eliminar contenido, no el directorio
            for item in dir_obj.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item)
            logger.info(f"✅ Directorio '{dir_path}' limpiado")
        else:
            dir_obj.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Directorio '{dir_path}' creado")
    
    logger.info("✅ Directorios reiniciados exitosamente")

def main():
    """Función principal de reset completo"""
    logger.info("🚀 Iniciando reset completo del sistema...")
    
    # Pedir confirmación
    confirm_reset()
    
    try:
        reset_postgresql()
        reset_qdrant()
        reset_data_directories()
        
        logger.info("🎉 ✅ Sistema reiniciado completamente!")
        logger.info("💡 Ahora puedes ejecutar:")
        logger.info("   1. uv run python -m rag_pdf_processor.utils.initialize_database")
        logger.info("   2. uv run python -m rag_pdf_processor.main")
        
    except Exception as e:
        logger.error(f"❌ Error durante el reset: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()