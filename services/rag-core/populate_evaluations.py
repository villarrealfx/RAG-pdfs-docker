import json
import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
load_dotenv()

# --- Configuración de la conexión a la base de datos ---
# Ajusta estos valores según tu configuración de PostgreSQL
DB_CONFIG = {
    'dbname': os.getenv('APP_DB_NAME'), 
    'user': os.getenv('APP_DB_USER'),       
    'password': os.getenv('APP_DB_PASSWORD'),   
    'host': os.getenv('RAG_DB_HOST'),           
    'port': '5432'                 
}

# Nombre de la tabla
TABLE_NAME = 'evaluation_results'

# Ruta al archivo JSON con los datos iniciales
JSON_FILE_PATH = 'initial_evaluation_data.json' 

def connect_to_db():
    """Establece la conexión con la base de datos."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Error conectando a la base de datos: {e}")
        return None

def read_json_data(filepath):
    """Lee los datos del archivo JSON."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results', []) 
    except FileNotFoundError:
        print(f"Archivo no encontrado: {filepath}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return []

def insert_data_to_db(conn, data):
    """Inserta los datos en la tabla especificada."""
    if not data:
        print("No hay datos para insertar.")
        return

    cursor = conn.cursor()
    # Asegúrate de que las columnas coincidan con tu tabla
    insert_query = f"""
        INSERT INTO {TABLE_NAME} 
        (run_id, run_timestamp, query_text, metric_name, metric_value, evaluation_suite, model_name, feedback_id)
        VALUES %s
        """

    # Preparar los datos para execute_values
    # Cada tupla debe seguir el mismo orden que las columnas en el INSERT
    values = [
        (
            item['run_id'],
            item['run_timestamp'],
            item['query_text'],
            item['metric_name'],
            item['metric_value'],
            item['evaluation_suite'],
            item['model_name'],
            item['feedback_id']
        )
        for item in data
    ]

    try:
        execute_values(cursor, insert_query, values, template=None, page_size=100)
        conn.commit()
        print(f"Se insertaron {len(values)} registros en la tabla {TABLE_NAME}.")
    except psycopg2.Error as e:
        print(f"Error insertando datos: {e}")
        conn.rollback()
    finally:
        cursor.close()

def main():
    """Función principal."""
    # 1. Leer datos del JSON
    print("Leyendo datos del archivo JSON...")
    data_to_insert = read_json_data(JSON_FILE_PATH)

    if not data_to_insert:
        print("No se encontraron datos válidos en el archivo JSON.")
        return

    print(f"Se encontraron {len(data_to_insert)} registros para insertar.")

    # 2. Conectar a la base de datos
    print("Conectando a la base de datos...")
    conn = connect_to_db()
    if not conn:
        print("No se pudo conectar a la base de datos. Abortando.")
        return

    try:
        # 3. Insertar datos
        print("Insertando datos en la base de datos...")
        insert_data_to_db(conn, data_to_insert)
    finally:
        # 4. Cerrar conexión
        conn.close()
        print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    main()
