import os
import json
from typing import List, Dict
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics.g_eval import Rubric
from deepeval.models import DeepSeekModel, GeminiModel
from dotenv import load_dotenv
from pathlib import Path
load_dotenv()

model_g = GeminiModel(
    model_name=os.getenv('EVAL_MODEL_GEMINI'),
    api_key=os.getenv('GOOGLE_API_KEY')
)
model = DeepSeekModel(
    api_key= os.getenv("OPENAI_API_KEY"),
    model= os.getenv("EVAL_MODEL_NAME")
)

# --- MÉTRICAS (igual que antes) ---
scada_faithfulness_metric = GEval(
    name="SCADA Faithfulness",
    model=model,
    evaluation_params=[
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.RETRIEVAL_CONTEXT],
    evaluation_steps=[
        "Extract key technical claims (e.g., procedures, standards, values, component names) from the (actual_output).",
        "Compare each claim against the 'Retrieved Context'(retrieval_context).",
        "Identify any claims in the output that are not directly supported by the content of the retrieved chunks.",
        "Detect domain-specific hallucinations (e.g., incorrect procedural steps, erroneous technical values, unmentioned standards).",
        "Penalize severely any unsupported claims, particularly those that could lead to operational errors.",
        "Assign an overall faithfulness score based on the ratio of supported versus hallucinated claims."
    ],
    threshold=0,
)

correctness_metric = GEval(
    name="Correctness vs Expert",
    model=model,
    evaluation_params=[
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.EXPECTED_OUTPUT],
    evaluation_steps=[
        "Compare the (actual_output) with the 'expert answer' (expected_output).",
        "Verify whether the facts, procedures, or technical data mentioned in both outputs match or are equivalent.",
        "Assess if the 'Actual Output' covers the same key points as the 'Expected Output'.",
        "Identify any contradictions or significant errors in the 'Actual Output' when compared to the 'Expected Output'.",
        "Assign an overall correctness score based on the similarity and accuracy relative to the expert answer."
        ],
    threshold=0,
)

technical_clarity_metric = GEval(
    name="Technical Clarity",
    model=model,
    evaluation_params=[
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    evaluation_steps=[
        "Evaluate whether the 'Actual Output' is clear and understandable for a SCADA operator or technician.",
        "Verify if appropriate technical terms are used and whether they are explained when necessary.",
        "Determine if the response structure is logical and follows a coherent sequence (e.g., diagnosis, procedure, precautions).",
        "Identify if the response is concise and avoids irrelevant or redundant information.",
        "Assign an overall technical clarity score to the response."
    ],
    threshold=0,
)

evaluation_metrics = [
    scada_faithfulness_metric,
    correctness_metric,
    technical_clarity_metric
]

# Cargando Data para prueba
file_path = Path(__file__).parent / "evaluation_dataset.json"
with open(file_path, 'r') as file:
    input_output_pairs = json.load(file)

test_data = input_output_pairs[9:11]

def run_geval_tests() -> List[Dict]:
    """
    Ejecuta las métricas GEval y devuelve una lista de resultados por cada entrada de test_data.
    """
    results = []
    for i, data in enumerate(test_data):
        test_case = LLMTestCase(
                input= data['query'],
                actual_output= data["actual_output"],
                expected_output= data['expected_output'],
                retrieval_context= data["retrieval_context"],
                )

        # Medir cada métrica individualmente
        score_faithfulness = scada_faithfulness_metric.measure(test_case)
        score_correctness = correctness_metric.measure(test_case)
        score_clarity = technical_clarity_metric.measure(test_case)

        results.append({
            "query": data['query'],
            "index": i,
            "metrics": {
                "SCADA_Faithfulness": score_faithfulness,
                "Correctness_vs_Expert": score_correctness,
                "Technical_Clarity": score_clarity
            }
        })

    return results

def get_test_results():
    return run_geval_tests()