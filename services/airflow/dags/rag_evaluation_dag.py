from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import requests
import json # Para manejar la respuesta JSON de la API

# Configuración de logging
logger = logging.getLogger('airflow.task')

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.task.trigger_rule import TriggerRule
from airflow.sdk import Variable

# Configuración centralizada
def get_rag_config():
    """Obtiene la configuración y la URL base de FastAPI."""
    return {
        # URL BASE de la API de Evaluación (ej. http://rag-core-service:8000)
        'api_base_url': Variable.get(
            "rag_evaluation_api_url", 
            "http://rag-core:8000" # Ajusta si tu servicio FastAPI tiene otro nombre
        ),
        # Endpoint para obtener feedback de la semana pasada
        'get_feedback_endpoint': "/get_feedback_last_week",
        # Endpoint para obtener anotaciones de expertos
        'get_annotations_endpoint': "/get_expert_annotations",
        # Endpoint para disparar la ejecución de la evaluación
        'run_evaluation_endpoint': "/run_evaluation_suite",
    }

default_args = {
    'owner': 'RAG-Team',
    'depends_on_past': False,
    'email_on_failure': True, # Ajusta según necesites
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
    'execution_timeout': timedelta(minutes=15) # Ajusta según la duración esperada de la evaluación
}

dag = DAG(
    'rag_evaluation_weekly',
    default_args=default_args,
    description='Orquestador para el pipeline de evaluación de RAG vía FastAPI.',
    schedule= None,  # '0 22 * * 0', # Domingo a las 10 PM (UTC)
    start_date=datetime(2025, 9, 20), # Ajusta la fecha de inicio
    catchup=False,
    max_active_runs=1,
    tags=['RAG', 'FastAPI', 'Evaluation', 'DeepEval'],
)

# ===== DEFINICIÓN DE FUNCIONES DEL ORQUESTADOR =====

def prepare_evaluation_data(**context):
    """
    Llama a endpoints de FastAPI para obtener feedback de la semana pasada
    y las anotaciones de experto correspondientes.
    """
    config = get_rag_config()
    url_feedback = f"{config['api_base_url']}{config['get_feedback_endpoint']}"
    url_annotations = f"{config['api_base_url']}{config['get_annotations_endpoint']}"
    
    logger.info(f"1/3. Llamando a API para obtener feedback de la semana pasada: {url_feedback}")
    
    try:
        # Petición GET para obtener feedback de la semana pasada
        # (Puede requerir parámetros como fecha_inicio y fecha_fin si no lo calcula internamente)
        response_feedback = requests.get(url_feedback, timeout=300) 
        response_feedback.raise_for_status()

        feedback_data = response_feedback.json()
        feedback_list = feedback_data.get('feedback_data', [])
        
        if not feedback_list:
            logger.info("✅ La API reporta que no hay feedback con rating bajo de la semana pasada.")
            # No hay nada que evaluar, saltamos el proceso
            context['task_instance'].xcom_push(key='evaluation_data', value=None)
            return 'skip_evaluation_task'
        
        logger.info(f"🎯 API devolvió {len(feedback_list)} entradas de feedback con rating bajo.")

        # Extraer feedback_ids para obtener anotaciones
        feedback_ids = [item['feedback_id'] for item in feedback_list if item.get('feedback_id')]
        
        logger.info(f"2/3. Llamando a API para obtener anotaciones de experto para {len(feedback_ids)} feedbacks: {url_annotations}")

        # Petición POST para obtener anotaciones de experto (o GET con query params)
        # Ajusta la estructura del payload según como lo recibas en tu endpoint
        payload = {"feedback_ids": feedback_ids}
        response_annotations = requests.post(url_annotations, json=payload, timeout=300)
        response_annotations.raise_for_status()

        annotations_data = response_annotations.json()

        print(f' OJO AQUI {annotations_data}')

        annotations_map = annotations_data.get('annotations', {})

        print(f' OJO AQUI {annotations_map}')

        logger.info(f"✅ API devolvió anotaciones para {len(annotations_map)} de {len(feedback_ids)} feedbacks solicitados.")

        # Combinar feedback y anotaciones para la siguiente tarea
        evaluation_data = {
            "feedback_list": feedback_list,
            "annotations_map": annotations_map
        }

        logger.info(f"3/3. Datos combinados listos para la evaluación.")
        context['task_instance'].xcom_push(key='evaluation_data', value=evaluation_data)
        return 'run_evaluation_task'

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red o API al preparar datos de evaluación: {e}")
        context['task_instance'].xcom_push(key='evaluation_data', value=None)
        return 'skip_evaluation_task'
    except Exception as e:
        logger.error(f"❌ Error inesperado al preparar datos de evaluación: {e}")
        context['task_instance'].xcom_push(key='evaluation_data', value=None)
        return 'skip_evaluation_task'


def run_evaluation_suite_wrapper(**context):
    """
    Llama al endpoint de FastAPI que ejecuta la suite de evaluación
    con los datos obtenidos previamente.
    """
    task_instance = context['task_instance']
    evaluation_data = task_instance.xcom_pull(
        task_ids='prepare_evaluation_task', 
        key='evaluation_data'
    )
    
    if not evaluation_data:
        logger.info("⏭️  No hay datos de evaluación para procesar.")
        # Aunque se esperaba que evaluation_data no fuera None si llega aquí,
        # por si acaso.
        return {"status": "no_data", "message": "No evaluation data provided."}

    config = get_rag_config()
    EVALUATION_URL = f"{config['api_base_url']}{config['run_evaluation_endpoint']}"
    
    logger.info(f"🔄 Enviando datos a FastAPI para ejecutar la evaluación: {EVALUATION_URL}...")
    
    try:
        # Llamar al endpoint de ejecución de evaluación
        response = requests.post(
            EVALUATION_URL, 
            json=evaluation_data, # Enviar los datos combinados
            timeout=3600 # Timeout largo, ya que la evaluación puede tardar mucho
        )
        response.raise_for_status() 

        response_json = response.json()
        
        if response_json.get("status") == "success":
            logger.info(f"✅ Evaluación ejecutada exitosamente por FastAPI.")
            logger.info(f"Mensaje de la API: {response_json.get('message', 'N/A')}")
            task_instance.xcom_push(key='evaluation_results', value=response_json)
            return response_json
        else:
            error_msg = response_json.get('message', 'Error desconocido desde la API.')
            logger.error(f"❌ Evaluación fallida en la API. Msg: {error_msg}")
            # Devolver un dict de error para el reporte
            error_result = {"status": "failed", "message": error_msg}
            task_instance.xcom_push(key='evaluation_results', value=error_result)
            return error_result

    except requests.exceptions.RequestException as e:
        error_msg = f"Error de red/API: {str(e)}"
        logger.error(f"❌ {error_msg}")
        error_result = {"status": "failed", "message": error_msg}
        task_instance.xcom_push(key='evaluation_results', value=error_result)
        return error_result
    
    except Exception as e:
        error_msg = f"Error inesperado al ejecutar la evaluación: {str(e)}"
        logger.error(f"❌ {error_msg}")
        error_result = {"status": "failed", "message": error_msg}
        task_instance.xcom_push(key='evaluation_results', value=error_result)
        return error_result


def final_report(**context):
    """
    Genera reporte final de la ejecución de la evaluación.
    """
    task_instance = context['task_instance']
    evaluation_results = task_instance.xcom_pull(task_ids='run_evaluation_task', key='evaluation_results')
    
    if evaluation_results:
        status = evaluation_results.get('status', 'unknown')
        message = evaluation_results.get('message', 'N/A')
        
        if status == 'success':
            logger.info(f"🏁 Evaluación completada exitosamente.")
            logger.info(f"Mensaje de la API: {message}")
            # Puedes incluir aquí métricas resumidas si la API las devuelve
            metrics_summary = evaluation_results.get('summary', {})
            if metrics_summary:
                logger.info(f"Resumen de métricas: {metrics_summary}")
        elif status == 'failed':
            logger.error(f"🏁 Evaluación fallida.")
            logger.error(f"Mensaje de la API: {message}")
        else:
            logger.warning(f"🏁 Evaluación completada con estado desconocido: {status}")
            logger.warning(f"Mensaje de la API: {message}")
    else:
        logger.info("🏁 No se recibieron resultados de la ejecución de la evaluación.")


# ===== DEFINICIÓN DE TAREAS Y ORQUESTACIÓN =====

# Tarea que prepara los datos (feedback + anotaciones)
prepare_evaluation_task = BranchPythonOperator(
    task_id='prepare_evaluation_task',
    python_callable=prepare_evaluation_data,
    dag=dag,
)

# Tarea que dispara la ejecución de la evaluación en FastAPI
run_evaluation_task = PythonOperator(
    task_id='run_evaluation_task',
    python_callable=run_evaluation_suite_wrapper,
    dag=dag,
    execution_timeout=timedelta(hours=2) # Ajusta según la duración típica de tus evaluaciones
)

# Tarea que se ejecuta si no hay datos para evaluar
skip_evaluation_task = EmptyOperator(
    task_id='skip_evaluation_task',
    dag=dag,
)

# Tarea que genera el reporte final
final_report_task = PythonOperator(
    task_id='final_report_task',
    python_callable=final_report,
    dag=dag,
    trigger_rule=TriggerRule.ONE_SUCCESS # Se ejecuta si evaluamos o si saltamos
)

# Tarea final
end_task = EmptyOperator(
    task_id='end_task',
    dag=dag,
)

# ===== ORQUESTACIÓN DEL FLUJO DE EVALUACIÓN =====
prepare_evaluation_task >> [run_evaluation_task, skip_evaluation_task]
run_evaluation_task >> final_report_task
skip_evaluation_task >> final_report_task
final_report_task >> end_task