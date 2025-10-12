import logging
import os
import hashlib
import time
import random
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field, conint
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from starlette.responses import JSONResponse

# --- 1. Importaciones de Lógica de Negocio ---
try:
    from rag_pdf_processor.utils.process_pdfs import (
        scan_folders, 
        calculate_hash_md5, 
        document_already_processed,
        process_single_document  
    )
    from rag_pdf_processor.utils.postgres_query import execute_query
    from rag_pdf_processor.retrieval.vector_retriever import VectorRetriever
    from rag_pdf_processor.retrieval.llm_interface import LLMInterface
    from rag_pdf_processor.retrieval.query_rewriter import QueryRewriter
    RAG_LOGIC_AVAILABLE = True
except ImportError as e:
    logging.error(f"❌ Error importando rag_pdf_processor en FastAPI: {e}")
    RAG_LOGIC_AVAILABLE = False

# --- 2. Configuración y Rutas Base ---
# Definición de la ruta base del proyecto RAG-Core (IMPORTANTE para rutas absolutas)
BASE_DIR = Path(__file__).resolve().parent

# Carpetas de datos dentro del contenedor RAG-Core
RAW_FOLDER = BASE_DIR / "data" / "raw"
PROCESSED_FOLDER = BASE_DIR / "data" / "processed"

# Asegurar que las carpetas existan
RAW_FOLDER.mkdir(parents=True, exist_ok=True)
PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Inicializar componentes RAG (Vector Store, LLM, Query Rewriter)

logger.info("🔄 Inicializando componentes RAG...")
try:
    vector_store = VectorRetriever(collection_name="chunks-hybrid")
    print("✅ Vector Store (Qdrant) inicializado.")
except Exception as e:
    print(f"Error inicializando Vector Store: {e}")
    raise

try:
    llm_interface = LLMInterface()
    print("✅ LLM Interface inicializado.")
except Exception as e:
    print(f"Error inicializando LLM Interface: {e}")
    raise

try:
    query_rewriter = QueryRewriter(llm_interface)
    print("✅ Query Rewriter inicializado.")
except Exception as e:
    print(f"Error inicializando Query Rewriter: {e}")
    raise



# --- 3. CONFIGURACIÓN E INICIALIZACIÓN DE FASTAPI ---
app = FastAPI(
    title="Document Processor Backend API",
    description="Endpoints para el flujo de procesamiento de documentos (Ingesta) y la consulta en tiempo real (RAG) y Feedback.",
    version="1.0.0"
)

# --- 4. MODELOS DE DATOS (PYDANTIC) ---

# Modelos de Ingesta
class DocumentPaths(BaseModel):
    monitored_folders: Optional[List[str]] = Field(default=None)
    paths: List[str] = Field(default_factory=list)

class HashInput(BaseModel):
    document_paths: List[str] = Field(...)

class HashOutput(BaseModel):
    hashes: Dict[str, Optional[str]] = Field(...)

class UnprocessedDocument(BaseModel):
    file_path: str = Field(...)
    hash_value: str = Field(...)

class CheckProcessedInput(BaseModel):
    hashes: Dict[str, Optional[str]] = Field(...)

class CheckProcessedOutput(BaseModel):
    unprocessed_documents: List[UnprocessedDocument] = Field(default_factory=list)

class ProcessDocumentInput(BaseModel):
    path_file: str = Field(...)
    path_file_clean: str = Field(...)
    hash_file: str = Field(...)

class ProcessingResult(BaseModel):
    success: bool = Field(...)
    message: str = Field(...)

class UserQueryInput(BaseModel):
    """Input para el endpoint de consulta RAG."""
    user_query: str = Field(..., description="La pregunta enviada por el usuario.")

class RAGChunkMetadata(BaseModel):
    """Metadatos de un chunk extraído para la respuesta."""
    chunk_id: str = Field(..., description="ID del chunk en Qdrant/DB.")
    content: str = Field(..., description="contenido relevante del chunk.")
    source_document: str = Field(..., description="Nombre del documento fuente.")
    relevance_score: Optional[float] = Field(..., description="Puntuación de relevancia (e.g., de la búsqueda o re-ranker).")
    original_score: Optional[float] = Field(None, description="Puntuación original antes del re-rank.")
    text_preview: str = Field(..., description="Un fragmento del texto del chunk.")

class RAGOutput(BaseModel):
    """Output del pipeline RAG que contiene la respuesta y todos los metadatos de apoyo."""
    query_used: str = Field(..., description="La pregunta del usuario procesada.")
    llm_response: str = Field(..., description="Respuesta final generada por el LLM.")
    chunks_used: List[RAGChunkMetadata] = Field(..., description="Lista de chunks que sirvieron de contexto.")
    llm_model: str = Field(..., description="Nombre del modelo LLM usado (e.g., gemini-2.5-flash).")

class FeedbackInput(BaseModel):
    query: str = Field(...)
    LLM_response: str = Field(...)
    chunk_ids: List[str] = Field(...)
    evaluation: conint(ge=1, le=5) = Field(..., description="Evaluación del 1 al 5.")
    comment: Optional[str] = Field(None)

class FeedbackResult(BaseModel):
    status: str = "Success"
    feedback_id: str = Field(...)

# --- 5. FUNCIONES AUXILIARES ---
def get_db_config():
    """Obtiene la configuración de la base de datos para el usuario de aplicación."""
    return {
        'dbname': os.getenv('APP_DB_NAME'),
        'user': os.getenv('APP_DB_USER'),
        'password': os.getenv('APP_DB_PASSWORD'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432')
    }

def save_feedback_to_db(query, llm_response, chunk_ids, rating):

    """Guarda el feedback del usuario en la base de datos."""

    feedback_id = hashlib.sha256(f"{query}{time.time()}".encode()).hexdigest()[:12]

    query = """
        INSERT INTO feedback (feedback_id, query, llm_response, chunk_ids, evaluation)
        VALUES (%s, %s, %s, %s, %s)
        """

    params = (feedback_id, query, llm_response, chunk_ids, rating)

    insert_query = """
        INSERT INTO user_feedback (feedback_id, query, llm_response, chunk_ids, evaluation)
        VALUES (%s, %s, %s, %s, %s)
    """

    result = execute_query(user = 'appuser', query=query, fetch=False, params=params)

    if result:  # .get("status") == "success":
        return feedback_id
    else:
        raise Exception("Failed to save feedback to the database.")
    
def execute_rag_pipeline(user_query: str) -> RAGOutput:
    """
    Pipeline RAG: Embed, Search, Rerank, LLM.
    Devuelve la respuesta del LLM y los metadatos de los chunks.
    """
    print(f"\n--- EJECUTANDO RAG PARA: '{user_query}' ---")

    # # Inicializar componentes del RAG
    # try:
    #     vector_store = VectorRetriever(collection_name="chunks-hybrid")
    #     print("✅ Vector Store (Qdrant) inicializado.")
    # except Exception as e:
    #     print(f"Error inicializando Vector Store: {e}")
    #     raise

    # try:
    #     llm_interface = LLMInterface()
    #     print("✅ LLM Interface inicializado.")
    # except Exception as e:
    #     print(f"Error inicializando LLM Interface: {e}")
    #     raise

    # try:
    #     query_rewriter = QueryRewriter(llm_interface)
    #     print("✅ Query Rewriter inicializado.")
    # except Exception as e:
    #     print(f"Error inicializando Query Rewriter: {e}")
    #     raise

    chunks_retrieved = vector_store.hybrid_search_with_rerank(  
                        user_query, 
                        limit=5, 
                        use_rerank=True  # use_rerank
            )
 
    context_chunks_for_llm = [
            {
                "chunk_id": chunk["id"],
                "content": chunk["content"],
                "source_document": f'book: {chunk["book_name"]} - chapter: {chunk["chapter"]}',
                "relevance_score": chunk["score"],  # get("score", 0.0),
                "original_score": chunk["original_score"],  # .get("original_score", 0.0),
                "text_preview": chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else ""),
                }
            for chunk in chunks_retrieved
        ]
    

    response = llm_interface.generate_response(
            query=user_query,
            context_chunks=context_chunks_for_llm,
            max_tokens=500,
            temperature= 0  # temperature
        )
    

    
    print("--- RAG COMPLETADO ---")

    print(f"Respuesta LLM ({len(response)} chars): {response[:300]}{'...' if len(response) > 300 else ''}\n")
    
    return RAGOutput(
        query_used=user_query,
        llm_response=response,
        chunks_used=context_chunks_for_llm,
        llm_model="deepseek-chat"
    )

# --- 7. DEFINICIÓN DE ENDPOINTS DE LA API ---

# Endpoint 1 a 4: Ingesta (Mantenidos)

# @app.get("/scan_folders", response_model=DocumentPaths)
# async def scan_folders_endpoint(monitored_folders: Optional[str] = None):
#     folder_list = monitored_folders.split(',') if monitored_folders else None
#     paths = scan_folders(folder_list)
#     return DocumentPaths(monitored_folders=folder_list, paths=paths)

# @app.post("/calculate_hashes", response_model=HashOutput)
# async def calculate_hashes_endpoint(input_data: HashInput):
#     hashes = calculate_hash_md5(input_data.document_paths)
#     return HashOutput(hashes=hashes)

# @app.post("/check_processed", response_model=CheckProcessedOutput)
# async def check_processed_endpoint(input_data: CheckProcessedInput):
#     unprocessed_tuples = document_already_processed(input_data.hashes)
#     unprocessed_list = [
#         UnprocessedDocument(file_path=path, hash_value=hash_val) 
#         for path, hash_val in unprocessed_tuples
#     ]
#     return CheckProcessedOutput(unprocessed_documents=unprocessed_list)


# --- ENDPOINT 1: CONSULTA RAG ---

@app.post("/query_rag", response_model=RAGOutput)
async def query_rag_endpoint(input_data: UserQueryInput):
    """
    **Endpoint: Consulta RAG en Tiempo Real**
    Ejecuta el pipeline completo de búsqueda, re-ranking, y generación LLM.
    """
    try:
        # Aquí se llama a la función que conecta a tus modelos/Qdrant
        rag_response = execute_rag_pipeline(input_data.user_query)
        return rag_response
    except Exception as e:
        print(f"ERROR RAG: Fallo al ejecutar el pipeline: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Fallo interno al procesar la consulta RAG."
        )

# --- ENDPOINT 2: ALMACENAMIENTO DE FEEDBACK ---

@app.post("/submit_feedback", response_model=FeedbackResult)
async def submit_feedback_endpoint(feedback_data: FeedbackInput):
    """
    **Endpoint 6: Almacenamiento de Feedback**
    Guarda la evaluación del usuario en PostgreSQL.
    """
    try:
        feedback_id = save_feedback_to_db(feedback_data)
        return FeedbackResult(feedback_id=feedback_id)
    except Exception as e:
        print(f"ERROR: Fallo al guardar el feedback: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Fallo interno del servidor al intentar guardar el feedback."
        )
    
# --- ENDPOINT 3: Unificado de Metadata (Llamado por Airflow) ---

@app.get("/ingest_metadata_only", 
         response_model=Dict[str, Any], 
         summary="Escanea, hashea y chequea documentos pendientes.")
def ingest_metadata_only():
    """
    Combina scan_folders, calculate_hash_md5 y document_already_processed.
    Devuelve la lista de documentos que Airflow necesita enviar para su procesamiento.
    """
    if not RAG_LOGIC_AVAILABLE:
        raise HTTPException(status_code=503, detail="Lógica RAG de negocio no disponible.")

    try:
        # 1. Escanear carpetas (asume que busca en /data/raw)
        files = scan_folders()
        
        # 2. Calcular hashes: lista de (ruta_absoluta, hash)
        hashes = calculate_hash_md5(files)
        
        # 3. Chequear estado en la BBDD (PostgreSQL)
        pending_files = document_already_processed(hashes)
        
        return {
            "status": "success",
            "message": f"Encontrados {len(files)} archivos, {len(pending_files)} pendientes.",
            "pending_files": pending_files
        }
    except Exception as e:
        logging.error(f"Error en ingest_metadata_only: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al procesar metadata: {str(e)}")


# --- ENDPOINT 3: Procesamiento Pesado (Llamado por Airflow) ---

@app.post("/process_document", response_model=ProcessingResult)
async def process_document_endpoint(input_data: ProcessDocumentInput):
    print(f"\n--- INICIANDO PROCESAMIENTO PARA: '{input_data.path_file}'\n'{input_data.path_file_clean}\n{input_data.hash_file} ---")
    
    success = process_single_document(
        input_data.path_file,
        input_data.path_file_clean,
        input_data.hash_file
    )
    if success:
        return ProcessingResult(success=True, message="Documento procesado con éxito.")
    else:
        raise HTTPException(status_code=500, detail="Fallo en el procesamiento del documento.")

# --- ENDPOINT 4: Endpoint de prueba de conexión ---
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "RAG Core API"}




