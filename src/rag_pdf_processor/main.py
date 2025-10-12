import os
import logging

from rag_pdf_processor.utils.logging_config import setup_logging_docker
from rag_pdf_processor.utils.config import DEV_MODE
from rag_pdf_processor.utils.process_pdfs import (
    scan_folders,
    calculate_hash_md5,
    document_already_processed,
    process_single_document
)

# Configurar logging al inicio
setup_logging_docker(service_name="pdf-processor", 
                     development_mode=DEV_MODE) 
logger = logging.getLogger(__name__)


def main():
    """Función principal"""
    logger.info("🚀 Iniciando el procesamiento de PDFs")
    
    # 1. Buscar archivos
    logger.info("🔍 Escaneando carpetas...")
    files = scan_folders()
    if not files:
        logger.warning("No se encontraron archivos para procesar")
        return
    
    # 2. Calcular hashes
    logger.info(f"📄 Archivos encontrados: {len(files)}")
    hashes = calculate_hash_md5(files)
    
    # 3. Verificar qué archivos ya fueron procesados
    logger.info("📊 Verificando estado de procesamiento...")
    pending_files = document_already_processed(hashes)
    if not pending_files:
        logger.info("✅ Todos los archivos ya han sido procesados")
        return
    
    logger.info(f"📄 Archivos pendientes por procesar: {len(pending_files)}")
    
    # 4. Procesar cada archivo pendiente
    for file_info in pending_files:
        path_file = file_info[0]  # path
        hash_file = file_info[1]  # hash
        
        # Crear path para archivo limpio
        path_file_clean = os.path.join(
            os.path.dirname(path_file).replace('raw', 'clean'),
            os.path.basename(path_file)
        )
        
        logger.info(f"🔄 Procesando: {os.path.basename(path_file)}", 
                   extra={"documento": os.path.basename(path_file), "hash": hash_file})
        
        # Procesar documento
        process_single_document(path_file, path_file_clean, hash_file)
    
    logger.info("🎉 Todos los manuales procesados!")

if __name__ == "__main__":
    main()