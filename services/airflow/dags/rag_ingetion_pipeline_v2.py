"""
DAG ADAPTADO A MICROSERVICIOS. Ahora funciona como ORQUESTADOR,
llamando a endpoints de FastAPI para toda la lógica de negocio (scan, hash, check, process).
"""

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import requests
import json # Para manejar la respuesta JSON de la API

# Configuración de logging
logger = logging.getLogger('airflow.task')

# No necesitamos importar las funciones locales del RAG aquí, ¡FastAPI las maneja!

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.task.trigger_rule import TriggerRule
from airflow.sdk import Variable

# Configuración centralizada
def get_rag_config():
    """Obtiene la configuración y la URL base de FastAPI."""
    return {
        # URL BASE de la API de Ingestión (ej. http://rag-core-service:8000)
        'api_base_url': Variable.get(
            "rag_ingestion_api_url", 
            "http://rag-core:8000"
        ),
        # Endpoint unificado para los primeros 3 pasos
        'metadata_endpoint': "/ingest_metadata_only",
        # Endpoint para el procesamiento individual del documento
        'process_endpoint': "/process_document",
    }

default_args = {
    'owner': 'RAG-Team',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
    'execution_timeout': timedelta(minutes=15)
}

dag = DAG(
    'rag_ingestion_api_orchestrator',
    default_args=default_args,
    description='Orquestador para el pipeline de ingesta de documentos RAG vía FastAPI',
    schedule= None,   # "*/15 * * * *", # "*/15 * * * *""
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['RAG', 'FastAPI', 'Orchestration'],
)

# ===== DEFINICIÓN DE FUNCIONES DEL ORQUESTADOR =====

def prepare_ingestion_metadata(**context):
    """
    Llama a un endpoint único de FastAPI para escanear carpetas,
    calcular hashes y verificar el estado de procesamiento.
    Recupera la lista de archivos pendientes de la API.
    """
    config = get_rag_config()
    url = f"{config['api_base_url']}{config['metadata_endpoint']}"
    
    logger.info(f"1/3. Llamando a API para escanear y chequear estado: {url}")
    
    try:
        # Petición GET al endpoint unificado (puede requerir parámetros si es necesario)
        response = requests.get(url, timeout=300) 
        response.raise_for_status() # Lanza HTTPError para 4xx/5xx

        api_data = response.json()
        
        # FastAPI devuelve la lista de archivos pendientes, cada elemento es [ruta_local, hash]
        # Ejemplo: pending_files = [["/path/to/doc.pdf", "hash_value"], ...]
        pending_files = api_data.get('pending_files', [])
        
        
        if not pending_files:
            logger.info("✅ La API reporta que no hay archivos nuevos o pendientes.")
            context['task_instance'].xcom_push(key='pending_files', value=[])
            return 'skip_processing_task'
        
        logger.info(f"🎯 API devolvió {len(pending_files)} archivos pendientes de procesar.")
        
        # Guardar la lista de archivos y hashes para la siguiente tarea
        context['task_instance'].xcom_push(key='pending_files', value=pending_files)
        return 'process_document_task'
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red o API al chequear metadata: {e}")
        context['task_instance'].xcom_push(key='pending_files', value=[])
        # Si falla, no podemos procesar, así que saltamos
        return 'skip_processing_task'
        

def process_documents_wrapper(**context):
    """
    Itera sobre los documentos pendientes y envía cada uno a FastAPI 
    con su archivo binario y hash.
    """
    task_instance = context['task_instance']
    pending_files = task_instance.xcom_pull(
        task_ids='prepare_ingestion_task', 
        key='pending_files'
    )
    
    if not pending_files:
        logger.info("⏭️  No hay documentos pendientes para el procesamiento final.")
        return { "processed": 0, "failed": 0, "total": 0, "errors": [] }
    
    config = get_rag_config()
    PROCESSING_URL = f"{config['api_base_url']}{config['process_endpoint']}"
    
    results = {
        "processed": 0,
        "failed": 0,
        "total": len(pending_files),
        "errors": [],
        "failed_files": []
    }
    
    logger.info(f"🔄 Enviando {len(pending_files)} documentos a FastAPI para procesamiento pesado ({PROCESSING_URL})...")
    
    for file_path_str, file_hash in pending_files:
        file_path = Path(file_path_str)
        file_name = file_path.name
        
        try:
            logger.info(f"📄 Enviando: {file_name} (Hash: {file_hash})")
            
            # 1. Leer archivo y preparar datos multipart
            # Es vital que Airflow tenga acceso al sistema de archivos donde residen los PDF
            # with open(file_path, 'rb') as f:
            #     files = {'file': (file_name, f.read(), 'application/pdf')}
            
            # 2. Datos de formulario adicionales (hash)
            # El hash es enviado como dato de formulario para que FastAPI lo reciba

            path_file_clean = f'data/processed/{file_name}'
            data = {
                'path_file': file_path_str,
                'path_file_clean':path_file_clean,
                'hash_file': file_hash
                }
            
            # 3. Llamar a FastAPI Processing Endpoint (POST con multipart/form-data)

            logger.info(f'datos a enviar: {data} \ntipo de datos: {type(data)}')

            response = requests.post(
                PROCESSING_URL, 
                # files=files, 
                json=data, 
                timeout=3600 # Un timeout largo para el procesamiento de embeddings
            )
            response.raise_for_status() 

            response_json = response.json()
            
            if response_json.get("status") == "success":
                results["processed"] += 1
                logger.info(f"✅ {file_name} procesado exitosamente por FastAPI.")
            else:
                results["failed"] += 1
                results["failed_files"].append(file_name)
                logger.warning(f"⚠️  {file_name} Falló en la API. Msg: {response_json.get('message', 'Error desconocido')}")

        except requests.exceptions.RequestException as e:
            results["failed"] += 1
            error_msg = f"{file_name}: Error de red/API: {str(e)}"
            results["errors"].append(error_msg)
            results["failed_files"].append(file_name)
            logger.error(f"❌ Error HTTP/API procesando {file_name}: {e}")
        
        except Exception as e:
            results["failed"] += 1
            error_msg = f"{file_name}: Error local al leer el archivo: {str(e)}"
            results["errors"].append(error_msg)
            results["failed_files"].append(file_name)
            logger.error(f"❌ Error inesperado al leer {file_name}: {e}")
            continue
    
    # Reporte final
    logger.info(
        f"📈 Procesamiento completado (Final): "
        f"{results['processed']} exitosos, "
        f"{results['failed']} fallidos"
    )
    
    task_instance.xcom_push(key='processing_results', value=results)
    return results

def final_report(**context):
    """
    Genera reporte final del procesamiento.
    """
    task_instance = context['task_instance']
    processing_results = task_instance.xcom_pull(task_ids='process_document_task', key='processing_results')
    
    # Intentamos obtener el conteo total de archivos escaneados (si la API lo devolviera)
    # Aquí asumimos que todos los archivos escaneados eran los del total
    total_scanned = processing_results.get('total', 0) if processing_results else 0
    
    if processing_results:
        logger.info(
            f"🏁 RESUMEN FINAL - "
            f"Archivos verificados: {total_scanned}, "
            f"Procesados (API): {processing_results['processed']}, "
            f"Fallidos: {processing_results['failed']}"
        )
        
        if processing_results['failed'] > 0:
            logger.warning(
                f"📋 Archivos con problemas: {processing_results['failed_files']}"
            )
    else:
        logger.info("🏁 No se requirió procesamiento.")


# ===== DEFINICIÓN DE TAREAS Y ORQUESTACIÓN =====

# Tarea ÚNICA que reemplaza a scan_documents, hash_documents y check_processed_status
prepare_ingestion_task = BranchPythonOperator(
    task_id='prepare_ingestion_task',
    python_callable=prepare_ingestion_metadata,
    dag=dag,
)

process_document_task = PythonOperator(
    task_id='process_document_task',
    python_callable=process_documents_wrapper,
    dag=dag,
    execution_timeout=timedelta(hours=1, minutes=30)
)

skip_processing_task = EmptyOperator(
    task_id='skip_processing_task',
    dag=dag,
)

final_report_task = PythonOperator(
    task_id='final_report_task',
    python_callable=final_report,
    dag=dag,
    trigger_rule=TriggerRule.ONE_SUCCESS # Se ejecuta si procesamos o si saltamos
)

end_task = EmptyOperator(
    task_id='end_task',
    dag=dag,
)

# ===== ORQUESTACIÓN DEL NUEVO FLUJO =====
prepare_ingestion_task >> [process_document_task, skip_processing_task]
process_document_task >> final_report_task
skip_processing_task >> final_report_task
final_report_task >> end_task