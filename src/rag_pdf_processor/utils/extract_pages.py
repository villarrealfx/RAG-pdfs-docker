import fitz  # PyMuPDF
import os

def extract_pages(input_pdf_path, output_pdf_path, start_page, end_page):
    """
    Extrae un rango de páginas de un PDF y guarda el resultado en un nuevo archivo.

    Args:
        input_pdf_path (str): Ruta al archivo PDF de entrada.
        output_pdf_path (str): Ruta donde se guardará el PDF resultante.
        start_page (int): Número de la primera página a incluir (1-indexed).
        end_page (int): Número de la última página a incluir (1-indexed).
    """
    # Asegúrate de que los números de página sean válidos
    doc = fitz.open(input_pdf_path)
    total_pages = len(doc)

    # Convertir a 0-indexed para PyMuPDF
    start_index = start_page - 1
    end_index = end_page - 1

    if start_index < 0 or end_index >= total_pages or start_index > end_index:
        print(f"Error: El rango de páginas {start_page}-{end_page} no es válido para un PDF de {total_pages} páginas.")
        doc.close()
        return

    # Seleccionar solo las páginas deseadas
    doc.select([i for i in range(start_index, end_index + 1)])

    # Guardar el nuevo PDF
    doc.save(output_pdf_path)
    doc.close()
    print(f"✅ PDF extraído guardado como: {output_pdf_path}")

def main():
    """Función principal para interactuar con el usuario."""
    # Obtener el nombre del script y asumir que el PDF está en el mismo directorio
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Opcional: Solicitar nombre del archivo PDF
    pdf_filename = input("Ingresa el nombre del archivo PDF (incluyendo la extensión .pdf): ")
    input_pdf_path = os.path.join(script_dir, pdf_filename)

    if not os.path.exists(input_pdf_path):
        print(f"❌ Error: No se encontró el archivo {input_pdf_path}")
        return

    try:
        start_page = int(input("Ingresa el número de la página de inicio (primera página es 1): "))
        end_page = int(input("Ingresa el número de la página final: "))
    except ValueError:
        print("❌ Error: Por favor, ingresa números válidos para las páginas.")
        return

    # Nombre del archivo de salida
    base_name, ext = os.path.splitext(pdf_filename)
    output_pdf_path = os.path.join(script_dir, f"{base_name}_extracted_pages_{start_page}_to_{end_page}{ext}")

    print(f"\n📄 Procesando '{pdf_filename}'...")
    print(f"✂️  Extrayendo páginas {start_page} a {end_page}...")
    extract_pages(input_pdf_path, output_pdf_path, start_page, end_page)

if __name__ == "__main__":
    main()