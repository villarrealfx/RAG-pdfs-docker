import os

import logging
import sys

import re
import fitz

from typing import List, Dict

import pandas as pd

from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import FastEmbedEmbeddings


logger = logging.getLogger(__name__)

# Obtener la ruta del directorio padre (core)
parent_dir = os.path.abspath(os.path.join(os.getcwd(), os.pardir))

# Añadir el directorio padre a la ruta de búsqueda de Python
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from rag_pdf_processor.clean_pdf import process_pdf_advanced
from rag_pdf_processor.utils.config import CHUNKS_DATA_DIR


def extract_structured_content(pdf_path: str) -> List[Dict]:
        """Extrae texto manteniendo estructura temática"""
        doc = fitz.open(pdf_path)
        logger.info(len(doc))
        structured_content = []
        current_topic = {"chapter": "", "sections": []}
        current_section = {"title": "", "content": ""}
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num).get_text()
            
            lines = page.split('\n')
            for line in lines:
                line = line.strip()
                
                # Detectar capítulos
                if _is_chapter_header(line):
                    if current_section["content"]:
                        current_topic["sections"].append(current_section)
                    
                    if current_topic["sections"]:
                        structured_content.append(current_topic)
                    
                    current_topic = {"chapter": line, "sections": []}
                    current_section = {"title": "Introduction", "content": ""}
                
                # Contenido normal
                elif line:
                    current_section["content"] += line + " "
        
        # Añadir los últimos elementos
        if current_section["content"]:
            current_topic["sections"].append(current_section)
        if current_topic["sections"]:
            structured_content.append(current_topic)
        
        doc.close()
        return structured_content

def _is_chapter_header(line: str) -> bool:
        """Detecta encabezados de capítulo"""
        patterns = [
            r"^Chapter\s+\d+[:.-]",
            r"^Capítulo\s+\d+[:.-]", 
            # r"^[A-Z][A-Z\s]{10,}",  # Texto en mayúsculas largo
            # r"^\d+\.\s+[A-Z]",      # 1. TITLE CASE
            r"^CHAPTER\s+\d+"
        ]
        return any(re.match(pattern, line) for pattern in patterns)

def create_semantic_chunks(structured_content: List[Dict], manual_name: str) -> List[Dict]:
    """Crea chunks semánticos"""

    embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5", device="cpu")
    
    text_splitter = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type="percentile",
        min_chunk_size=50,
        )
    full_doc = []

    for i, doc in enumerate(structured_content):
        if not doc['chapter'] == '':
            for j in range(len(doc['sections'])):
                docs_chunk_new = text_splitter.create_documents([doc['sections'][j]['content']])
                for i, chunk in enumerate(docs_chunk_new):
                    contenido = chunk.page_content
                    embedding = embeddings.embed_query(contenido)
                    full_doc.append({"book_name": manual_name,"Chapter": doc['chapter'], "Content": contenido, "Embedding": embedding })
    
    logger.info(f"Se han creado {len(full_doc)} chunks semánticos.")

    df = pd.DataFrame(full_doc)
    df.to_csv(f"{CHUNKS_DATA_DIR}/{manual_name}_semantic_chunks.csv", index=False)
    logger.info(f"Se han creado archivo de respaldo con los chunks semánticos de {manual_name}.")

    return full_doc

if __name__ == '__main__':
    # estructurar documento
    path_file = f'{parent_dir}/data/raw/U-SD04_dev.pdf'
    path_file_clean = f'{parent_dir}/data/clean/{os.path.basename(path_file)[:-4]}_clean.pdf'

    pdf_clean = process_pdf_advanced(path_file, path_file_clean)
    content = extract_structured_content(path_file_clean)
    documents = create_semantic_chunks(content, os.path.basename(path_file_clean))  