import os
import shutil
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import logging

from rag_pdf_processor.utils.postgres_query import execute_query
from rag_pdf_processor.utils.config import RAW_DATA_DIR, PROCESSED_DATA_DIR, PG_CONNECTION

from rag_pdf_processor.chunker_text import (
    extract_structured_content,
    create_semantic_chunks
)
from rag_pdf_processor.database_pg import (
    QdrantVectorStore,
    save_processing_metadata
)
from rag_pdf_processor.clean_pdf import process_pdf_advanced


logger = logging.getLogger(__name__)

def scan_folders(monitored_folders: Optional[List[str]] = None) -> List[str]:
    """
    Escanea carpetas y devuelve lista de PDFs encontrados
    
    Args:
        monitored_folders: Lista de carpetas a escanear. Si es None, usa las predeterminadas
    
    Returns:
        Lista de rutas completas de documentos PDF encontrados
    """
    if monitored_folders is None:
        monitored_folders = [RAW_DATA_DIR]

    documents_found = []
    
    for folder in monitored_folders:
        folder_path = Path(folder)
        
        if not folder_path.exists():
            logger.warning(f"Carpeta no encontrada: {folder}")
            continue
        
        if not folder_path.is_dir():
            logger.warning(f"La ruta no es una carpeta: {folder}")
            continue
        
        logger.info(f"Escaneando carpeta: {folder_path}", extra={"carpeta": str(folder_path)})
        
        try:
            for file_path in folder_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() == '.pdf':
                    documents_found.append(str(file_path))
                    logger.debug(f"Documento encontrado: {file_path.name}")
                    
        except PermissionError:
            logger.error(f"Permiso denegado para acceder a: {folder}")
        except Exception as e:
            logger.error(f"Error inesperado escaneando {folder}: {e}")
    
    if not documents_found:
        logger.info("No se encontraron documentos PDF en las carpetas monitoreadas")
    else:
        logger.info(f"Total de documentos encontrados: {len(documents_found)}")
    
    return documents_found

def calculate_hash_md5(documentos: List[str]) -> Dict[str, Optional[str]]:
    """
    Calcula hash MD5 para cada documento encontrado
    
    Args:
        documentos: Lista de rutas de documentos
    
    Returns:
        Diccionario con rutas como clave y hash MD5 como valor
    """
    if not documentos:
        logger.info("No hay documentos para calcular hash")
        return {}
    
    hashes = {}
    
    for doc_path in documentos:
        file_path = Path(doc_path)
        
        if not file_path.exists():
            logger.warning(f"Documento no encontrado: {doc_path}")
            hashes[doc_path] = None
            continue
        
        if not file_path.is_file():
            logger.warning(f"La ruta no es un archivo: {doc_path}")
            hashes[doc_path] = None
            continue
        
        try:
            # Verificar tamaño del archivo antes de procesar
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.warning(f"Archivo vacío: {doc_path}")
                hashes[doc_path] = None
                continue
            
            hash_md5 = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_md5.update(chunk)
            
            file_hash = hash_md5.hexdigest()  # ← Aquí obtienes la cadena hexadecimal
            hashes[doc_path] = file_hash

            logger.debug(f"Hash calculado para {file_path.name}: {file_hash[:8]}...", 
            extra={"archivo": file_path.name, "hash": file_hash})
            
        except PermissionError:
            logger.error(f"Permiso denegado para leer: {doc_path}")
            hashes[doc_path] = None
        except Exception as e:
            logger.error(f"Error calculando hash para {doc_path}: {e}")
            hashes[doc_path] = None

    return hashes

def document_already_processed(hashes: Dict[str, Optional[str]]) -> List[Tuple[str, str]]:
    """
    Verifica si documentos ya fueron procesados consultando la base de datos
    
    Args:
        hashes: Diccionario con rutas de archivos y sus hashes MD5
    
    Returns:
        Lista de tuplas (ruta_archivo, hash_md5) de documentos no procesados
    """
    if not hashes:
        logger.info("No hay documentos para verificar")
        return []
    
    new_documents = []
    processed_count = 0
    
    for file_path, hash_md5 in hashes.items():
        if not hash_md5:
            logger.warning(f"Saltando documento sin hash: {file_path}")
            continue
        
        try:
            user = 'appuser'
            # IMPORTANTE: Usar parámetros para evitar SQL injection
            pg_query = "SELECT * FROM processed_documents WHERE hash_md5 = %s"
            
            data = execute_query(user, pg_query, fetch=True, params=(hash_md5,))
            
            if not data:
                new_documents.append((file_path, hash_md5))
                logger.info(f"Documento nuevo encontrado: {os.path.basename(file_path)}")
            else:
                processed_count += 1
                logger.debug(f"Documento ya procesado: {os.path.basename(file_path)}")
                
        except Exception as e:
            logger.error(f"Error verificando documento {os.path.basename(file_path)}: {e}")
            # Decision: No agregar a nuevos si hay error en la consulta
            # Podría ser un error transitorio de BD
    
    logger.info(f"Documentos nuevos: {len(new_documents)}, Ya procesados: {processed_count}")
    
    return new_documents

def move_file_to_processed(path_file, path_processed):
    """Mueve un archivo procesado al directorio de procesados"""
    
    # Crear directorio de destino si no existe
    if not os.path.exists(path_processed):
        os.makedirs(path_processed)
    
    # Obtener solo el nombre del archivo
    filename = os.path.basename(path_file)
    destination_path = os.path.join(path_processed, filename)
    
    # Mover el archivo
    try:
        shutil.move(path_file, destination_path)
        logger.info(f"✅ Archivo '{filename}' movido a '{path_processed}'")
        return True
    except FileNotFoundError:
        logger.info(f"❌ Error: El archivo de origen '{path_file}' no fue encontrado.")
        return False
    except PermissionError:
        logger.info(f"❌ Error: Permisos insuficientes para mover '{path_file}'.")
        return False
    except Exception as e:
        logger.info(f"❌ Error al mover el archivo: {e}")
        return False


def process_single_document(path_file, path_file_clean, hash_file):
    """Procesa un solo documento PDF"""
    

    logger.info(f"path_file: {path_file}")
    logger.info(f"path_file_clean: {path_file_clean}")
    logger.info(f"hash_file: {hash_file}")

    try:
        logger.info(f"🔄 Procesando: {os.path.basename(path_file)}")
        
        # 1. Limpieza de pdf ✅
        logger.info("1. Limpiando PDF...")
        process_pdf_advanced(path_file, path_file_clean)
        
        # 2. Crear contenido estructurado ✅
        logger.info("2. Extrayendo contenido estructurado...")
        content = extract_structured_content(path_file_clean)
        
        # 3. Crear chunks semánticos basados en el contenido ✅
        logger.info("3. Creando chunks semánticos...")
        documents = create_semantic_chunks(content, os.path.basename(path_file_clean))

        if not documents:
            logger.error("⚠️  No se generaron chunks. Guardando como fallido...")
            save_processing_metadata(
                PG_CONNECTION, 
                path_file, 
                os.path.basename(path_file), 
                hash_file, 
                successfully_processed=False, 
                error_message="No se generaron chunks"
            )
            return False
        
        # 4. Guardar vectores en Qdrant CON BÚSQUEDA HÍBRIDA
        logger.info(f"4. Guardando {len(documents)} chunks en Qdrant (colección híbrida)...")
        vector_store = QdrantVectorStore()  
        vector_store.insert_chunks(documents)  # ← Ahora inserta dense + sparse vectors
        
        # 5. Guardar metadata en PostgreSQL
        logger.info("5. Guardando metadata de procesamiento...")
        save_processing_metadata(
            PG_CONNECTION, 
            path_file, 
            os.path.basename(path_file), 
            hash_file, 
            successfully_processed=True, 
            error_message=None
        )
        
        # 6. Mover archivo original a data/processed
        logger.info("6. Moviendo archivo a procesados...")
        if move_file_to_processed(path_file, PROCESSED_DATA_DIR):
            logger.info(f"✅ Documento {os.path.basename(path_file)} procesado exitosamente!")
            return True
        else:
            logger.info(f"⚠️  Documento procesado pero error al mover archivo: {os.path.basename(path_file)}")
            return False
    except Exception as e:
        logger.error(f"❌ Error procesando {os.path.basename(path_file)}: {e}") 
        # Guardar error en metadata
        # try:
        #     save_processing_metadata(
        #         PG_CONNECTION, 
        #         path_file, 
        #         os.path.basename(path_file), 
        #         hash_file, 
        #         successfully_processed=False, 
        #         error_message=str(e)
        #     )
        # except:
        #     pass
        return False

if __name__ == "__main__":
    # Ejemplo de uso
    folders_to_scan = ["data/raw", "data/more_pdfs"]
    documentos = scan_folders()
    hashes = calculate_hash_md5(documentos)
    nuevos_documentos = document_already_processed(hashes)
    
    logger.info(f"Documentos listos para procesamiento: {len(nuevos_documentos)}")
    logger.info(nuevos_documentos)
    for doc, hsh in nuevos_documentos:
        logger.info(f"- {doc} (MD5: {hsh})")