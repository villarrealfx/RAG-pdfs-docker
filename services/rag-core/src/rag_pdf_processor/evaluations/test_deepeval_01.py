import os
import json
import pytest
import logging
from typing import List, Optional, Dict, Tuple
from dotenv import load_dotenv

from deepeval import assert_test
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
file_path = "evaluation_dataset.json"
with open(file_path, 'r') as file:
    # Carga los datos del archivo JSON
    input_output_pairs = json.load(file)

test_data = input_output_pairs[9:]

# Funciones de Pruebas deepeval
def  test_relevancy (): 
    # Define la métrica con un umbral.
    relevancy_metric = AnswerRelevancyMetric(threshold= 0 , model= model, strict_mode=False )

    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            actual_output = data["actual_output"],
            # retrieval_context=data[retrieval_context], 
        ) 
        
        assert_test(test_case, [relevancy_metric])

def test_contextual_precision():
    contextual_precision = ContextualPrecisionMetric(model=model,threshold=0, strict_mode=False)
    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            expected_output = data["expected_output"],
            retrieval_context=data["retrieval_context"], 
        ) 
        
        assert_test(test_case, [contextual_precision])

def test_faithfulness():
    faithfulness = FaithfulnessMetric(model=model,threshold=0, strict_mode=False)
    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            actual_output = data["actual_output"],
            retrieval_context=data["retrieval_context"],
        ) 
        
        assert_test(test_case, [faithfulness])
       
def test_contextual_recall():
    contextual_recall = ContextualRecallMetric(model=model,threshold=0, strict_mode=False)
    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            expected_output = data["expected_output"],
            retrieval_context=data["retrieval_context"], 
        ) 
        
        assert_test(test_case, [contextual_recall])

def test_contextual_relevancy():
    contextual_relevancy = ContextualRelevancyMetric(model=model,threshold=0, strict_mode=False)
    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            expected_output = data["expected_output"],
            retrieval_context=data["retrieval_context"], 
        ) 
        
        assert_test(test_case, [contextual_relevancy])

def test_hallucination():
    hallucination = HallucinationMetric(model=model,threshold=0, strict_mode=False)
    for data in test_data:
    
        # Caso 1: Respuesta parcialmente relevante.
        test_case = LLMTestCase( 
            input = data['query'], 
            actual_output = data["actual_output"],
            context=data["retrieval_context"], 
        ) 
        
        assert_test(test_case, [hallucination])


# deepeval test run test_deepeval.py::nombre_de_la_funcion_test
# pytest test_deepeval.py::nombre_de_la_funcion_test -v
# 