import sys
import logging
import os

import psycopg2
from typing import List, Dict
import hashlib
from fastembed import TextEmbedding

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
logger = logging.getLogger(__name__)

class QdrantVectorStore:
    def __init__(self, host: str = "qdrant", port: int = 6333):
        try:
            self.client = QdrantClient(
                host=host, 
                port=port,
                timeout=10.0
            )
            self.collection_name = "retrieval_context-hybrid"  # ← Nombre de la colección híbrida
            self.embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")  # ← Modelo para generar embeddings
            
            # Crear colección híbrida
            self._create_hybrid_collection()
            
            logger.info("✅ Cliente Qdrant híbrido inicializado")
        except Exception as e:
            logger.error(f"❌ Error inicializando cliente Qdrant: {e}")
            raise
    
    def test_connection(self):
        """Prueba la conexión básica"""
        try:
            response = self.client.get_collections()
            logger.info("✅ Conexión a Qdrant verificada")
            return True
        except Exception as e:
            logger.error(f"❌ Error de conexión: {e}")
            return False
    
    def _create_hybrid_collection(self):
        """Crea la colección híbrida si no existe"""
        try:
            # Intentar obtener la colección
            collection_info = self.client.get_collection(self.collection_name)
            logger.info(f"✅ Colección '{self.collection_name}' ya existe")
        except UnexpectedResponse as e:
            if e.status_code == 404:
                logger.info(f"🔄 Creando colección híbrida '{self.collection_name}'...")
                try:
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
                    logger.info(f"✅ Colección híbrida '{self.collection_name}' creada exitosamente")
                except Exception as create_error:
                    logger.error(f"❌ Error creando colección: {create_error}")
                    raise
            else:
                logger.error(f"❌ Error inesperado: {e}")
                raise
        except Exception as e:
            logger.error(f"❌ Error verificando colección: {e}")
            raise

    def create_collection_if_not_exists(self, vector_size: int = 384):
        """Mantener para compatibilidad, pero usar _create_hybrid_collection"""
        self._create_hybrid_collection()

    def insert_retrieval_context(self, retrieval_context: List[Dict]):
        """
        Inserta retrieval_context con dense + sparse vectors.
        
        Args:
            retrieval_context (list): Lista con la estructura:
                [
                    {
                        "book_name": str,
                        "Chapter": str,
                        "Content": str
                    }
                ]
        """
        successful_inserts = 0
        
        for chunk in retrieval_context:
            try:
                # Generar ID único basado en el contenido
                content_str = f"{chunk['book_name']}_{chunk['Chapter']}_{chunk['Content'][:50]}"
                chunk_id = hashlib.md5(content_str.encode()).hexdigest()
                
                # Generar dense vector (embedding semántico) usando fastembed
                dense_vector = list(self.embedding_model.embed([chunk["Content"]]))[0].tolist()
                
                # Preparar punto para Qdrant con dense + sparse vectors
                point = models.PointStruct(
                    id=chunk_id,
                    vector={
                        "dense": dense_vector,
                        "sparse": models.Document(
                            text=chunk["Content"],
                            model="Qdrant/bm25",
                        ),
                    },
                    payload={
                        "book_name": chunk["book_name"],
                        "Chapter": chunk["Chapter"],
                        "Content": chunk["Content"]
                    }
                )
                
                # Insertar en Qdrant
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[point]
                )
                
                successful_inserts += 1
                
            except Exception as e:
                logger.error(f"❌ Error insertando chunk {chunk.get('book_name', 'unknown')}: {e}")
        
        logger.info(f"✅ {successful_inserts}/{len(retrieval_context)} puntos insertados en '{self.collection_name}'.")
        return successful_inserts

def save_processing_metadata(connection_string, file_path, file_name, hash_md5, successfully_processed=None, error_message=None):
    """
    Guarda o actualiza la metadata del procesamiento de documentos en PostgreSQL
    
    Args:
        connection_string: String de conexión a PostgreSQL
        file_path: Ruta completa del archivo
        file_name: Nombre del archivo
        hash_md5: Hash MD5 del archivo
        successfully_processed: Boolean indicando si se procesó correctamente (opcional)
        error_message: Mensaje de error si falló (opcional)
    """
    
    try:
        print(connection_string)
        # Conectar a PostgreSQL
        conn = psycopg2.connect(connection_string)
        cur = conn.cursor()
        
        # Verificar si el registro ya existe
        cur.execute("""
            SELECT id FROM processed_documents 
            WHERE hash_md5 = %s
        """, (hash_md5,))
        
        existing_record = cur.fetchone()
        
        if existing_record:
            # Actualizar registro existente
            cur.execute("""
                UPDATE processed_documents 
                SET path = %s,
                    file_name = %s,
                    state = TRUE,
                    updated_at = CURRENT_TIMESTAMP,
                    successfully_processed = %s,
                    error_message = %s
                WHERE hash_md5 = %s
            """, (file_path, file_name, successfully_processed, error_message, hash_md5))
            
            logger.info(f"🔄 Actualizado registro para {file_name}")
        else:
            # Insertar nuevo registro
            cur.execute("""
                INSERT INTO processed_documents 
                (path, file_name, hash_md5, state, successfully_processed, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (file_path, file_name, hash_md5, True, successfully_processed, error_message))
            
            logger.info(f"🆕 Insertado nuevo registro para {file_name}")
        
        # Confirmar cambios
        conn.commit()
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.info(f"❌ Error al guardar metadata: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
    

# Test rápido:
if __name__ == "__main__":
    try:
        store = QdrantVectorStore(host="localhost", port=6335)
        store.test_connection()
        store._create_collection()
        logger.info("✅ Todo funciona correctamente!")
    except Exception as e:
        logger.info(f"❌ Error en test: {e}")

