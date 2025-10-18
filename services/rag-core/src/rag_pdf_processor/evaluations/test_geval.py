import os
import json
from pathlib import Path
from deepeval import assert_test 
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics.g_eval import Rubric # Opcional, para rubricas

from deepeval.models import DeepSeekModel, GeminiModel
from dotenv import load_dotenv 
load_dotenv()

# Modelos para prueba
model = GeminiModel(
    model_name=os.getenv('EVAL_MODEL_GEMINI'),
    api_key=os.getenv('GOOGLE_API_KEY')
)
model_d = DeepSeekModel(
    api_key= os.getenv("OPENAI_API_KEY"),
    model= os.getenv("EVAL_MODEL_NAME")
)

# --- 1. Métrica de Fidelidad Técnica (RAG Specific) ---
# Evalúa si la respuesta del LLM se basa fielmente en los chunks recuperados, penalizando alucinaciones técnicas.

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

# --- 2. Métrica de Corrección vs. Experto (Reference-based) ---
# Evalúa si la respuesta del LLM es tan correcta como la respuesta de un experto humano.
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

# --- 3. Métrica de Claridad Técnica (Referenceless) ---
# Evalúa si la respuesta es clara, concisa y adecuada para un técnico.
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


# Lista para pasar a evaluate o assert_test
evaluation_metrics = [
    scada_faithfulness_metric,
    correctness_metric,
    technical_clarity_metric
]

# Cargando Data para prueba
file_path = Path(__file__).parent / "evaluation_dataset.json"
with open(file_path, 'r') as file:
    # Carga los datos del archivo JSON
    input_output_pairs = json.load(file)

test_data = input_output_pairs[9:10]  #[9:]


def test_geval_metrics():
    for data in test_data:
        test_case = LLMTestCase(
                input= data['query'],
                actual_output= data["actual_output"],
                expected_output= data['expected_output'],
                retrieval_context= data["retrieval_context"],
                )
        assert_test(test_case, evaluation_metrics)
    
