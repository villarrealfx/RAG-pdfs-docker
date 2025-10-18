import os
import json
import logging
from typing import List, Dict
from dotenv import load_dotenv
from deepeval.metrics import (
    ContextualPrecisionMetric,
    FaithfulnessMetric,
    ContextualRecallMetric,
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    BiasMetric,
    HallucinationMetric
)
from deepeval.test_case import LLMTestCase
from deepeval.models import DeepSeekModel, GeminiModel
from pathlib import Path

# Cargando variables de entorno y Logger
load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Modelos para prueba
model_g = GeminiModel(
    model_name=os.getenv('EVAL_MODEL_GEMINI'),
    api_key=os.getenv('GOOGLE_API_KEY')
)
model = DeepSeekModel(
    api_key= os.getenv("OPENAI_API_KEY"),
    model= os.getenv("EVAL_MODEL_NAME")
)

# Cargando Data para prueba
file_path = Path(__file__).parent / "evaluation_dataset.json"
with open(file_path, 'r') as file:
    input_output_pairs = json.load(file)

test_data = input_output_pairs[9:11]

def run_all_tests() -> List[Dict]:
    """
    Ejecuta todas las métricas y devuelve una lista de resultados por cada entrada de test_data.
    """
    results = []
    for i, data in enumerate(test_data):
        query = data['query']
        actual_output = data["actual_output"]
        expected_output = data.get("expected_output")
        retrieval_context = data.get("retrieval_context", [])
        context = retrieval_context # para hallucination

        # Inicializar métricas
        relevancy_metric = AnswerRelevancyMetric(threshold=0, model=model, strict_mode=False)
        contextual_precision = ContextualPrecisionMetric(model=model, threshold=0, strict_mode=False)
        faithfulness = FaithfulnessMetric(model=model, threshold=0, strict_mode=False)
        contextual_recall = ContextualRecallMetric(model=model, threshold=0, strict_mode=False)
        contextual_relevancy = ContextualRelevancyMetric(model=model, threshold=0, strict_mode=False)
        hallucination = HallucinationMetric(model=model, threshold=0, strict_mode=False)

        # Crear test cases
        tc_relevancy = LLMTestCase(input=query, actual_output=actual_output)
        tc_precision = LLMTestCase(input=query, expected_output=expected_output, retrieval_context=retrieval_context)
        tc_faithfulness = LLMTestCase(input=query, actual_output=actual_output, retrieval_context=retrieval_context)
        tc_recall = LLMTestCase(input=query, expected_output=expected_output, retrieval_context=retrieval_context)
        tc_c_relevancy = LLMTestCase(input=query, expected_output=expected_output, retrieval_context=retrieval_context)
        tc_hallucination = LLMTestCase(input=query, actual_output=actual_output, context=context)

        # Medir
        score_relevancy = relevancy_metric.measure(tc_relevancy)
        score_precision = contextual_precision.measure(tc_precision)
        score_faithfulness = faithfulness.measure(tc_faithfulness)
        score_recall = contextual_recall.measure(tc_recall)
        score_c_relevancy = contextual_relevancy.measure(tc_c_relevancy)
        score_hallucination = hallucination.measure(tc_hallucination)

        results.append({
            "query": query,
            "index": i,
            "metrics": {
                "AnswerRelevancy": score_relevancy,
                "ContextualPrecision": score_precision,
                "Faithfulness": score_faithfulness,
                "ContextualRecall": score_recall,
                "ContextualRelevancy": score_c_relevancy,
                "Hallucination": score_hallucination,
            }
        })

    return results

# Función que puede ser llamada por tu endpoint
def get_test_results():
    return run_all_tests()