# run_test_scores.py
from rag_pdf_processor.evaluations.test_deepeval_scores import get_test_results as get_deepeval_scores
from rag_pdf_processor.evaluations.test_geval_scores import get_test_results as get_geval_scores

def run_deepeval_test_scores() -> dict:
    """
    Ejecuta los tests y devuelve los scores reales de cada métrica.
    """
    deepeval_results = get_deepeval_scores()
    geval_results = get_geval_scores()

    return {
        "deepeval_01": deepeval_results,
        "geval": geval_results
    }