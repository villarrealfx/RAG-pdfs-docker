import logging
from typing import List, Dict, Optional
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding
import uuid


from rag_pdf_processor.retrieval.llm_interface import LLMInterface
from .query_rewriter import QueryRewriter 
logger = logging.getLogger(__name__)

class VectorRetriever:
    """Sistema de búsqueda híbrida: dense + sparse vectors"""
    
    def __init__(self, 
                 host: str = "qdrant", 
                 port: int = 6333, 
                 collection_name: str = "retrieval_context-hybrid",
                 embedding_model: str = "BAAI/bge-small-en-v1.5"):
        """
        Inicializar sistema de búsqueda híbrida
        
        Args:
            host: Host de Qdrant
            port: Puerto de Qdrant
            collection_name: Nombre de la colección híbrida
            embedding_model: Modelo para embeddings densos
        """
        self.client = QdrantClient(host=host, port=port, timeout=10.0)
        self.collection_name = collection_name
        self.embedding_model = TextEmbedding(model_name=embedding_model)
        
        # Crear colección si no existe
        self._create_hybrid_collection()
        
        logger.info(f"✅ HybridRetriever inicializado para colección: {collection_name}")
        logger.info(f"📝 Modelos: Dense ({embedding_model}) + Sparse (BM25)")
    
    def _create_hybrid_collection(self):
        """Crear colección con dense + sparse vectors"""
        try:
            # Verificar si colección existe
            self.client.get_collection(self.collection_name)
            logger.info(f"✅ Colección '{self.collection_name}' ya existe")
        except:
            logger.info(f"🔄 Creando colección híbrida '{self.collection_name}'...")
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=384,  # Tamaño de BGE-small
                        distance=models.Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                }
            )
            logger.info(f"✅ Colección híbrida '{self.collection_name}' creada")
    
    def upsert_chunk(self, chunk_data: Dict) -> bool:
        """
        Insertar o actualizar un chunk con dense + sparse vectors
        
        Args:
            chunk_data: Diccionario con keys: book_name, Chapter, Content, id (opcional)
            
        Returns:
            True si éxito, False si falla
        """
        try:
            # Generar ID si no existe
            chunk_id = chunk_data.get("id", str(uuid.uuid4()))
            
            # Generar dense vector (embedding semántico)
            dense_vector = list(self.embedding_model.embed([chunk_data["Content"]]))[0].tolist()
            
            # Preparar punto para Qdrant
            point = models.PointStruct(
                id=chunk_id,
                vector={
                    "dense": dense_vector,
                    "sparse": models.Document(
                        text=chunk_data["Content"],
                        model="Qdrant/bm25",
                    ),
                },
                payload={
                    "book_name": chunk_data["book_name"],
                    "Chapter": chunk_data["Chapter"],
                    "Content": chunk_data["Content"]
                }
            )
            
            # Insertar en Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.debug(f"✅ Chunk insertado: {chunk_id[:8]}...", 
                        extra={"chunk_id": chunk_id, "book_name": chunk_data["book_name"]})
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error insertando chunk: {e}")
            return False
    
    def upsert_retrieval_context_batch(self, retrieval_context_data: List[Dict]) -> int:
        """
        Insertar múltiples retrieval_context en batch
        
        Args:
            retrieval_context_data: Lista de diccionarios con retrieval_context
            
        Returns:
            Número de retrieval_context insertados exitosamente
        """
        successful_inserts = 0
        
        for chunk_data in retrieval_context_data:
            if self.upsert_chunk(chunk_data):
                successful_inserts += 1
        
        logger.info(f"✅ {successful_inserts}/{len(retrieval_context_data)} retrieval_context insertados en '{self.collection_name}'")
        return successful_inserts
    
    def hybrid_search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Búsqueda híbrida: dense + sparse vectors con RRF fusion
        
        Args:
            query: Consulta del usuario
            limit: Número de resultados
            
        Returns:
            Lista de retrieval_context con similitud
        """
        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    # Búsqueda densa (semántica)
                    models.Prefetch(
                        query=list(self.embedding_model.embed([query]))[0].tolist(),
                        using="dense",
                        limit=limit * 2,
                    ),
                    # Búsqueda dispersa (palabras clave)
                    models.Prefetch(
                        query=models.Document(text=query, model="Qdrant/bm25"),
                        using="sparse",
                        limit=limit * 2,
                    ),
                ],
                # Fusionar resultados con RRF
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
            
            # Convertir resultados al formato estándar
            converted_results = []
            for point in results.points:
                result = {
                    "content": point.payload.get("Content", ""),
                    "book_name": point.payload.get("book_name", ""),
                    "chapter": point.payload.get("Chapter", ""),
                    "score": point.score,
                    "id": point.id
                }
                converted_results.append(result)
            
            logger.debug(f"🔍 Búsqueda híbrida encontró {len(converted_results)} resultados", 
                        extra={"query_length": len(query), "limit": limit})
            
            return converted_results
            
        except Exception as e:
            logger.error(f"❌ Error en búsqueda híbrida: {e}")
            return []
    
    def hybrid_search_with_rerank(self, query: str, limit: int = 5, use_rerank: bool = True) -> List[Dict]:
        """
        Búsqueda híbrida con opción de reclasificación
        
        Args:
            query: Consulta del usuario
            limit: Número de resultados
            use_rerank: Si True, aplica reclasificación de documentos
            
        Returns:
            Lista de retrieval_context con similitud (posiblemente reclasificados)
        """
        # Primero hacer la búsqueda híbrida normal
        results = self.hybrid_search(query, limit=limit*2)  # Buscar más para rerank
        
        if use_rerank and results:
            try:
                from .reranker import DocumentReranker
                reranker = DocumentReranker()
                # Reclasificar los resultados
                reranked_results = reranker.rerank(query, results, top_k=limit)
                logger.info(f"✅ Reclasificación aplicada: {len(results)} → {len(reranked_results)} resultados", 
                        extra={"original_scores": [r.get("original_score", 0) for r in reranked_results],
                                "rerank_scores": [r.get("rerank_score", 0) for r in reranked_results]})
                return reranked_results
            except Exception as e:
                logger.warning(f"⚠️ Error en reclasificación, usando resultados originales: {e}")
                return results[:limit]
        
        return results[:limit]
    
    def hybrid_search_with_query_rewrite(self, query: str, limit: int = 5, use_rerank: bool = True, llm_interface_for_rewrite: Optional[LLMInterface] = None) -> List[Dict]:
        """
        Búsqueda híbrida que primero reescribe la consulta original.

        Args:
            query: Consulta original del usuario.
            limit: Número de resultados.
            use_rerank: Si True, aplica reclasificación después de la búsqueda.
            llm_interface_for_rewrite: Instancia de LLMInterface para usar en la reescritura.
                                       Si es None, se asume que está disponible o se maneja el error.

        Returns:
            Lista de retrieval_context con similitud (posiblemente reclasificados y basados en la consulta reescrita).
        """
        if not llm_interface_for_rewrite:
            logger.warning("⚠️ No se proporcionó LLMInterface para reescritura. Usando la consulta original.")
            # Si no se proporciona un LLMInterface, usar la búsqueda normal sin reescritura
            # O lanzar un error si la reescritura es obligatoria
            return self.hybrid_search_with_rerank(query, limit, use_rerank)

        try:
            # 1. Inicializar QueryRewriter
            rewriter = QueryRewriter(llm_interface_for_rewrite)

            # 2. Reescribir la consulta
            rewritten_query = rewriter.rewrite_query(query)
            logger.info(f"🔄 Consulta original: '{query}' -> Reescrita: '{rewritten_query}'")

            # 3. Realizar la búsqueda híbrida con la consulta reescrita
            # Usar el método existente de búsqueda con reclasificación
            results = self.hybrid_search_with_rerank(rewritten_query, limit=limit, use_rerank=use_rerank)

            # Opcional: Añadir la consulta reescrita a los resultados para trazabilidad
            # for result in results:
            #     result['rewritten_query_used'] = rewritten_query

            logger.debug(f"🔍 Búsqueda con consulta reescrita encontró {len(results)} resultados.")
            return results

        except Exception as e:
            logger.error(f"❌ Error en búsqueda con reescritura: {e}")
            # Si falla la reescritura o la búsqueda subsiguiente, intentar con la consulta original
            logger.info("Intentando búsqueda con la consulta original...")
            return self.hybrid_search_with_rerank(query, limit, use_rerank)

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict]:
        """Obtener un chunk específico por ID"""
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[chunk_id],
                with_payload=True
            )
            
            if points:
                point = points[0]
                return {
                    "content": point.payload.get("Content", ""),
                    "book_name": point.payload.get("book_name", ""),
                    "chapter": point.payload.get("Chapter", ""),
                    "id": point.id
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo chunk por ID {chunk_id}: {e}")
            return None