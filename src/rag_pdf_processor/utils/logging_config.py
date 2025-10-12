import logging
import sys
import json
from datetime import datetime

# Variable para evitar múltiples configuraciones
_logging_configured = False

def setup_logging_docker(
    service_name: str = "pdf-processor",
    log_level: int = logging.INFO,
    use_json_format: bool = True,
    development_mode: bool = False
):
    """
    Configura logging para entorno Docker.
    - use_json_format: Si True, usa JSON; si False, formato legible
    - development_mode: Si True, aumenta nivel de debug
    """
    global _logging_configured
    
    if _logging_configured:
        logging.info(f"Logging ya configurado previamente para servicio: {service_name}")
        return
    
    _logging_configured = True
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    
    # Decidir formato basado en ambos parámetros
    if development_mode or not use_json_format:
        # Formato legible (desarrollo o cuando se especifica)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)-20s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%H:%M:%S"
        )
        if development_mode:
            log_level = logging.DEBUG  # Más verbose en desarrollo
    else:
        # Formato JSON (producción por defecto)
        formatter = StructuredFormatter(service_name=service_name)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    
    root_logger.addHandler(handler)
    
    logging.info(f"✅ Logging configurado para servicio: {service_name}")
    return root_logger

class StructuredFormatter(logging.Formatter):
    def __init__(self, service_name: str = "pdf-processor"):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
            "service": self.service_name,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if hasattr(record, 'extra') and record.extra:
            log_entry.update(record.extra)
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)