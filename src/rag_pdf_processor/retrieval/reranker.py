import logging
from typing import List, Dict
from fastembed.rerank.cross_encoder import TextCrossEncoder

logger = logging.getLogger(__name__)

class DocumentReranker:
    """Sistema de reclasificación de documentos para mejorar relevancia"""
    
    def __init__(self, model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2"):
        """
        Inicializar modelo de reclasificación
        
        Args:
            model_name: Nombre del modelo de reranking
        """
        try:
            self.reranker = TextCrossEncoder(model_name=model_name)
            logger.info(f"✅ DocumentReranker inicializado con modelo: {model_name}")
        except Exception as e:
            logger.error(f"❌ Error inicializando reranker: {e}")
            raise
    
    def rerank(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Reclasificar documentos basados en relevancia con la consulta
        
        Args:
            query: Consulta original del usuario
            documents: Lista de documentos recuperados (con keys: content, book_name, chapter, score, id)
            top_k: Número de mejores resultados a devolver
            
        Returns:
            Lista de documentos reclasificados y ordenados por relevancia
        """

        try:
            if not documents:
                return []
            
            # Extraer solo los contenidos
            contents = [doc["content"] for doc in documents]
            
            # fastembed.rerank() devuelve una lista de floats directamente
            rerank_scores = list(self.reranker.rerank(query=query, documents=contents))
            
            # Crear lista de (índice_original, score_rerank, documento)
            scored_docs = []
            for i, (doc, rerank_score) in enumerate(zip(documents, rerank_scores)):
                updated_doc = doc.copy()
                updated_doc["rerank_score"] = float(rerank_score)  # Convertir a float
                updated_doc["original_score"] = doc.get("score", 0)  # Score original
                scored_docs.append((i, float(rerank_score), updated_doc))
            
            # Ordenar por score de reranking (descendente)
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            # Devolver los top_k documentos reclasificados
            reranked_docs = [item[2] for item in scored_docs[:top_k]]
            
            logger.debug(f"🔄 Reclasificación completada: {len(documents)} → {len(reranked_docs)} documentos")
            return reranked_docs
            
        except Exception as e:
            logger.error(f"❌ Error en reclasificación: {e}")
            # Si falla, devolver documentos originales sin cambios
            return documents[:top_k]