import os
import logging

import psycopg2
from psycopg2 import OperationalError, InterfaceError

from rag_pdf_processor.utils.initialize_database import get_appuser_config
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

def database_connection(config):
    """
    Establece conexión a base de datos PostgreSQL con manejo mejorado de errores
    
    Args:
        config (dict): Configuración de conexión (host, database, user, password, etc.)
    
    Returns:
        tuple: (connection, cursor) objetos
    
    Raises:
        OperationalError: Error específico de conexión a la base de datos
        Exception: Otros errores inesperados
    """
    conn = None
    cur = None
    
    try:
        conn = psycopg2.connect(**config)
        cur = conn.cursor()
        
        # Verificación adicional de que la conexión es válida
        cur.execute('SELECT 1')
        logger.info("Conexión a Base de Datos realizada con éxito y verificada")
        
        return conn, cur
        
    except OperationalError as e:
        logger.error(f"Error operacional al conectar a la base de datos: {e}")
        # Cierre seguro de recursos si se crearon parcialmente
        if cur:
            cur.close()
        if conn:
            conn.close()
        raise OperationalError(f"Error de conexión: {e}") from e
        
    except InterfaceError as e:
        logger.error(f"Error de interfaz con la base de datos: {e}")
        raise InterfaceError(f"Error de interfaz: {e}") from e
        
    except Exception as e:
        logger.error(f"Error inesperado al crear conexión a Base de Datos: {e}")
        # Cierre seguro en caso de cualquier excepción
        if cur:
            cur.close()
        if conn:
            conn.close()
        raise Exception(f"Error inesperado: {e}") from e
    
def execute_query(user, query, fetch=True, params=None):
    """
    Ejecuta consultas SQL con manejo seguro de transacciones y errores
    
    Args:
        user: Usuario que realiza la consulta
        query: Consulta SQL a ejecutar
        fetch: True para SELECT, False para INSERT/UPDATE/DELETE
    
    Returns:
        list/dict: Resultados de la consulta o información de filas afectadas
    """
    users = (os.getenv('APP_USERS', '')).split(',')
    conn, cursor = None, None
    
    try:
        
        # Validación de usuario
        if user not in users and user != 'root':
            logger.warning(f"Usuario no autorizado '{user}' - Acceso denegado")
            return {"error": "Usuario no autorizado", "status": 403}
        
        # Establecer conexión
        conn, cursor = database_connection(get_appuser_config())
        logger.info(f"Conexión establecida como usuario: {user}")
        
        # Ejecutar consulta
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Manejo de transacciones
        if not fetch:
            # Operaciones de escritura - con commit explícito
            conn.commit()
            results = {"rows_affected": cursor.rowcount, "status": "success"}
            logger.info(f"Escritura exitosa. Filas afectadas: {cursor.rowcount}")
        else:
            # Operaciones de lectura
            results = cursor.fetchall()
            if results and cursor.description:
                columns = [desc[0] for desc in cursor.description]
                results = [dict(zip(columns, row)) for row in results]
            else:
                results = []
            logger.info(f"Lectura exitosa. Filas retornadas: {len(results)}")
        
        return results
        
    except psycopg2.IntegrityError as e:
        logger.error(f"Error de integridad de datos: {e}")
        if conn:
            conn.rollback()
        return {"error": "Violación de restricciones de integridad", "status": 400}
        
    except psycopg2.ProgrammingError as e:
        logger.error(f"Error en la consulta SQL: {e}")
        if conn:
            conn.rollback()
        return {"error": "Error en la sintaxis SQL", "status": 400}
        
    except psycopg2.OperationalError as e:
        logger.error(f"Error operacional de la base de datos: {e}")
        if conn:
            conn.rollback()
        return {"error": "Error de conexión con la base de datos", "status": 503}
        
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        if conn:
            conn.rollback()
        return {"error": "Error interno del servidor", "status": 500}
        
    finally:
        # Cierre garantizado de recursos
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                logger.info("Conexión cerrada correctamente")
        except Exception as e:
            logger.warning(f"Error al cerrar recursos: {e}")
    
