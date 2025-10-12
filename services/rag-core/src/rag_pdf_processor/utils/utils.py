# ./procesador-pdf/utils.py
import hashlib
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

def calcular_hash_archivo(file_path: str, chunk_size: int = 8192) -> Optional[str]:
    """
    Calcula el hash MD5 de un archivo de manera eficiente.
    
    Args:
        file_path: Ruta al archivo
        chunk_size: Tamaño de bloques para lectura (bytes)
    
    Returns:
        Hash MD5 del archivo o None si hay error
    """
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error calculando hash para {file_path}: {e}")
        return None

def obtener_metadatos_documento(ruta: str) -> Dict[str, Any]:
    """
    Obtiene metadatos básicos de un documento.
    
    Args:
        ruta: Ruta al archivo
    
    Returns:
        Diccionario con metadatos del documento
    """
    try:
        if not os.path.exists(ruta):
            return {"error": "Archivo no encontrado"}
        
        stat_info = os.stat(ruta)
        path_obj = Path(ruta)
        
        return {
            "nombre_archivo": path_obj.name,
            "ruta_completa": str(path_obj.absolute()),
            "directorio": str(path_obj.parent),
            "extension": path_obj.suffix.lower(),
            "tamaño_bytes": stat_info.st_size,
            "tamaño_mb": round(stat_info.st_size / (1024 * 1024), 2),
            "fecha_modificacion": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "fecha_acceso": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            "hash_md5": calcular_hash_archivo(ruta),
            "existe": True
        }
    except Exception as e:
        logger.error(f"Error obteniendo metadatos para {ruta}: {e}")
        return {"error": str(e), "existe": False}

def validar_archivo_pdf(ruta: str) -> bool:
    """
    Valida si un archivo es un PDF válido.
    
    Args:
        ruta: Ruta al archivo
    
    Returns:
        True si es PDF válido, False otherwise
    """
    try:
        if not ruta.lower().endswith('.pdf'):
            return False
        
        if not os.path.exists(ruta):
            return False
        
        # Verificar magic number de PDF
        with open(ruta, 'rb') as f:
            header = f.read(5)
            return header.startswith(b'%PDF-')
            
    except Exception as e:
        logger.error(f"Error validando PDF {ruta}: {e}")
        return False

def formatear_tamaño_bytes(tamaño_bytes: int) -> str:
    """
    Formatea tamaño en bytes a formato legible.
    
    Args:
        tamaño_bytes: Tamaño en bytes
    
    Returns:
        String formateado (ej: "2.5 MB")
    """
    for unidad in ['B', 'KB', 'MB', 'GB']:
        if tamaño_bytes < 1024.0:
            return f"{tamaño_bytes:.2f} {unidad}"
        tamaño_bytes /= 1024.0
    return f"{tamaño_bytes:.2f} TB"

def crear_directorio_si_no_existe(ruta: str) -> bool:
    """
    Crea un directorio si no existe.
    
    Args:
        ruta: Ruta del directorio a crear
    
    Returns:
        True si se creó o ya existía, False si hay error
    """
    try:
        Path(ruta).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creando directorio {ruta}: {e}")
        return False

def limpiar_nombre_archivo(nombre: str) -> str:
    """
    Limpia un nombre de archivo de caracteres inválidos.
    
    Args:
        nombre: Nombre de archivo a limpiar
    
    Returns:
        Nombre limpio
    """
    caracteres_invalidos = '<>:"/\\|?*'
    for char in caracteres_invalidos:
        nombre = nombre.replace(char, '_')
    return nombre[:255]  # Limitar longitud