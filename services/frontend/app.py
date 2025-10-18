import streamlit as st
import logging
import requests
import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()

# --- Logging configuration for Streamlit ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FASTAPI API CONFIGURATION ---
API_BASE_URL = os.getenv("FASTAPI_URL", "http://rag-core:8000")

logger.info(f"Connecting to FastAPI at: {API_BASE_URL} | FASTAPI_URL env var: {os.getenv('FASTAPI_URL')}")

# --- API COMMUNICATION FUNCTIONS ---

def call_rag_api(query: str, use_query_rewrite: bool) -> Optional[Dict[str, Any]]:
    """Calls the /query_rag endpoint of FastAPI."""
    url = f"{API_BASE_URL}/query_rag"
    payload = {
        "user_query": query,
        "use_query_rewrite": use_query_rewrite  # New parameter
    }
    
    try:
        response = requests.post(url, json=payload, timeout=600)
        response.raise_for_status()  # Raises exception for 4xx/5xx errors
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling /query_rag: {e}")
        st.error(f"❌ Error connecting or processing RAG query: {e}")
        return None

def call_feedback_api(payload: Dict[str, Any]) -> bool:
    """Calls the /submit_feedback endpoint of FastAPI."""
    url = f"{API_BASE_URL}/submit_feedback"
    
    try:
        # Payload must match FastAPI's FeedbackInput model
        response = requests.post(url, json=payload, timeout=600)
        response.raise_for_status() 
        logger.info(f"[SUCCESS] Feedback saved successfully. ID: {response.json().get('feedback_id')}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[ERROR] Error saving feedback via API: {e}")
        st.error(f"❌ Error saving your evaluation: {e}")
        return False


# --- Streamlit application configuration ---
st.set_page_config(page_title="RAG System", page_icon="🤖", layout="wide")
st.title("🤖 Retrieval-Augmented Generation (RAG) System")
st.subheader("Query your technical knowledge base")

# --- Session state initialization ---
# Only maintaining states related to UI and last response data.
session_keys_defaults = {
    'last_query': "",
    'last_response': "",
    'last_retrieval_context': [], # Will store list of RAGChunkMetadata as dictionaries
    'feedback_rating': None,
    'feedback_sent': False,    
    'show_success_message': False    
}

for key, default_value in session_keys_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ RAG Configuration (Simulated)")
    # These options are now only indicative or should be sent to FastAPI
    # In this example, we keep them as UI only for simplicity.
    use_query_rewrite = st.checkbox("Use Query Rewriting", value=False, disabled=False) # Enabled
    use_rerank = st.checkbox("Use Document Re-ranking", value=True, disabled=True)
    temperature = st.slider("LLM Temperature", min_value=0.0, max_value=1.0, value=0.0, step=0.1, disabled=True)
    
    show_retrieved_retrieval_context = st.checkbox("Show Retrieved Contexts", value=True)
    show_chunk_scores = st.checkbox("Show Chunk Scores", value=True)
    
    st.divider()
    st.info(f"Connected to FastAPI at: **{API_BASE_URL}**")

# --- Main body ---
query = st.text_input("Enter your question:", placeholder="E.g.: What are the advantages of using RAG?", key="query_input")

if st.button("Get Answer", key="get_answer_btn") and query:
    # 1. Reset feedback state and success message
    st.session_state.feedback_sent = False
    st.session_state.show_success_message = False

    st.subheader("🔍 Query Processing (Via API)")
    progress_bar = st.progress(0, text="Calling FastAPI...")

    try:
        # 2. RAG API call - Passing the checkbox state
        rag_response_data = call_rag_api(query, use_query_rewrite)
        
        if rag_response_data:
            # 3. Save response and contexts in state from JSON response (RAGOutput)
            st.session_state.last_query = rag_response_data.get("query_used", query)
            st.session_state.last_response = rag_response_data.get("actual_output", "Error: LLM response not found.")
            st.session_state.last_retrieval_context = rag_response_data.get("retrieval_context_used", [])
            
            progress_bar.progress(100, text="Done! Response received from FastAPI.")

            # 4. Show results immediately after query
            st.subheader("💬 LLM Response")
            st.write(st.session_state.last_response)
            st.caption(f"Model used: {rag_response_data.get('llm_model', 'N/A')}")

            if show_retrieved_retrieval_context:
                st.subheader("📚 Retrieved Contexts (Sources)")
                retrieval_context_retrieved = st.session_state.last_retrieval_context # List of RAGChunkMetadata
                
                if not retrieval_context_retrieved:
                    st.info("No relevant contexts found.")
                else:
                    for i, chunk in enumerate(retrieval_context_retrieved):
                        # Visualization with RAGChunkMetadata fields
                        score_str = f"Relevance Score: {chunk.get('relevance_score', 'N/A'):.3f}"
                        score_ini = f"Initial Score: {chunk.get('original_score', 'N/A'):.3f}"
                        
                        with st.expander(f"Chunk {i+1} ({score_str} | {score_ini}) - Source: {chunk.get('source_document', 'Unknown')}"):
                            st.write(f"**Chunk ID:** {chunk.get('chunk_id', 'N/A')}")
                            st.write(f"**Source Document:** {chunk.get('source_document', 'N/A')}")
                            st.write(f"**Preview:** {chunk.get('text_preview', 'N/A')}")

        else:
            progress_bar.empty()
            st.error("Could not get response from API.")

    except Exception as e:
        logger.error(f"General error occurred during call: {e}")
        st.error(f"❌ Unexpected error occurred: {e}")
    finally:
        progress_bar.empty()

# --- Feedback Section ---
# Only shown if there is a response and feedback hasn't been sent.
if (st.session_state.last_query and st.session_state.last_response and
    st.session_state.last_retrieval_context and not st.session_state.feedback_sent):

    # Success message if just sent (using st.session_state.show_success_message)
    if st.session_state.get('show_success_message', False):
        st.success("✅ Evaluation submitted successfully!")
        
    # Feedback form
    with st.form(key="feedback_form"):
        st.subheader("📊 Evaluate the Response")
        
        # Comment field (added)
        feedback_comment = st.text_area("Comments (Optional):", key="feedback_comment_widget")
        
        st.session_state.feedback_rating = st.radio(
            "How helpful was this response? (1 = Very poor, 5 = Excellent)",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: '⭐' * x,
            index=2, # Default value (3 stars)
            key="feedback_rating_widget"
        )

        submitted = st.form_submit_button("Submit Evaluation")
        
        if submitted:
            if st.session_state.feedback_rating is not None:
                # 1. Extract only context IDs (as expected by FeedbackInput model)
                chunk_ids_list = [chunk.get("chunk_id", "unknown") for chunk in st.session_state.last_retrieval_context]
                
                # 2. Build payload EXACTLY as expected by FastAPI's FeedbackInput
                feedback_payload = {
                    "query": st.session_state.last_query,
                    "actual_output": st.session_state.last_response,
                    "chunk_ids": chunk_ids_list,
                    "evaluation": st.session_state.feedback_rating,
                    "comment": feedback_comment if feedback_comment else None # Send None if empty
                }
                
                # 3. Call feedback endpoint
                success = call_feedback_api(feedback_payload)
                
                if success:
                    # Mark as sent and update state
                    st.session_state.feedback_sent = True
                    st.session_state.show_success_message = True
                    # Rerun to hide form and show success message
                    st.rerun() 
                # If not successful, call_feedback_api already showed the error.
            else:
                st.warning("Please select a rating before submitting.")

 # --- General Feedback Charts Section ---
st.divider()
st.subheader("📊 User Feedback Overview")

# Button to load and show feedback chart
if st.button("Update Feedback Charts"):
    # This logic only runs when the button is pressed
    try:
        url = f"{API_BASE_URL}/get_feedback_ratings"
        st.info(f"Calling: {url}")
        response = requests.get(url, timeout=600)
        response.raise_for_status()

        data = response.json()
        ratings_data = data.get('ratings', [])

        if not ratings_data:
            st.warning("No feedback ratings data found.")
        else:
            # Create DataFrame
            df_feedback = pd.DataFrame(ratings_data)

            # Pie chart
            import plotly.graph_objects as go
            if not df_feedback.empty:
                labels = []
                rating = df_feedback['rating'].tolist()
                for r in rating:
                    if r == 1:
                        labels.append('Very Poor')
                    if r == 2:
                        labels.append('Poor')
                    if r == 3:
                        labels.append('Needs Improvement')
                    if r == 4:
                        labels.append('Good')
                    if r == 5:
                        labels.append('Excellent')    

                values = df_feedback['count'].tolist()

                fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, textinfo='label+percent',
                            insidetextorientation='radial'
                        )])


                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.warning("Could not create data for feedback chart (df_feedback is empty).")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling /get_feedback_ratings: {e}")
        st.error(f"❌ Error getting feedback data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing feedback data: {e}")
        st.error(f"❌ Unexpected error processing feedback data: {e}")

# --- Evaluation Charts Section ---
st.divider()
st.subheader("📈 RAG Evaluation")

# Initialize state to show/hide evaluation charts section
if 'show_evaluation_charts' not in st.session_state:
    st.session_state.show_evaluation_charts = False

# Initialize state to store loaded evaluation data
if 'evaluation_data' not in st.session_state:
    st.session_state.evaluation_data = pd.DataFrame()

# Button to show/hide charts
if st.button("Show/Hide Evaluation Charts"):
    st.session_state.show_evaluation_charts = not st.session_state.show_evaluation_charts

if st.session_state.show_evaluation_charts:
    st.info("Loading evaluation charts from API...")

    # --- Filtering Parameters ---
    col1, col2 = st.columns(2)
    with col1:
        run_id_filter = st.text_input("Filter by Run ID (optional):", "")
    with col2:
        use_date_filter = st.checkbox("Filter by date range")
        start_date_filter = None
        end_date_filter = None
        if use_date_filter:
            start_date_filter = st.date_input("Date From", value=None)
            end_date_filter = st.date_input("Date To", value=None)

    # Button to load data and plot
    if st.button("Update Charts"):
        # Reset previous data when loading new ones
        st.session_state.evaluation_data = pd.DataFrame()
        params = {}
        if run_id_filter:
            params['run_id'] = run_id_filter
        if start_date_filter:
            params['start_date'] = start_date_filter.isoformat()
        if end_date_filter:
            params['end_date'] = end_date_filter.isoformat()

        try:
            url = f"{API_BASE_URL}/get_evaluation_results"
            response = requests.get(url, params=params, timeout=600)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])

            if not results:
                st.warning("No evaluation data found with applied filters.")
            else:
                # import pandas as pd
                df = pd.DataFrame(results)
                df['run_timestamp'] = pd.to_datetime(df['run_timestamp'])

                # Save loaded data in session state
                st.session_state.evaluation_data = df

                st.success(f"✅ Data loaded. {len(df)} results available.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling /get_evaluation_results: {e}")
            st.error(f"❌ Error getting evaluation results: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing evaluation results: {e}")
            st.error(f"❌ Unexpected error processing results: {e}")

    # --- Show Charts if there is data in state ---
    df = st.session_state.evaluation_data

    if not df.empty:

        # <<<<<<<<<<<<<<<<<< Charts >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

        # Chart 1: Metric Behavior - Box and Whisker
        st.subheader("Metric Behavior Distribution")
        fig1 = px.box(df, x='metric_name', y='metric_value', 
              title='Score Distribution by Metric',
              color='metric_name')
        fig1.update_layout(xaxis_title='Metric', yaxis_title='Score')
        
        st.plotly_chart(fig1, use_container_width=True)

        # Chart 2: Scores by Query and Metric
        st.subheader("Scores by Query and Metric")
        # Interactive scatter plot
        fig2 = px.scatter(df, x='query_text', y='metric_value', 
                        color='metric_name', size='metric_value',
                        title='Scores by Query and Metric',
                        hover_data=['model_name', 'run_timestamp'])
        fig2.update_layout(
            xaxis_title='Query',
            yaxis_title='Score',
            xaxis={'tickangle': 45, 'showticklabels': False},  # Hide labels due to length
            height=600)
        st.plotly_chart(fig2, use_container_width=True)

        # Chart 3: Metrics by query
        st.subheader("Metrics by Query")
        # Calculate metric averages
        metric_means = df.groupby('metric_name')['metric_value'].mean().reset_index()

        fig3c = go.Figure()

        fig3c.add_trace(go.Scatterpolar(
            r=metric_means['metric_value'],
            theta=metric_means['metric_name'],
            fill='toself',
            name='Metric Averages'
        ))

        fig3c.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1]
                )),
            showlegend=True,
            title='Radar Chart - Metric Averages'
        )
        st.plotly_chart(fig3c, use_container_width=True)

        # Chart 4: Metrics by Query (Radar) - NOW WITH STATE DATA
        st.subheader("Metric Profile by Query (Select a run and a query)")
        # Filter by run_id for radar
        available_runs = df['run_id'].unique()
        # Use st.selectbox without fixed key to avoid conflict with general state
        # But use previously selected value if exists in state
        if 'selected_run_radar' not in st.session_state:
            st.session_state.selected_run_radar = available_runs[0] if len(available_runs) > 0 else None

        selected_run_radar = st.selectbox(
            "Select a Run ID for radar chart",
            options=available_runs,
            index=list(available_runs).index(st.session_state.selected_run_radar) if st.session_state.selected_run_radar in available_runs else 0,
            key="radar_run_temp" # Temporary key to avoid conflict with state
        )
        # Update state only if value changes
        if selected_run_radar != st.session_state.selected_run_radar:
            st.session_state.selected_run_radar = selected_run_radar
            # Reset selected query if run_id changes
            st.session_state.selected_query_radar = None

        df_radar = df[df['run_id'] == st.session_state.selected_run_radar]

        if not df_radar.empty:
            available_queries = df_radar['query_text'].unique()
            # Use st.selectbox for query
            if 'selected_query_radar' not in st.session_state or st.session_state.selected_query_radar not in available_queries:
                 st.session_state.selected_query_radar = available_queries[0] if len(available_queries) > 0 else None

            selected_query_radar = st.selectbox(
                "Select a Query",
                options=available_queries,
                index=list(available_queries).index(st.session_state.selected_query_radar) if st.session_state.selected_query_radar in available_queries else 0,
                key="radar_query_temp" # Temporary key
            )
            # Update state only if value changes
            if selected_query_radar != st.session_state.selected_query_radar:
                st.session_state.selected_query_radar = selected_query_radar

            df_final_radar = df_radar[df_radar['query_text'] == st.session_state.selected_query_radar]

            if not df_final_radar.empty:
                fig3 = px.line_polar(df_final_radar, r='metric_value', theta='metric_name',
                                     line_close=True,
                                     title=f'Metric Profile for Run: {st.session_state.selected_run_radar} | Query: {st.session_state.selected_query_radar[:50]}...')
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.warning("No data for selected Run ID and Query.")
        else:
            st.warning("No data for selected Run ID.")

        # Chart 4: Simple histogram of all metrics
        df_clean = df[df['metric_value'] <= 1.0]
        # Create categories
        df_clean['score_category'] = pd.cut(df_clean['metric_value'], 
                                   bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                                   labels=['0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0'])
        fig11 = px.histogram(df_clean, x='score_category',
                   title='Distribution by Score Categories')
        
        st.plotly_chart(fig11, use_container_width=True)

        # Chart 5: Metrics by value (bars grouped by metric)
        st.subheader("Metrics by Value (Grouped by Metric)")
        fig1 = px.bar(df, x='metric_name', y='metric_value',
                     title='Metric Values',
                     color='run_id', # Differentiate runs
                     hover_data=['query_text', 'evaluation_suite', 'model_name', 'run_timestamp'])
        st.plotly_chart(fig1, use_container_width=True)

        # Chart 6: Metric Evolution by Run (Lines)
        st.subheader("Metric Evolution by Run (Timestamp)")
        df_grouped = df.groupby(['run_timestamp', 'metric_name'])['metric_value'].mean().reset_index()
        fig2 = px.line(df_grouped, x='run_timestamp', y='metric_value', color='metric_name',
                       title='Metric Evolution Over Time (Average per run)',
                       markers=True)
        st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.caption("RAG System developed with Python, FastAPI, and Streamlit.")
st.caption("Author: Carlos Villreal - 2025")

# ---------------------------------------------------------------------- #

# import streamlit as st
# import logging
# import requests
# import json
# import os

# import pandas as pd
# import plotly.express as px
# import plotly.graph_objects as go
# from typing import List, Dict, Any, Optional

# from dotenv import load_dotenv
# load_dotenv()

# # --- Configuración de logging para Streamlit ---
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- CONFIGURACIÓN DE LA API FASTAPI ---
# API_BASE_URL = os.getenv("FASTAPI_URL", "http://rag-core:8000")

# logger.info(f"Conectando a FastAPI en: {API_BASE_URL} | FASTAPI_URL env var: {os.getenv('FASTAPI_URL')}")

# # --- FUNCIONES DE COMUNICACIÓN CON LA API ---

# def call_rag_api(query: str, use_query_rewrite: bool) -> Optional[Dict[str, Any]]:
#     """Llama al endpoint /query_rag de FastAPI."""
#     url = f"{API_BASE_URL}/query_rag"
#     payload = {
#         "user_query": query,
#         "use_query_rewrite": use_query_rewrite  # Nuevo parámetro
#     }
    
#     try:
#         response = requests.post(url, json=payload, timeout=600)
#         response.raise_for_status()  # Lanza excepción para errores 4xx/5xx
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Error al llamar a /query_rag: {e}")
#         st.error(f"❌ Error al conectar o procesar la consulta RAG: {e}")
#         return None

# def call_feedback_api(payload: Dict[str, Any]) -> bool:
#     """Llama al endpoint /submit_feedback de FastAPI."""
#     url = f"{API_BASE_URL}/submit_feedback"
    
#     try:
#         # El payload debe coincidir con el modelo FeedbackInput de FastAPI
#         response = requests.post(url, json=payload, timeout=600)
#         response.raise_for_status() 
#         logger.info(f"[SUCCESS] Feedback guardado exitosamente. ID: {response.json().get('feedback_id')}")
#         return True
#     except requests.exceptions.RequestException as e:
#         logger.error(f"[ERROR] Error al guardar feedback vía API: {e}")
#         st.error(f"❌ Error al guardar tu evaluación: {e}")
#         return False


# # --- Configuración de la aplicación Streamlit ---
# st.set_page_config(page_title="RAG System", page_icon="🤖", layout="wide")
# st.title("🤖 Sistema de Generación Aumentada por Recuperación (RAG)")
# st.subheader("Consulta tu base de conocimiento técnico")

# # --- Inicialización de estado de sesión ---
# # Solo se mantienen los estados relacionados con la UI y los datos de la última respuesta.
# session_keys_defaults = {
#     'last_query': "",
#     'last_response': "",
#     'last_retrieval_context': [], # Almacenará la lista de RAGChunkMetadata como diccionarios
#     'feedback_rating': None,
#     'feedback_sent': False,    
#     'show_success_message': False    
# }

# for key, default_value in session_keys_defaults.items():
#     if key not in st.session_state:
#         st.session_state[key] = default_value

# # --- Sidebar ---
# with st.sidebar:
#     st.header("⚙️ Configuración del RAG (Simulada)")
#     # Estas opciones ahora son solo indicativas o deberían enviarse a FastAPI
#     # En este ejemplo, las dejamos solo como UI para simplificar.
#     use_query_rewrite = st.checkbox("Usar Reescritura de Consulta", value=False, disabled=False) # Habilitado
#     use_rerank = st.checkbox("Usar Reclasificación de Documentos", value=True, disabled=True)
#     temperature = st.slider("Temperatura del LLM", min_value=0.0, max_value=1.0, value=0.0, step=0.1, disabled=True)
    
#     show_retrieved_retrieval_context = st.checkbox("Mostrar retrieval_context Recuperados", value=True)
#     show_chunk_scores = st.checkbox("Mostrar Scores de retrieval_context", value=True)
    
#     st.divider()
#     st.info(f"Conectado a FastAPI en: **{API_BASE_URL}**")

# # --- Cuerpo principal ---
# query = st.text_input("Ingresa tu pregunta:", placeholder="Ej: What are the advantages of using RAG?", key="query_input")

# if st.button("Obtener Respuesta", key="get_answer_btn") and query:
#     # 1. Resetear estado de feedback y mensaje de éxito
#     st.session_state.feedback_sent = False
#     st.session_state.show_success_message = False

#     st.subheader("🔍 Procesamiento de la Consulta (Vía API)")
#     progress_bar = st.progress(0, text="Llamando a FastAPI...")

#     try:
#         # 2. Llamada a la API RAG - Se pasa el estado del checkbox
#         rag_response_data = call_rag_api(query, use_query_rewrite)
        
#         if rag_response_data:
#             # 3. Guardar respuesta y retrieval_context en el estado desde la respuesta JSON (RAGOutput)
#             st.session_state.last_query = rag_response_data.get("query_used", query)
#             st.session_state.last_response = rag_response_data.get("actual_output", "Error: Respuesta LLM no encontrada.")
#             st.session_state.last_retrieval_context = rag_response_data.get("retrieval_context_used", [])
            
#             progress_bar.progress(100, text="¡Listo! Respuesta recibida de FastAPI.")

#             # 4. Mostrar resultados inmediatamente después de la consulta
#             st.subheader("💬 Respuesta del LLM")
#             st.write(st.session_state.last_response)
#             st.caption(f"Modelo utilizado: {rag_response_data.get('llm_model', 'N/A')}")

#             if show_retrieved_retrieval_context:
#                 st.subheader("📚 retrieval_context Recuperados (Fuentes)")
#                 retrieval_context_retrieved = st.session_state.last_retrieval_context # Lista de RAGChunkMetadata
                
#                 if not retrieval_context_retrieved:
#                     st.info("No se encontraron retrieval_context relevantes.")
#                 else:
#                     for i, chunk in enumerate(retrieval_context_retrieved):
#                         # Visualización con los campos de RAGChunkMetadata
#                         score_str = f"Relevance Score: {chunk.get('relevance_score', 'N/A'):.3f}"
#                         score_ini = f"Initial Score: {chunk.get('original_score', 'N/A'):.3f}"
                        
#                         with st.expander(f"Chunk {i+1} ({score_str} | {score_ini}) - Fuente: {chunk.get('source_document', 'Desconocida')}"):
#                             st.write(f"**ID del Chunk:** {chunk.get('chunk_id', 'N/A')}")
#                             st.write(f"**Documento Fuente:** {chunk.get('source_document', 'N/A')}")
#                             st.write(f"**Vista Previa:** {chunk.get('text_preview', 'N/A')}")

#         else:
#             progress_bar.empty()
#             st.error("No se pudo obtener la respuesta de la API.")

#     except Exception as e:
#         logger.error(f"Ocurrió un error general durante la llamada: {e}")
#         st.error(f"❌ Ocurrió un error inesperado: {e}")
#     finally:
#         progress_bar.empty()

# # --- Sección de Feedback ---
# # Se muestra solo si hay una respuesta y el feedback no ha sido enviado.
# if (st.session_state.last_query and st.session_state.last_response and
#     st.session_state.last_retrieval_context and not st.session_state.feedback_sent):

#     # Mensaje de éxito si se acaba de enviar (usamos st.session_state.show_success_message)
#     if st.session_state.get('show_success_message', False):
#         st.success("✅ ¡Evaluación enviada exitosamente!")
        
#     # Formulario para el feedback
#     with st.form(key="feedback_form"):
#         st.subheader("📊 Evalúa la respuesta")
        
#         # Campo para el comentario (agregado)
#         feedback_comment = st.text_area("Comentarios (Opcional):", key="feedback_comment_widget")
        
#         st.session_state.feedback_rating = st.radio(
#             "¿Qué tan útil fue esta respuesta? (1 = Muy pobre, 5 = Excelente)",
#             options=[1, 2, 3, 4, 5],
#             format_func=lambda x: '⭐' * x,
#             index=2, # Valor por defecto (3 estrellas)
#             key="feedback_rating_widget"
#         )

#         submitted = st.form_submit_button("Enviar Evaluación")
        
#         if submitted:
#             if st.session_state.feedback_rating is not None:
#                 # 1. Extraer solo los IDs de los retrieval_context (como espera el modelo FeedbackInput)
#                 chunk_ids_list = [chunk.get("chunk_id", "unknown") for chunk in st.session_state.last_retrieval_context]
                
#                 # 2. Construir el payload EXACTAMENTE como lo espera FeedbackInput de FastAPI
#                 feedback_payload = {
#                     "query": st.session_state.last_query,
#                     "actual_output": st.session_state.last_response,
#                     "chunk_ids": chunk_ids_list,
#                     "evaluation": st.session_state.feedback_rating,
#                     "comment": feedback_comment if feedback_comment else None # Enviar None si está vacío
#                 }
                
#                 # 3. Llamar al endpoint de feedback
#                 success = call_feedback_api(feedback_payload)
                
#                 if success:
#                     # Marcar como enviado y actualizar estado
#                     st.session_state.feedback_sent = True
#                     st.session_state.show_success_message = True
#                     # Rerun para que se oculte el formulario y se muestre el mensaje de éxito
#                     st.rerun() 
#                 # Si no es exitoso, call_feedback_api ya mostró el error.
#             else:
#                 st.warning("Por favor, selecciona una calificación antes de enviar.")

#  # --- Sección de Gráficos de Feedback General ---
# st.divider()
# st.subheader("📊 Feedback General de Usuarios")

# # Botón para cargar y mostrar gráfico de feedback
# if st.button("Actualizar Gráficos de Feedback"):
#     # Esta lógica se ejecuta solo cuando se pulsa el botón
#     try:
#         url = f"{API_BASE_URL}/get_feedback_ratings"
#         st.info(f"Llamando a: {url}")
#         response = requests.get(url, timeout=600)
#         response.raise_for_status()

#         data = response.json()
#         ratings_data = data.get('ratings', [])

#         if not ratings_data:
#             st.warning("No se encontraron datos de ratings de feedback.")
#         else:
#             # Crear el DataFrame
#             df_feedback = pd.DataFrame(ratings_data)

#             # Gráfico de torta
#             import plotly.graph_objects as go
#             if not df_feedback.empty:
#                 labels = []
#                 rating = df_feedback['rating'].tolist()
#                 for r in rating:
#                     if r == 1:
#                         labels.append('Muy Mala')
#                     if r == 2:
#                         labels.append('Mala')
#                     if r == 3:
#                         labels.append('Mejorable')
#                     if r == 4:
#                         labels.append('Buena')
#                     if r == 5:
#                         labels.append('Muy Buena')    

#                 values = df_feedback['count'].tolist()

#                 fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, textinfo='label+percent',
#                             insidetextorientation='radial'
#                         )])


#                 st.plotly_chart(fig_pie, use_container_width=True)
#             else:
#                 st.warning("No se pudieron crear los datos para el gráfico de feedback (df_feedback está vacío).")

#     except requests.exceptions.RequestException as e:
#         logger.error(f"Error al llamar a /get_feedback_ratings: {e}")
#         st.error(f"❌ Error al obtener los datos de feedback: {e}")
#     except Exception as e:
#         logger.error(f"Error inesperado al procesar los datos de feedback: {e}")
#         st.error(f"❌ Error inesperado al procesar los datos de feedback: {e}")

# # --- Sección de Gráficos de Evaluación ---
# st.divider()
# st.subheader("📈 Evaluación del RAG")

# # Inicializar estado para mostrar/ocultar la sección de gráficos
# if 'show_evaluation_charts' not in st.session_state:
#     st.session_state.show_evaluation_charts = False

# # Inicializar estado para almacenar los datos de evaluación cargados
# if 'evaluation_data' not in st.session_state:
#     st.session_state.evaluation_data = pd.DataFrame()

# # Botón para mostrar/ocultar gráficos
# if st.button("Mostrar/Ocultar Gráficos de Evaluación"):
#     st.session_state.show_evaluation_charts = not st.session_state.show_evaluation_charts

# if st.session_state.show_evaluation_charts:
#     st.info("Cargando gráficos de evaluación desde la API...")

#     # --- Parámetros de Filtrado ---
#     col1, col2 = st.columns(2)
#     with col1:
#         run_id_filter = st.text_input("Filtrar por Run ID (opcional):", "")
#     with col2:
#         use_date_filter = st.checkbox("Filtrar por rango de fechas")
#         start_date_filter = None
#         end_date_filter = None
#         if use_date_filter:
#             start_date_filter = st.date_input("Fecha Desde", value=None)
#             end_date_filter = st.date_input("Fecha Hasta", value=None)

#     # Botón para cargar datos y graficar
#     if st.button("Actualizar Gráficos"):
#         # Reiniciar datos previos al cargar nuevos
#         st.session_state.evaluation_data = pd.DataFrame()
#         params = {}
#         if run_id_filter:
#             params['run_id'] = run_id_filter
#         if start_date_filter:
#             params['start_date'] = start_date_filter.isoformat()
#         if end_date_filter:
#             params['end_date'] = end_date_filter.isoformat()

#         try:
#             url = f"{API_BASE_URL}/get_evaluation_results"
#             response = requests.get(url, params=params, timeout=600)
#             response.raise_for_status()
#             data = response.json()
#             results = data.get('results', [])

#             if not results:
#                 st.warning("No se encontraron datos de evaluación con los filtros aplicados.")
#             else:
#                 # import pandas as pd
#                 df = pd.DataFrame(results)
#                 df['run_timestamp'] = pd.to_datetime(df['run_timestamp'])

#                 # Guardar los datos cargados en el estado de sesión
#                 st.session_state.evaluation_data = df

#                 st.success(f"✅ Datos cargados. {len(df)} resultados disponibles.")

#         except requests.exceptions.RequestException as e:
#             logger.error(f"Error al llamar a /get_evaluation_results: {e}")
#             st.error(f"❌ Error al obtener los resultados de evaluación: {e}")
#         except Exception as e:
#             logger.error(f"Error inesperado al procesar los resultados de evaluación: {e}")
#             st.error(f"❌ Error inesperado al procesar los resultados: {e}")

#     # --- Mostrar Gráficos si hay datos en el estado ---
#     df = st.session_state.evaluation_data

#     if not df.empty:

#         # <<<<<<<<<<<<<<<<<< Graficos >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

#         # Gráfico 1: Comportamiento de Metrica  Caja y Bigone
#         st.subheader("Comportamiento de cada métrica")
#         fig1 = px.box(df, x='metric_name', y='metric_value', 
#               title='Distribución de Puntuaciones por Métrica',
#               color='metric_name')
#         fig1.update_layout(xaxis_title='Métrica', yaxis_title='Puntuación')
        
#         st.plotly_chart(fig1, use_container_width=True)

#         # Gráfico 2: Puntuaciones por Consulta y Métrica
#         st.subheader("Puntuaciones por Consulta y Métrica")
#         # Scatter plot interactivo
#         fig2 = px.scatter(df, x='query_text', y='metric_value', 
#                         color='metric_name', size='metric_value',
#                         title='Puntuaciones por Consulta y Métrica',
#                         hover_data=['model_name', 'run_timestamp'])
#         fig2.update_layout(
#             xaxis_title='Consulta',
#             yaxis_title='Puntuación',
#             xaxis={'tickangle': 45, 'showticklabels': False},  # Ocultar labels por longitud
#             height=600)
#         st.plotly_chart(fig2, use_container_width=True)

#         # Gráfico 3: métricas por consulta
#         st.subheader("métricas por consulta")
#         # Calcular promedios por métrica
#         metric_means = df.groupby('metric_name')['metric_value'].mean().reset_index()

#         fig3c = go.Figure()

#         fig3c.add_trace(go.Scatterpolar(
#             r=metric_means['metric_value'],
#             theta=metric_means['metric_name'],
#             fill='toself',
#             name='Promedio Métricas'
#         ))

#         fig3c.update_layout(
#             polar=dict(
#                 radialaxis=dict(
#                     visible=True,
#                     range=[0, 1]
#                 )),
#             showlegend=True,
#             title='Radar Chart - Promedio de Métricas'
#         )
#         st.plotly_chart(fig3c, use_container_width=True)

#         # Gráfico 4: Métricas por Query (Radar) - AHORA CON DATOS DEL ESTADO
#         st.subheader("Perfil de Métricas por Query (Selecciona una ejecución y una query)")
#         # Filtrar por run_id para el radar
#         available_runs = df['run_id'].unique()
#         # Usar st.selectbox sin key fija para que no cause conflicto con el estado general
#         # Pero usar el valor previamente seleccionado si existe en el estado
#         if 'selected_run_radar' not in st.session_state:
#             st.session_state.selected_run_radar = available_runs[0] if len(available_runs) > 0 else None

#         selected_run_radar = st.selectbox(
#             "Selecciona un Run ID para el gráfico de radar",
#             options=available_runs,
#             index=list(available_runs).index(st.session_state.selected_run_radar) if st.session_state.selected_run_radar in available_runs else 0,
#             key="radar_run_temp" # Clave temporal para evitar conflicto con el estado
#         )
#         # Actualizar el estado solo si cambia el valor
#         if selected_run_radar != st.session_state.selected_run_radar:
#             st.session_state.selected_run_radar = selected_run_radar
#             # Reiniciar la query seleccionada si cambia el run_id
#             st.session_state.selected_query_radar = None

#         df_radar = df[df['run_id'] == st.session_state.selected_run_radar]

#         if not df_radar.empty:
#             available_queries = df_radar['query_text'].unique()
#             # Usar st.selectbox para la query
#             if 'selected_query_radar' not in st.session_state or st.session_state.selected_query_radar not in available_queries:
#                  st.session_state.selected_query_radar = available_queries[0] if len(available_queries) > 0 else None

#             selected_query_radar = st.selectbox(
#                 "Selecciona una Query",
#                 options=available_queries,
#                 index=list(available_queries).index(st.session_state.selected_query_radar) if st.session_state.selected_query_radar in available_queries else 0,
#                 key="radar_query_temp" # Clave temporal
#             )
#             # Actualizar el estado solo si cambia el valor
#             if selected_query_radar != st.session_state.selected_query_radar:
#                 st.session_state.selected_query_radar = selected_query_radar

#             df_final_radar = df_radar[df_radar['query_text'] == st.session_state.selected_query_radar]

#             if not df_final_radar.empty:
#                 fig3 = px.line_polar(df_final_radar, r='metric_value', theta='metric_name',
#                                      line_close=True,
#                                      title=f'Perfil de Métricas para Run: {st.session_state.selected_run_radar} | Query: {st.session_state.selected_query_radar[:50]}...')
#                 st.plotly_chart(fig3, use_container_width=True)
#             else:
#                 st.warning("No hay datos para el Run ID y Query seleccionados.")
#         else:
#             st.warning("No hay datos para el Run ID seleccionado.")

#         # Gráfico 4: Histograma simple de todas las métricas
#         df_clean = df[df['metric_value'] <= 1.0]
#         # Crear categorías
#         df_clean['score_category'] = pd.cut(df_clean['metric_value'], 
#                                    bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
#                                    labels=['0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0'])
#         fig11 = px.histogram(df_clean, x='score_category',
#                    title='Distribución por Categorías de Puntuación')
        
#         st.plotly_chart(fig11, use_container_width=True)

#         # Gráfico 5: Métricas por valor (barras agrupadas por métrica)
#         st.subheader("Métricas por Valor (Agrupadas por Métrica)")
#         fig1 = px.bar(df, x='metric_name', y='metric_value',
#                      title='Valor de Métricas',
#                      color='run_id', # Diferenciar ejecuciones
#                      hover_data=['query_text', 'evaluation_suite', 'model_name', 'run_timestamp'])
#         st.plotly_chart(fig1, use_container_width=True)

#         # Gráfico 6: Evolución de Métricas por Run (Líneas)
#         st.subheader("Evolución de Métricas por Run (Timestamp)")
#         df_grouped = df.groupby(['run_timestamp', 'metric_name'])['metric_value'].mean().reset_index()
#         fig2 = px.line(df_grouped, x='run_timestamp', y='metric_value', color='metric_name',
#                        title='Evolución de Métricas a lo largo del tiempo (Promedio por ejecución)',
#                        markers=True)
#         st.plotly_chart(fig2, use_container_width=True)

# st.divider()
# st.caption("Sistema RAG desarrollado con Python, FastAPI, y Streamlit.")
# st.caption("Autor: Carlos Villreal - 2025")