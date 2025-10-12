import sys

import logging
logger = logging.getLogger(__name__)
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import fitz
import re

def process_pdf_advanced(input_path, output_path):
    """
    Procesa PDF eliminando encabezados, pies, elementos gráficos y copyright lateral.
    """
    doc = fitz.open(input_path)
    start_page = 1
    
    for page_num in range(start_page, len(doc)):
        page = doc[page_num]
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        logger.info(f"Procesando página {page_num + 1}...")
        
        # Zonas de eliminación (ajustar según necesidad)
        header_zone = fitz.Rect(0, 0, page_width, page_height * 0.10)  # Top 10%
        footer_zone = fitz.Rect(0, page_height * 0.87, page_width, page_height)  # Bottom 13%
        left_zone = fitz.Rect(0, 0, page_width * 0.15, page_height)  # Left 15%
        
        # 1. ELIMINAR ELEMENTOS GRÁFICOS IZQUIERDOS (logo, líneas, etc.)
        image_list = page.get_images()
        for img_index, img_info in enumerate(image_list):
            image_rects = page.get_image_rects(img_info[0])
            for img_rect in image_rects:
                if left_zone.intersects(img_rect):
                    logger.info(f"  Eliminando imagen en zona izquierda: {img_rect}")
                    page.add_redact_annot(img_rect)
        
        # 2. ELIMINAR TEXTO NO DESEADO (incluyendo copyright con símbolo especial)
        blocks = page.get_text("dict")["blocks"]
        objects_to_remove = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = fitz.Rect(span["bbox"])
                        
                        # DEBUG: Mostrar texto encontrado
                        if left_zone.contains(bbox):
                            logger.info(f"  Texto en zona izquierda: '{text}' en bbox {bbox}")
                        
                        # ENCABEZADOS
                        if header_zone.contains(bbox):
                            header_patterns = [
                                r"Power Systems Control",
                                r"SINAUT Spectrum",
                                r"Network Applications", 
                                r"Data Analysis",
                                r"SDM Base Applications Reference"
                            ]
                            if any(re.search(pattern, text, re.IGNORECASE) for pattern in header_patterns):
                                logger.info(f"  Eliminando encabezado: '{text}'")
                                objects_to_remove.append(bbox)
                        
                        # PIES DE PÁGINA
                        if footer_zone.contains(bbox):
                            footer_patterns = [
                                r"U-NA20-E-2\.0\.0\.0",
                                r"Version 2\.0\.0\.0", 
                                r"\d{2}/\d{2}",  # Fechas
                                r"Page\s+\d+",   # Page <número>
                                r"^\d+$",        # Números simples
                                r"^\d+\s*/\s*\d+$", # Fracciones
                                r"^[ivxlcdm]+$",  # Números romanos
                                r"U-SD04-E-2.17.0.0",

                            ]
                            if any(re.search(pattern, text, re.IGNORECASE) for pattern in footer_patterns):
                                logger.info(f"  Eliminando pie de página: '{text}'")
                                objects_to_remove.append(bbox)
                        
                        # COPYRIGHT LATERAL (diferentes representaciones del símbolo ©)
                        if left_zone.contains(bbox):
                            copyright_patterns = [
                                r"Copyright.*Siemens AG.*1997-2004",
                                r"Copyright.*Siemens.*All Rights Reserved",
                                r"©.*Siemens AG.*1997-2004",
                                r"\(c\).*Siemens.*1997-2004",
                                r"Siemens AG.*1997-2004.*All Rights Reserved"
                            ]
                            
                            # Verificar patrones de copyright
                            for pattern in copyright_patterns:
                                if re.search(pattern, text, re.IGNORECASE):
                                    logger.info(f"  Eliminando copyright: '{text}'")
                                    objects_to_remove.append(bbox)
                                    break
                            
                            # Verificación adicional por palabras clave
                            copyright_keywords = ["Copyright", "Siemens", "1997-2004", "All Rights Reserved"]
                            if (any(keyword in text for keyword in copyright_keywords) and 
                                len(text) > 20):  # Texto largo típico de copyright
                                logger.info(f"  Eliminando por palabras clave: '{text}'")
                                objects_to_remove.append(bbox)
        
        # 3. ELIMINACIÓN POR ZONA IZQUIERDA (eliminar TODO texto en la zona izquierda como fallback)
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        bbox = fitz.Rect(span["bbox"])
                        if left_zone.contains(bbox):
                            # Evitar eliminar texto útil que pueda estar cerca del margen
                            text = span["text"].strip()
                            if len(text) > 30:  # Textos largos probablemente sean copyright
                                logger.info(f"  Eliminando texto lateral largo: '{text}'")
                                objects_to_remove.append(bbox)
                            elif not text.isalnum():  # Texto con símbolos especiales
                                logger.info(f"  Eliminando texto con símbolos: '{text}'")
                                objects_to_remove.append(bbox)

        # 3. Buscar y eliminar texto de copyright ESPECÍFICAMENTE
        text_instances = page.search_for("Copyright")
        for inst in text_instances:
            if (header_zone.intersects(inst) or 
                footer_zone.intersects(inst) or 
                left_zone.intersects(inst)):
                page.add_redact_annot(inst)
                logger.info(f"  Eliminando texto 'Copyright' encontrado")
        
        # Aplicar todas las redacciones
        for bbox in objects_to_remove:
            page.add_redact_annot(bbox)
        
        page.apply_redactions()
        logger.info(f"  Página {page_num + 1} procesada - {len(objects_to_remove)} elementos eliminados")
    
    # Guardar solo a partir de página 8
    doc.select([i for i in range(start_page, len(doc))])
    doc.save(output_path)
    doc.close()
    logger.info(f"PDF procesado guardado en: {output_path}")
    # os.remove(input_path)
    # logger.info(f"Eliminado archivo {os.path.basename(input_path)}")

    return doc

# Función alternativa para el símbolo de copyright
def remove_copyright_by_drawing(page, left_zone):
    """
    Intenta eliminar el copyright dibujando un rectángulo blanco sobre la zona.
    Útil cuando el copyright es gráfico o texto convertido a curvas.
    """
    # Crear un rectángulo blanco para cubrir la zona del copyright
    redact_rect = left_zone
    page.draw_rect(redact_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=False)
    logger.info("  Cubriendo zona izquierda con rectángulo blanco")

# Ejemplo de uso
if __name__ == "__main__":
    input_pdf = "U-SD04_dev.pdf"
    output_pdf = "output_clean.pdf"
    process_pdf_advanced(input_pdf, output_pdf)