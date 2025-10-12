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

print(f"Conectando a FastAPI en: {API_BASE_URL} | FASTAPI_URL env var: {os.getenv('FASTAPI_URL')}")

# --- FUNCIONES DE COMUNICACIÓN CON LA API ---

def call_rag_api(query: str) -> Optional[Dict[str, Any]]:
    """Llama al endpoint /query_rag de FastAPI."""
    url = f"{API_BASE_URL}/query_rag"
    payload = {"user_query": query}
    
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
    'last_chunks': [], # Almacenará la lista de RAGChunkMetadata como diccionarios
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
    use_query_rewrite = st.checkbox("Usar Reescritura de Consulta", value=False, disabled=True)
    use_rerank = st.checkbox("Usar Reclasificación de Documentos", value=True, disabled=True)
    temperature = st.slider("Temperatura del LLM", min_value=0.0, max_value=1.0, value=0.0, step=0.1, disabled=True)
    
    show_retrieved_chunks = st.checkbox("Mostrar Chunks Recuperados", value=True)
    show_chunk_scores = st.checkbox("Mostrar Scores de Chunks", value=True)
    
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
        # 2. Llamada a la API RAG
        rag_response_data = call_rag_api(query)
        
        if rag_response_data:
            # 3. Guardar respuesta y chunks en el estado desde la respuesta JSON (RAGOutput)
            st.session_state.last_query = rag_response_data.get("query_used", query)
            st.session_state.last_response = rag_response_data.get("llm_response", "Error: Respuesta LLM no encontrada.")
            st.session_state.last_chunks = rag_response_data.get("chunks_used", [])
            
            progress_bar.progress(100, text="¡Listo! Respuesta recibida de FastAPI.")

            # 4. Mostrar resultados inmediatamente después de la consulta
            st.subheader("💬 Respuesta del LLM")
            st.write(st.session_state.last_response)
            st.caption(f"Modelo utilizado: {rag_response_data.get('llm_model', 'N/A')}")

            if show_retrieved_chunks:
                st.subheader("📚 Chunks Recuperados (Fuentes)")
                chunks_retrieved = st.session_state.last_chunks # Lista de RAGChunkMetadata
                
                if not chunks_retrieved:
                    st.info("No se encontraron chunks relevantes.")
                else:
                    for i, chunk in enumerate(chunks_retrieved):
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
    st.session_state.last_chunks and not st.session_state.feedback_sent):

    # Mensaje de éxito si se acaba de enviar (usamos st.session_state.show_success_message)
    if st.session_state.get('show_success_message', False):
        st.success("✅ ¡Evaluación enviada exitosamente!")
        # Esto evitará que el formulario se muestre inmediatamente, ya que feedback_sent sigue siendo False
        # hasta el próximo rerun. Lo haremos temporalmente para que se muestre el mensaje.
        
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

        submitted = st.form_submit_button("Enviar Evaluación", key="submit_feedback_btn")
        
        if submitted:
            if st.session_state.feedback_rating is not None:
                # 1. Extraer solo los IDs de los chunks (como espera el modelo FeedbackInput)
                chunk_ids_list = [chunk.get("chunk_id", "unknown") for chunk in st.session_state.last_chunks]
                
                # 2. Construir el payload EXACTAMENTE como lo espera FeedbackInput de FastAPI
                feedback_payload = {
                    "query": st.session_state.last_query,
                    "LLM_response": st.session_state.last_response,
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


st.divider()
st.caption("Sistema RAG desarrollado con Python, FastAPI, y Streamlit.")
st.caption("Autor: Carlos Villarreal - 2025")