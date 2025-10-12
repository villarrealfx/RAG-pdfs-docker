import re
from pathlib import Path

def replace_prints_in_file(file_path):
    """Reemplaza prints por logging en un archivo Python"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Guardar el contenido original para comparar
    original_content = content
    
    # Patrón para detectar prints que contienen palabras clave de error
    error_patterns = [
        r'print\(["\'].*?error.*?["\'].*?\)',
        r'print\(["\'].*?Error.*?["\'].*?\)',
        r'print\(["\'].*?ERROR.*?["\'].*?\)',
        r'print\(["\'].*?failed.*?["\'].*?\)',
        r'print\(["\'].*?Failed.*?["\'].*?\)',
        r'print\(["\'].*?❌.*?["\'].*?\)',
        r'print\(["\'].*?⚠️.*?["\'].*?\)',
    ]
    
    # Reemplazar prints de error primero
    for pattern in error_patterns:
        content = re.sub(pattern, lambda m: m.group(0).replace('print(', 'logger.error('), content, flags=re.IGNORECASE)
    
    # Reemplazar prints de warning
    warning_patterns = [
        r'print\(["\'].*?warning.*?["\'].*?\)',
        r'print\(["\'].*?Warning.*?["\'].*?\)',
        r'print\(["\'].*?⚠️.*?["\'].*?\)',
    ]
    
    for pattern in warning_patterns:
        content = re.sub(pattern, lambda m: m.group(0).replace('print(', 'logger.warning('), content, flags=re.IGNORECASE)
    
    # Reemplazar prints de éxito
    success_patterns = [
        r'print\(["\'].*?✅.*?["\'].*?\)',
        r'print\(["\'].*?success.*?["\'].*?\)',
        r'print\(["\'].*?Success.*?["\'].*?\)',
    ]
    
    for pattern in success_patterns:
        content = re.sub(pattern, lambda m: m.group(0).replace('print(', 'logger.info('), content, flags=re.IGNORECASE)
    
    # Reemplazar prints restantes por info
    # Pero evitar reemplazar los que ya se reemplazaron
    content = re.sub(r'(?<!logger\.)print\(', 'logger.info(', content)
    
    # Añadir import de logging si no existe
    if 'import logging' not in content and 'logger = logging.getLogger' not in content:
        # Añadir imports después de los imports existentes
        import_match = re.search(r'(import.*?|from.*?import.*?)\n', content)
        if import_match:
            insert_pos = import_match.end()
            logging_imports = '\nimport logging\nlogger = logging.getLogger(__name__)\n'
            content = content[:insert_pos] + logging_imports + content[insert_pos:]
    
    # Asegurar que hay un logger definido
    if 'logger = logging.getLogger' not in content:
        # Buscar después de imports y añadir logger
        import_end = re.search(r'\n\n', content)
        if import_end:
            insert_pos = import_end.start()
            logger_def = '\nlogger = logging.getLogger(__name__)\n'
            content = content[:insert_pos] + logger_def + content[insert_pos:]
    
    # Si se hizo algún cambio, escribir el archivo
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Actualizado: {file_path}")
    else:
        print(f"ℹ️  Sin cambios: {file_path}")

def main():
    """Procesa todos los archivos .py en services/pdf_processor/"""
    pdf_processor_path = Path('services/pdf_processor')
    
    if not pdf_processor_path.exists():
        print("❌ Directorio services/pdf_processor no encontrado")
        return
    
    # Buscar todos los archivos .py
    py_files = list(pdf_processor_path.rglob('*.py'))
    
    print(f"🔍 Encontrados {len(py_files)} archivos .py")
    
    for py_file in py_files:
        print(f"📝 Procesando: {py_file}")
        replace_prints_in_file(py_file)
    
    print("\n✅ Proceso completado!")

if __name__ == "__main__":
    main()