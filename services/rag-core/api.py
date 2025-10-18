import logging
import os
import hashlib
import time
from datetime import datetime
import random
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field, conint
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from starlette.responses import JSONResponse

# --- 1. Importaciones de Lógica de Negocio ---
from rag_pdf_processor.evaluations.run_tests import run_deepeval_tests
from rag_pdf_processor.evaluations.run_test_scores import run_deepeval_test_scores
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
    logger.info("✅ Vector Store (Qdrant) inicializado.")
except Exception as e:
    logger.error(f"Error inicializando Vector Store: {e}")
    raise

try:
    llm_interface = LLMInterface()
    logger.info("✅ LLM Interface inicializado.")
except Exception as e:
    logger.error(f"Error inicializando LLM Interface: {e}")
    raise

try:
    query_rewriter = QueryRewriter(llm_interface)
    logger.info("✅ Query Rewriter inicializado.")
except Exception as e:
    logger.error(f"Error inicializando Query Rewriter: {e}")
    raise

# --- 3. CONFIGURACIÓN E INICIALIZACIÓN DE FASTAPI ---
app = FastAPI(
    title="Document Processor Backend API",
    description="Endpoints para el flujo de procesamiento de documentos (Ingesta) y la consulta en tiempo real (RAG) y Feedback.",
    version="1.0.0"
)

# --- 4. MODELOS DE DATOS (PYDANTIC) ---

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
    use_query_rewrite: bool = Field(default=False, description="Si se debe usar la expansión de consulta.")

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
    actual_output: str = Field(..., description="Respuesta final generada por el LLM.")
    retrieval_context_used: List[RAGChunkMetadata] = Field(..., description="Lista de retrieval_context que sirvieron de contexto.")
    llm_model: str = Field(..., description="Nombre del modelo LLM usado (e.g., gemini-2.5-flash).")

class FeedbackInput(BaseModel):
    query: str = Field(...)
    actual_output: str = Field(...)
    chunk_ids: List[str] = Field(...)
    evaluation: conint(ge=1, le=5) = Field(..., description="Evaluación del 1 al 5.")
    comment: Optional[str] = Field(None)

class FeedbackResult(BaseModel):
    status: str = "Success"
    feedback_id: str = Field(...)

### ------------------------------------------------------------------- ###
class FeedbackItem(BaseModel):
    feedback_id: str
    query: str
    actual_output: str
    chunk_ids: str  # Cadena separada por comas
    rating: int
    timestamp: str # o datetime si lo manejas así

class GetFeedbackResponse(BaseModel):
    feedback_data: List[FeedbackItem]

class GetAnnotationsRequest(BaseModel):
    feedback_ids: List[str]

class GetAnnotationsResponse(BaseModel):
    annotations: Dict[str, str] # { feedback_id: expected_output, ... }

class RunEvaluationRequest(BaseModel):
    feedback_list: List[FeedbackItem]
    annotations_map: Dict[str, str] # { feedback_id: expected_output, ... }

class RunEvaluationResponse(BaseModel):
    status: str
    message: str

class AnnotationItem(BaseModel):
    feedback_id: str
    expected_output: str

class LoadAnnotationsRequest(BaseModel):
    annotations: List[AnnotationItem]
    annotated_by: str = "Experto"

# Modelo de respuesta del endpoint
class EvaluationMetric(BaseModel):
    run_id: str
    run_timestamp: datetime
    query_text: str
    metric_name: str
    metric_value: float
    evaluation_suite: str
    model_name: str
    feedback_id: Optional[str] = None

class GetEvaluationResultsResponse(BaseModel):
    results: List[EvaluationMetric]

### ------------------------------------------------------------------- ###

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

def save_feedback_to_db(query, actual_output, chunk_ids, rating, comment):

    """Guarda el feedback del usuario en la base de datos."""

    feedback_id = hashlib.sha256(f"{query}{time.time()}".encode()).hexdigest()[:12]

    query_insert = """
        INSERT INTO user_feedback (feedback_id, query, llm_response, chunk_ids, rating, comment)
        VALUES (%s, %s, %s, %s, %s, %s)
        """

    params = (feedback_id, query, actual_output, chunk_ids, rating, comment)

    result = execute_query(user = 'appuser', query=query_insert, fetch=False, params=params)

    if result:  # .get("status") == "success":
        return feedback_id
    else:
        raise Exception("Failed to save feedback to the database.")

def execute_rag_pipeline_rewriter(user_query: str, query_rewriter: QueryRewriter) -> RAGOutput:
    """
    Pipeline RAG: Expand Query, Embed, Search, Rerank, LLM.
    Devuelve la respuesta del LLM y los metadatos de los retrieval_context.
    """
    logger.info(f"\n--- EJECUTANDO RAG PARA: '{user_query}' ---")

    # 1. Expandir la consulta original
    expanded_queries = query_rewriter.expand_query_multiple(user_query, num_queries=3)

    logger.info(f"🔍 Consultas expandidas: {expanded_queries}")

    # 2. Buscar con cada query expandida y combinar resultados
    all_retrieval_context = []
    for query in expanded_queries:
        retrieval_context = vector_store.hybrid_search_with_rerank(
            query,
            limit=5,  # Ajustar si es necesario
            use_rerank=True
        )
        all_retrieval_context.extend(retrieval_context)

    # 3. Eliminar duplicados y ordenar por relevancia (si es necesario)
    unique_retrieval_context_map = {}
    for chunk in all_retrieval_context:
        chunk_id = chunk.get("id")
        if chunk_id and chunk_id not in unique_retrieval_context_map:
            unique_retrieval_context_map[chunk_id] = chunk

    unique_retrieval_context = list(unique_retrieval_context_map.values())
    logger.info(f"total retrieval_context únicos: {len(unique_retrieval_context)}")

    # 4. Ordenar por relevancia por score rerank
    unique_retrieval_context.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)

    # 5. Limitar a 5 retrieval_context finales, se puede ajustar si es necesario
    final_retrieval_context = unique_retrieval_context[:5]

    logger.info(f"📦 retrieval_context combinados y finalizados: {len(final_retrieval_context)}")

    # 6. Crear contexto para LLM
    context_retrieval_context_for_llm = [
            {
                "chunk_id": chunk["id"],
                "content": chunk["content"],
                "source_document": f'book: {chunk["book_name"]} - chapter: {chunk["chapter"]}',
                "relevance_score": chunk["rerank_score"], 
                "original_score": chunk["original_score"],  
                "text_preview": chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else ""),
                }
            for chunk in final_retrieval_context
        ]

    # 7. Generar respuesta con el LLM
    response = llm_interface.generate_response(
        query=user_query,  # Usar la pregunta original para el LLM
        context_retrieval_context=context_retrieval_context_for_llm,
        max_tokens=500,
        temperature=0
    )

    logger.info(f"Respuesta LLM ({len(response)} chars): {response[:150]}{'...' if len(response) > 150 else ''}\n")

    logger.info("--- RAG COMPLETADO ---")

    return RAGOutput(
        query_used=user_query,
        actual_output=response,
        retrieval_context_used=context_retrieval_context_for_llm,
        llm_model="deepseek-chat"
    )
    
def execute_rag_pipeline(user_query: str) -> RAGOutput:
    """
    Pipeline RAG: Embed, Search, Rerank, LLM.
    Devuelve la respuesta del LLM y los metadatos de los retrieval_context.
    """
    logger.info(f"\n--- EJECUTANDO RAG PARA: '{user_query}' ---")


    retrieval_context_retrieved = vector_store.hybrid_search_with_rerank(  
                        user_query, 
                        limit=5, 
                        use_rerank=True  # use_rerank
            )
 
    context_retrieval_context_for_llm = [
            {
                "chunk_id": chunk["id"],
                "content": chunk["content"],
                "source_document": f'book: {chunk["book_name"]} - chapter: {chunk["chapter"]}',
                "relevance_score": chunk["rerank_score"],  # get("score", 0.0),
                "original_score": chunk["original_score"],  # .get("original_score", 0.0),
                "text_preview": chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else ""),
                }
            for chunk in retrieval_context_retrieved
        ]
    

    response = llm_interface.generate_response(
            query=user_query,
            context_retrieval_context=context_retrieval_context_for_llm,
            max_tokens=500,
            temperature= 0  # temperature
        )
    
    logger.info("--- RAG COMPLETADO ---")

    logger.info(f"Respuesta LLM ({len(response)} chars): {response[:300]}{'...' if len(response) > 300 else ''}\n")
    
    return RAGOutput(
        query_used=user_query,
        actual_output=response,
        retrieval_context_used=context_retrieval_context_for_llm,
        llm_model="deepseek-chat"
    )

### ------------------------------------------------------------------- ###
def get_feedback_last_week_from_db() -> List[Dict]:
    """
    Obtiene feedback de la semana pasada con rating 1, 2 o 3.
    """
    # Consulta SQL para obtener feedback de la semana pasada
    # Ajusta la lógica de fechas si es necesario
    from datetime import datetime, timedelta, UTC
    # Suponiendo que la zona horaria es UTC o que timestamp es naive en UTC
    now = datetime.now(UTC)
    start_of_last_week = (now - timedelta(days=now.weekday() + 7)).date() # Lunes de la semana anterior
    end_of_last_week = start_of_last_week + timedelta(days=6) # Domingo de la semana anterior

    query_sql = """
        SELECT feedback_id, query, llm_response, chunk_ids, rating, timestamp
        FROM user_feedback
        WHERE rating IN (1, 2, 3)
        AND timestamp >= %s AND timestamp <= %s
        ORDER BY timestamp DESC;
    """
    params = (start_of_last_week.isoformat(), end_of_last_week.isoformat())
    rows = execute_query(user='appuser', query=query_sql, fetch=True, params=params)

    feedback_list = []
    try:
        for row in rows:
            feedback_list.append({
                "feedback_id": row['feedback_id'],
                "query": row['query'],
                "actual_output": row['llm_response'],
                "chunk_ids": row['chunk_ids'], # Es una cadena separada por comas
                "rating": row['rating'],
                "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None # Convertir datetime a string
            })
        return feedback_list
    except Exception as e:
        logger.error(f"Error inesperado: {e}")

def get_expert_annotations_from_db(feedback_ids: List[str]) -> Dict[str, str]:
    """
    Obtiene las anotaciones de experto para los feedback_ids dados.
    """
    if not feedback_ids:
        return {}
    # Usar placeholders para evitar inyección SQL
    placeholders = ','.join(['%s'] * len(feedback_ids))
    query_sql = f"""
        SELECT feedback_id, expected_output
        FROM expert_annotations
        WHERE feedback_id IN ({placeholders});
    """
    rows = execute_query(user='appuser', query=query_sql, fetch=True, params=feedback_ids)

    annotations_map = {row['feedback_id']: row['expected_output'] for row in rows}
    return annotations_map

def get_chunks_content_from_ids(chunk_ids_str: str, retriever: VectorRetriever) -> List[str]:
    """
    Recibe una cadena de chunk_ids separados por comas,
    y devuelve una lista con el contenido de cada chunk obtenido desde Qdrant.
    """
    chunk_ids = [cid.strip() for cid in chunk_ids_str.split(",") if cid.strip()]
    contents = []

    for cid in chunk_ids:
        chunk = retriever.get_chunk_by_id(cid)
        if chunk:
            contents.append(chunk["content"])  # Solo el campo "content" como solicitaste
        else:
            logger.warning(f"⚠️ Chunk con ID {cid} no encontrado en Qdrant.")
            # Puedes decidir agregar un string vacío o None, o simplemente omitirlo
            # contents.append(None)
    return contents

def run_evaluation_suite_logic(feedback_list: List[Dict], annotations_map: Dict[str, str], vector_store: VectorRetriever):
    """
    Lógica principal para ejecutar la suite de evaluación.
    Obtiene chunks, corre métricas, y guarda resultados en la BBDD.
    """
    from rag_pdf_processor.evaluations.test_deepeval_scores import model as model_1
    from rag_pdf_processor.evaluations.test_geval_scores import model as model_2
    from deepeval.metrics import (
        AnswerRelevancyMetric, FaithfulnessMetric, HallucinationMetric,
        ContextualRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric
    )
    from deepeval.metrics import GEval # Si decides usarlo
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    import uuid

    # Generar un run_id único para esta ejecución
    run_id = str(uuid.uuid4())

    results_to_save = []
    for item in feedback_list:
        query = item['query']
        actual_output = item['actual_output']
        feedback_id = item['feedback_id']
        retrieval_context_raw = get_chunks_content_from_ids(item['chunk_ids'], vector_store)
        expected_output = annotations_map.get(feedback_id)

        # --- Ejecutar Métricas ---
        # Inicializar métricas (usa el modelo que tengas configurado, model_1 o model_2)
        metrics_no_exp = [
            AnswerRelevancyMetric(threshold=0, model=model_1, strict_mode=False),
            FaithfulnessMetric(threshold=0, model=model_1, strict_mode=False),
            HallucinationMetric(threshold=0, model=model_1, strict_mode=False),
            ContextualRelevancyMetric(threshold=0, model=model_1, strict_mode=False)
        ]

        metrics_with_exp = []
        if expected_output:
            metrics_with_exp = [
                ContextualPrecisionMetric(threshold=0, model=model_1, strict_mode=False),
                ContextualRecallMetric(threshold=0, model=model_1, strict_mode=False),
                # Ejemplo de GEval definir las evaluaciones 
                # GEval( ... )
            ]

        # Crear test case
        tc = LLMTestCase(
            input=query,
            actual_output=actual_output,
            expected_output=expected_output if expected_output else None, # Puede ser None
            retrieval_context=retrieval_context_raw if retrieval_context_raw else None # Puede ser None
        )

        # Medir métricas sin expected_output
        scores_no_exp = {}
        for metric in metrics_no_exp:
            try:
                score = metric.measure(tc)
                scores_no_exp[metric.__class__.__name__] = score
            except Exception as e:
                logger.error(f"Error al medir métrica {metric.__class__.__name__} para feedback {feedback_id}: {e}")
                scores_no_exp[metric.__class__.__name__] = None # O manejar el error como prefieras

        # Medir métricas con expected_output
        scores_with_exp = {}
        for metric in metrics_with_exp:
            try:
                score = metric.measure(tc)
                scores_with_exp[metric.__class__.__name__] = score
            except Exception as e:
                logger.error(f"Error al medir métrica {metric.__class__.__name__} para feedback {feedback_id}: {e}")
                scores_with_exp[metric.__class__.__name__] = None # O manejar el error como prefieras

        # Combinar resultados
        all_scores = {**scores_no_exp, **scores_with_exp}

        # Crear entradas para la tabla evaluation_results
        for metric_name, metric_value in all_scores.items():
            if metric_value is not None: # Solo guardar si se pudo calcular
                results_to_save.append({
                    "run_id": run_id,
                    "query_text": query,
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "evaluation_suite": "rag_evaluation_weekly",
                    "model_name": os.getenv("EVAL_MODEL_NAME", "unknown"),
                    "feedback_id": feedback_id
                })

    # --- Guardar Resultados ---
    if results_to_save:
        insert_query = """
            INSERT INTO evaluation_results (run_id, run_timestamp, query_text, metric_name, metric_value, evaluation_suite, model_name, feedback_id)
            VALUES (%(run_id)s, DEFAULT, %(query_text)s, %(metric_name)s, %(metric_value)s, %(evaluation_suite)s, %(model_name)s, %(feedback_id)s);
        """
        # execute_query no es ideal para grandes inserciones, considera usar psycopg2 extras.execute_batch o similar si es necesario
        for result in results_to_save:
            execute_query(user='appuser', query=insert_query, fetch=False, params=result)
        logger.info(f"Guardados {len(results_to_save)} resultados de evaluación para run_id {run_id}.")
    else:
        logger.warning(f"No se generaron resultados válidos para el run_id {run_id}.")


    return {
        "status": "success",
        "message": f"Evaluación completada. {len(results_to_save)} resultados guardados.",
        "run_id": run_id
    }

### ------------------------------------------------------------------- ###

# --- ENDPOINT 1: CONSULTA RAG (Llamado por frontend) ---

@app.post("/query_rag", response_model=RAGOutput)
async def query_rag_endpoint(input_data: UserQueryInput):
    """
    **Endpoint: Consulta RAG en Tiempo Real**
    Ejecuta el pipeline completo: expansión, búsqueda, re-ranking, y generación LLM.
    """
    try:
        # Llamar a la función principal con el rewriter
        if input_data.use_query_rewrite:

            logger.info("Usando expansión de consulta.")
            rag_response = execute_rag_pipeline_rewriter(input_data.user_query, query_rewriter)
            return rag_response
        else:
            logger.info("Usando consulta directa.")
            rag_response = execute_rag_pipeline(input_data.user_query)
            return rag_response
    except Exception as e:
        logger.error(f"ERROR RAG: Fallo al ejecutar el pipeline: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno al procesar la consulta RAG."
        )

# --- ENDPOINT 2: ALMACENAMIENTO DE FEEDBACK (Llamado por frontend)---

@app.post("/submit_feedback", response_model=FeedbackResult)
async def submit_feedback_endpoint(feedback_data: FeedbackInput):
    """
    **Endpoint 6: Almacenamiento de Feedback**
    Guarda la evaluación del usuario en PostgreSQL.
    """

    query = feedback_data.query
    actual_output = feedback_data.actual_output
    chunk_ids = ", ".join(map(str, feedback_data.chunk_ids))
    rating = feedback_data.evaluation
    comment = feedback_data.comment

    try:
        feedback_id = save_feedback_to_db(query=query, actual_output=actual_output, chunk_ids=chunk_ids, rating=rating, comment=comment)
        return FeedbackResult(feedback_id=feedback_id)
    except Exception as e:
        logger.error(f"ERROR: Fallo al guardar el feedback: {e}")
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


# --- ENDPOINT 4: Procesamiento Pesado (Llamado por Airflow) ---

@app.post("/process_document", response_model=ProcessingResult)
async def process_document_endpoint(input_data: ProcessDocumentInput):
    logger.info(f"\n--- INICIANDO PROCESAMIENTO  ---")
    
    success = process_single_document(
        input_data.path_file,
        input_data.path_file_clean,
        input_data.hash_file
    )
    if success:
        return ProcessingResult(success=True, message="Documento procesado con éxito.")
    else:
        raise HTTPException(status_code=500, detail="Fallo en el procesamiento del documento.")

# --- ENDPOINT 5: Endpoint de prueba LLMs y RAG ---
@app.get("/run_deepeval_tests")
def run_deepeval_tests_endpoint():
    """
    **Endpoint: Ejecutar pruebas DeepEval y devolver resultados**
    """
    try:
        results = run_deepeval_tests()
        return JSONResponse(content=results)
    except Exception as e:
        logger.error(f"Error ejecutando tests DeepEval: {e}")
        raise HTTPException(status_code=500, detail=f"Error al ejecutar los tests: {str(e)}")

# --- ENDPOINT 6: Endpoint de pruebas scores ---
@app.get("/run_deepeval_test_scores")
def run_deepeval_test_scores_endpoint():
    """
    **Endpoint: Ejecutar pruebas DeepEval y devolver scores numéricos**
    """
    try:
        results = run_deepeval_test_scores()
        return JSONResponse(content=results)
    except Exception as e:
        logger.error(f"Error ejecutando tests DeepEval (scores): {e}")
        raise HTTPException(status_code=500, detail=f"Error al ejecutar los tests: {str(e)}")


### -------------------------------------------------------------------- ###
@app.get("/get_feedback_last_week", response_model=GetFeedbackResponse)
async def get_feedback_last_week_endpoint():
    """
    **Endpoint: Obtener feedback con rating bajo de la semana pasada.**
    """
    try:
        feedback_data = get_feedback_last_week_from_db()
        return GetFeedbackResponse(feedback_data=feedback_data)
    except Exception as e:
        logger.error(f"ERROR: Fallo al obtener feedback de la semana pasada: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno del servidor al intentar obtener el feedback."
        )
    
@app.post("/get_expert_annotations", response_model=GetAnnotationsResponse)
async def get_expert_annotations_endpoint(request: GetAnnotationsRequest):
    """
    **Endpoint: Obtener anotaciones de experto para una lista de feedback_ids.**
    """
    try:
        feedback_ids = request.feedback_ids
        annotations = get_expert_annotations_from_db(feedback_ids)
        return GetAnnotationsResponse(annotations=annotations)
    except Exception as e:
        logger.error(f"ERROR: Fallo al obtener anotaciones de experto: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno del servidor al intentar obtener las anotaciones."
        )
    
@app.post("/run_evaluation_suite", response_model=RunEvaluationResponse)
async def run_evaluation_suite_endpoint(request: RunEvaluationRequest):
    """
    **Endpoint: Ejecutar la suite de evaluación de DeepEval con los datos proporcionados.**
    """
    try:
        feedback_list = [item.dict() for item in request.feedback_list] # Convertir Pydantic a dict
        annotations_map = request.annotations_map
        # Usar el vector_store ya inicializado globalmente
        result = run_evaluation_suite_logic(feedback_list, annotations_map, vector_store)
        return RunEvaluationResponse(status=result["status"], message=result["message"])
    except Exception as e:
        logger.error(f"ERROR: Fallo al ejecutar la suite de evaluación: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno del servidor al intentar ejecutar la evaluación."
        )
    
@app.post("/load_expert_annotations")
async def load_expert_annotations_endpoint(request: LoadAnnotationsRequest, current_user: str ): # <-- Agregar autenticación real
    """
    **Endpoint (requiere autenticación): Cargar anotaciones de experto.**
    """
    # Verificar si el usuario es un experto autorizado
    # if not current_user.is_expert: # <-- Lógica de autorización
    #     raise HTTPException(status_code=403, detail="No autorizado para cargar anotaciones.")
    try:
        inserted_count = 0
        for item in request.annotations:
            # Usar execute_query para insertar
            insert_query = """
                INSERT INTO expert_annotations (feedback_id, query, actual_output, expected_output, annotated_by)
                SELECT uf.feedback_id, uf.query, uf.llm_response, %s, %s
                FROM user_feedback uf
                WHERE uf.feedback_id = %s
                AND NOT EXISTS (SELECT 1 FROM expert_annotations ea WHERE ea.feedback_id = %s);
            """
            params = (item.expected_output, request.annotated_by, item.feedback_id, item.feedback_id)
            result = execute_query(user='appuser', query=insert_query, fetch=False, params=params)
            # execute_query puede devolver el número de filas afectadas o un booleano
            # Ajusta según tu implementación de execute_query
            if result: # o si devuelve filas afectadas > 0
                inserted_count += 1

        return {"status": "success", "message": f"{inserted_count} anotaciones insertadas."}
    except Exception as e:
        logger.error(f"ERROR: Fallo al cargar anotaciones: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno del servidor al intentar cargar las anotaciones."
        )
    
# Endpoint para obtener resultados de evaluación
@app.get("/get_evaluation_results", response_model=GetEvaluationResultsResponse)
async def get_evaluation_results(
    run_id: Optional[str] = Query(None), # Usar Query para parámetros de filtro
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    evaluation_suite: Optional[str] = Query(None),
    # ... otros filtros ...
):
    """
    **Endpoint: Obtener resultados de evaluación de DeepEval desde la base de datos.**
    """
    try:
        # Construir la consulta SQL con los filtros recibidos
        query_sql = """
            SELECT run_id, run_timestamp, query_text, metric_name, metric_value, evaluation_suite, model_name, feedback_id
            FROM evaluation_results
            WHERE 1=1
        """
        params = []
        if run_id:
            query_sql += " AND run_id = %s"
            params.append(run_id)
        if start_date:
            query_sql += " AND run_timestamp >= %s"
            params.append(start_date)
        if end_date:
            query_sql += " AND run_timestamp <= %s"
            params.append(end_date)
        if evaluation_suite:
            query_sql += " AND evaluation_suite = %s"
            params.append(evaluation_suite)

        query_sql += " ORDER BY run_timestamp DESC, metric_name;"

        # Ejecutar la consulta
        rows = execute_query(user='appuser', query=query_sql, fetch=True, params=params)

        # Convertir resultados a la estructura esperada por el modelo Pydantic
        results = [
            EvaluationMetric(
                run_id=row['run_id'],
                run_timestamp=row['run_timestamp'],
                query_text=row['query_text'],
                metric_name=row['metric_name'],
                metric_value=row['metric_value'],
                evaluation_suite=row['evaluation_suite'],
                model_name=row['model_name'],
                feedback_id=row['feedback_id']
            )
            for row in rows
        ]

        return GetEvaluationResultsResponse(results=results)
    except Exception as e:
        logger.error(f"ERROR: Fallo al obtener resultados de evaluación: {e}")
        raise HTTPException(
            status_code=500,
            detail="Fallo interno del servidor al intentar obtener los resultados."
        )
    
### ---------------------------------------------------------------------- ###

# --- ENDPOINT 7: Endpoint de prueba de conexión ---
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "RAG Core API"}