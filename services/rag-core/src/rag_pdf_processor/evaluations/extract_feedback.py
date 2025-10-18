import os
import json
from typing import List, Dict, Optional
from rag_pdf_processor.utils.postgres_query import execute_query
from rag_pdf_processor.retrieval.vector_retriever import VectorRetriever
from dotenv import load_dotenv
load_dotenv()

def get_retrieval_context_content_from_ids(chunk_ids_str: str, retriever: VectorRetriever) -> List[Dict]:
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
            print(f"⚠️ Chunk con ID {cid} no encontrado en Qdrant.")
            contents.append(None)  # O puedes omitirlo

    return contents

def main():
    # Configura tu VectorRetriever
    retriever = VectorRetriever(collection_name="retrieval_context-hybrid")

    query_sql = """
        SELECT query, actual_output, chunk_ids
        FROM user_feedback
        WHERE rating = 3
    """
    user = os.getenv("APP_DB_USER")
    rows = execute_query(user, query_sql)

    result = []

    for row in rows:
        query = row['query']
        actual_output = row['actual_output']
        chunk_ids_str = row['chunk_ids']

        if chunk_ids_str:
            retrieval_context_content = get_retrieval_context_content_from_ids(chunk_ids_str, retriever)
        else:
            retrieval_context_content = []

        result.append({
            "query": query,
            "actual_output": actual_output,
            "retrieval_context": retrieval_context_content
        })

    # Guardar en un archivo JSON
    with open("feedback_with_retrieval_context.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Archivo JSON generado correctamente.")

if __name__ == "__main__":
    main()