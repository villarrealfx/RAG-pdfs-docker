import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Any

def run_deepeval_tests() -> Dict[str, Any]:
    """
    Ejecuta los tests de DeepEval y devuelve un diccionario con los resultados.
    """
    # Ruta base
    base_dir = Path(__file__).resolve().parent.parent.parent
    eval_dir = base_dir / "rag_pdf_processor" / "evaluations"

    # Archivos de tests
    test_files = [
        eval_dir / "test_deepeval_01.py",
        eval_dir / "test_geval.py"
    ]

    all_results = {}

    for test_file in test_files:
        if not test_file.exists():
            all_results[test_file.name] = {"error": f"Archivo no encontrado: {test_file}"}
            continue

        output_file = test_file.with_name(f"results_{test_file.stem}.json")

        # Ejecutar pytest con json-report
        cmd = [
            "python", "-m", "pytest",
            str(test_file),
            "--json-report",
            f"--json-report-file={output_file}",
            "-v"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            all_results[test_file.name] = {
                "error": result.stderr,
                "stdout": result.stdout
            }
        else:
            # Leer el archivo JSON generado
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                all_results[test_file.name] = data
            else:
                all_results[test_file.name] = {"error": "Archivo de resultados no generado."}

    return all_results