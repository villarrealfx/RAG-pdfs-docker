import streamlit as st
import logging
import requests
import json
import os
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()

# --- Configuración de logging para Streamlit ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURACIÓN DE LA API FASTAPI ---
API_BASE_URL = os.getenv("FASTAPI_URL", "http://rag-core:8000")

logger.info(f"Conectando a FastAPI en: {API_BASE_URL} | FASTAPI_URL env var: {os.getenv('FASTAPI_URL')}")

# --- FUNCIONES DE COMUNICACIÓN CON LA API ---

def call_rag_api(query: str, use_query_rewrite: bool) -> Optional[Dict[str, Any]]:
    """Llama al endpoint /query_rag de FastAPI."""
    url = f"{API_BASE_URL}/query_rag"
    payload = {
        "user_query": query,
        "use_query_rewrite": use_query_rewrite  # Nuevo parámetro
    }
    
    try:
        response = requests.post(url, json=payload, timeout=600)
        response.raise_for_status()  # Lanza excepción para errores 4xx/5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al llamar a /query_rag: {e}")
        st.error(f"❌ Error al conectar o procesar la consulta RAG: {e}")
        return None

def call_feedback_api(payload: Dict[str, Any]) -> bool:
    """Llama al endpoint /submit_feedback de FastAPI."""
    url = f"{API_BASE_URL}/submit_feedback"
    
    try:
        # El payload debe coincidir con el modelo FeedbackInput de FastAPI
        response = requests.post(url, json=payload, timeout=600)
        response.raise_for_status() 
        logger.info(f"[SUCCESS] Feedback guardado exitosamente. ID: {response.json().get('feedback_id')}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[ERROR] Error al guardar feedback vía API: {e}")
        st.error(f"❌ Error al guardar tu evaluación: {e}")
        return False


# --- Configuración de la aplicación Streamlit ---
st.set_page_config(page_title="RAG System", page_icon="🤖", layout="wide")
st.title("🤖 Sistema de Recuperación Aumentada por Generación (RAG)")
st.subheader("Consulta tu base de conocimiento técnico")

# --- Inicialización de estado de sesión ---
# Solo se mantienen los estados relacionados con la UI y los datos de la última respuesta.
session_keys_defaults = {
    'last_query': "",
    'last_response': "",
    'last_retrieval_context': [], # Almacenará la lista de RAGChunkMetadata como diccionarios
    'feedback_rating': None,
    'feedback_sent': False,    
    'show_success_message': False    
}

for key, default_value in session_keys_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuración del RAG (Simulada)")
    # Estas opciones ahora son solo indicativas o deberían enviarse a FastAPI
    # En este ejemplo, las dejamos solo como UI para simplificar.
    use_query_rewrite = st.checkbox("Usar Reescritura de Consulta", value=False, disabled=False) # Habilitado
    use_rerank = st.checkbox("Usar Reclasificación de Documentos", value=True, disabled=True)
    temperature = st.slider("Temperatura del LLM", min_value=0.0, max_value=1.0, value=0.0, step=0.1, disabled=True)
    
    show_retrieved_retrieval_context = st.checkbox("Mostrar retrieval_context Recuperados", value=True)
    show_chunk_scores = st.checkbox("Mostrar Scores de retrieval_context", value=True)
    
    st.divider()
    st.info(f"Conectado a FastAPI en: **{API_BASE_URL}**")

# --- Cuerpo principal ---
query = st.text_input("Ingresa tu pregunta:", placeholder="Ej: What are the advantages of using RAG?", key="query_input")

if st.button("Obtener Respuesta", key="get_answer_btn") and query:
    # 1. Resetear estado de feedback y mensaje de éxito
    st.session_state.feedback_sent = False
    st.session_state.show_success_message = False

    st.subheader("🔍 Procesamiento de la Consulta (Vía API)")
    progress_bar = st.progress(0, text="Llamando a FastAPI...")

    try:
        # 2. Llamada a la API RAG - Se pasa el estado del checkbox
        rag_response_data = call_rag_api(query, use_query_rewrite)
        
        if rag_response_data:
            # 3. Guardar respuesta y retrieval_context en el estado desde la respuesta JSON (RAGOutput)
            st.session_state.last_query = rag_response_data.get("query_used", query)
            st.session_state.last_response = rag_response_data.get("actual_output", "Error: Respuesta LLM no encontrada.")
            st.session_state.last_retrieval_context = rag_response_data.get("retrieval_context_used", [])
            
            progress_bar.progress(100, text="¡Listo! Respuesta recibida de FastAPI.")

            # 4. Mostrar resultados inmediatamente después de la consulta
            st.subheader("💬 Respuesta del LLM")
            st.write(st.session_state.last_response)
            st.caption(f"Modelo utilizado: {rag_response_data.get('llm_model', 'N/A')}")

            if show_retrieved_retrieval_context:
                st.subheader("📚 retrieval_context Recuperados (Fuentes)")
                retrieval_context_retrieved = st.session_state.last_retrieval_context # Lista de RAGChunkMetadata
                
                if not retrieval_context_retrieved:
                    st.info("No se encontraron retrieval_context relevantes.")
                else:
                    for i, chunk in enumerate(retrieval_context_retrieved):
                        # Visualización con los campos de RAGChunkMetadata
                        score_str = f"Relevance Score: {chunk.get('relevance_score', 'N/A'):.3f}"
                        score_ini = f"Initial Score: {chunk.get('original_score', 'N/A'):.3f}"
                        
                        with st.expander(f"Chunk {i+1} ({score_str} | {score_ini}) - Fuente: {chunk.get('source_document', 'Desconocida')}"):
                            st.write(f"**ID del Chunk:** {chunk.get('chunk_id', 'N/A')}")
                            st.write(f"**Documento Fuente:** {chunk.get('source_document', 'N/A')}")
                            st.write(f"**Vista Previa:** {chunk.get('text_preview', 'N/A')}")

        else:
            progress_bar.empty()
            st.error("No se pudo obtener la respuesta de la API.")

    except Exception as e:
        logger.error(f"Ocurrió un error general durante la llamada: {e}")
        st.error(f"❌ Ocurrió un error inesperado: {e}")
    finally:
        progress_bar.empty()

# --- Sección de Feedback ---
# Se muestra solo si hay una respuesta y el feedback no ha sido enviado.
if (st.session_state.last_query and st.session_state.last_response and
    st.session_state.last_retrieval_context and not st.session_state.feedback_sent):

    # Mensaje de éxito si se acaba de enviar (usamos st.session_state.show_success_message)
    if st.session_state.get('show_success_message', False):
        st.success("✅ ¡Evaluación enviada exitosamente!")
        
    # Formulario para el feedback
    with st.form(key="feedback_form"):
        st.subheader("📊 Evalúa la respuesta")
        
        # Campo para el comentario (agregado)
        feedback_comment = st.text_area("Comentarios (Opcional):", key="feedback_comment_widget")
        
        st.session_state.feedback_rating = st.radio(
            "¿Qué tan útil fue esta respuesta? (1 = Muy pobre, 5 = Excelente)",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: '⭐' * x,
            index=2, # Valor por defecto (3 estrellas)
            key="feedback_rating_widget"
        )

        submitted = st.form_submit_button("Enviar Evaluación")
        
        if submitted:
            if st.session_state.feedback_rating is not None:
                # 1. Extraer solo los IDs de los retrieval_context (como espera el modelo FeedbackInput)
                chunk_ids_list = [chunk.get("chunk_id", "unknown") for chunk in st.session_state.last_retrieval_context]
                
                # 2. Construir el payload EXACTAMENTE como lo espera FeedbackInput de FastAPI
                feedback_payload = {
                    "query": st.session_state.last_query,
                    "actual_output": st.session_state.last_response,
                    "chunk_ids": chunk_ids_list,
                    "evaluation": st.session_state.feedback_rating,
                    "comment": feedback_comment if feedback_comment else None # Enviar None si está vacío
                }
                
                # 3. Llamar al endpoint de feedback
                success = call_feedback_api(feedback_payload)
                
                if success:
                    # Marcar como enviado y actualizar estado
                    st.session_state.feedback_sent = True
                    st.session_state.show_success_message = True
                    # Rerun para que se oculte el formulario y se muestre el mensaje de éxito
                    st.rerun() 
                # Si no es exitoso, call_feedback_api ya mostró el error.
            else:
                st.warning("Por favor, selecciona una calificación antes de enviar.")

#### ------------------------------------------------------------------ ####
# --- Sección de Gráficos de Evaluación ---
st.divider()
st.subheader("📈 Evaluación del RAG")

# Inicializar estado para mostrar/ocultar la sección de gráficos
if 'show_evaluation_charts' not in st.session_state:
    st.session_state.show_evaluation_charts = False

# Botón para mostrar/ocultar gráficos
if st.button("Mostrar/Ocultar Gráficos de Evaluación"):
    st.session_state.show_evaluation_charts = not st.session_state.show_evaluation_charts

if st.session_state.show_evaluation_charts:
    st.info("Cargando gráficos de evaluación desde la API...")

    # --- Parámetros de Filtrado ---
    col1, col2 = st.columns(2)
    with col1:
        # Opcional: Permitir filtrar por run_id si se conocen ejecuciones específicas
        run_id_filter = st.text_input("Filtrar por Run ID (opcional):", "")
    with col2:
        # Filtrar por rango de fechas
        use_date_filter = st.checkbox("Filtrar por rango de fechas")
        start_date_filter = None
        end_date_filter = None
        if use_date_filter:
            start_date_filter = st.date_input("Fecha Desde", value=None)
            end_date_filter = st.date_input("Fecha Hasta", value=None)

    # Botón para cargar datos y graficar
    if st.button("Actualizar Gráficos"):
        # Construir parámetros de la URL
        params = {}
        if run_id_filter:
            params['run_id'] = run_id_filter
        if start_date_filter:
            params['start_date'] = start_date_filter.isoformat() # Convertir a string
        if end_date_filter:
            params['end_date'] = end_date_filter.isoformat()

        try:
            # Llamar al nuevo endpoint
            url = f"{API_BASE_URL}/get_evaluation_results"
            response = requests.get(url, params=params, timeout=600) # Ajusta timeout si es necesario
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])

            if not results:
                st.warning("No se encontraron datos de evaluación con los filtros aplicados.")
            else:
                import pandas as pd
                import plotly.express as px

                # Convertir a DataFrame
                df = pd.DataFrame(results)
                df['run_timestamp'] = pd.to_datetime(df['run_timestamp']) # Asegurar tipo datetime

                # Mostrar datos crudos (opcional, para debugging)
                # st.dataframe(df)

                # Gráfico 1: Métricas por valor (barras agrupadas por métrica)
                st.subheader("Métricas por Valor (Agrupadas por Métrica)")
                if not df.empty:
                    # Agrupar por métrica y calcular promedio (o tomar el valor si es por run/query)
                    # Para simplificar, mostramos todos los valores de cada métrica
                    fig1 = px.bar(df, x='metric_name', y='metric_value',
                                 title='Valor de Métricas',
                                 color='run_id', # Diferenciar ejecuciones
                                 hover_data=['query_text', 'evaluation_suite', 'model_name', 'run_timestamp'])
                    st.plotly_chart(fig1, use_container_width=True)

                # Gráfico 2: Evolución de Métricas por Run (Líneas)
                st.subheader("Evolución de Métricas por Run (Timestamp)")
                if not df.empty:
                    # Agrupar por run_timestamp y metric_name, promediando metric_value
                    # (o tomando el valor si es por run_id específico)
                    df_grouped = df.groupby(['run_timestamp', 'metric_name'])['metric_value'].mean().reset_index()
                    fig2 = px.line(df_grouped, x='run_timestamp', y='metric_value', color='metric_name',
                                   title='Evolución de Métricas a lo largo del tiempo (Promedio por ejecución)',
                                   markers=True)
                    st.plotly_chart(fig2, use_container_width=True)

                # Gráfico 3: Métricas por Query (Radar)
                st.subheader("Perfil de Métricas por Query (Selecciona una ejecución y una query)")
                if not df.empty:
                    # Filtrar por run_id para el radar
                    available_runs = df['run_id'].unique()
                    selected_run_radar = st.selectbox("Selecciona un Run ID para el gráfico de radar", available_runs, key="radar_run")
                    df_radar = df[df['run_id'] == selected_run_radar]

                    available_queries = df_radar['query_text'].unique()
                    selected_query_radar = st.selectbox("Selecciona una Query", available_queries, key="radar_query")
                    df_radar = df_radar[df_radar['query_text'] == selected_query_radar]

                    if not df_radar.empty:
                        fig3 = px.line_polar(df_radar, r='metric_value', theta='metric_name',
                                             line_close=True,
                                             title=f'Perfil de Métricas para Run: {selected_run_radar} | Query: {selected_query_radar[:50]}...')
                        st.plotly_chart(fig3, use_container_width=True)
                    else:
                        st.warning("No hay datos para el Run ID y Query seleccionados.")


        except requests.exceptions.RequestException as e:
            logger.error(f"Error al llamar a /get_evaluation_results: {e}")
            st.error(f"❌ Error al obtener los resultados de evaluación: {e}")
        except Exception as e:
            logger.error(f"Error inesperado al procesar los resultados de evaluación: {e}")
            st.error(f"❌ Error inesperado al procesar los resultados: {e}")

#### ------------------------------------------------------------------ ####

st.divider()
st.caption("Sistema RAG desarrollado con Python, FastAPI, y Streamlit.")
st.caption("Autor: Carlos Villreal - 2025")