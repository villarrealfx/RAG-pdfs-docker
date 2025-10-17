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
    ContextualPrecisionMetric
)
from deepeval.metrics import BiasMetric
from deepeval.test_case import LLMTestCase
from deepeval.models import DeepSeekModel

try:
    from rag_pdf_processor.retrieval.vector_retriever import VectorRetriever
    from rag_pdf_processor.retrieval.llm_interface import LLMInterface
    from rag_pdf_processor.retrieval.query_rewriter import QueryRewriter
except ImportError as e:
    logging.error(f"❌ Error importando rag_pdf_processor en FastAPI: {e}")

model = DeepSeekModel(
    api_key= os.getenv("OPENAI_API_KEY"),
    model= os.getenv("EVAL_MODEL_NAME")
)


load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

bias = BiasMetric(model=model, threshold=0.25)
contextual_precision = ContextualPrecisionMetric(model=model,threshold=0.25)
contextual_recall = ContextualRecallMetric(model=model,threshold=0.25)
answer_relevancy = AnswerRelevancyMetric(model=model,threshold=0.25)
faithfulness = FaithfulnessMetric(model=model,threshold=0.25)
precision = ContextualPrecisionMetric(model=model, threshold=0.25)

evaluation_metrics = [
  bias,
  contextual_precision,
  contextual_recall,
  answer_relevancy,
  faithfulness,
  precision
]

file_path = "evaluation_dataset.json"
with open(file_path, 'r') as file:
    # Carga los datos del archivo JSON
    input_output_pairs = json.load(file)

logger.info("🔄 Inicializando componentes RAG...")
try:
    vector_store = VectorRetriever(collection_name="retrieval_context-hybrid")
    logger.info("✅ Vector Store (Qdrant) inicializado.")
except Exception as e:
    logger.error(f"Error inicializando Vector Store: {e}")
    raise

try:
    llm_interface = LLMInterface()
    logger.info("✅ LLM Interface inicializado.")
except Exception as e:
    logger.error(f"Error inicializando LLM Interface: {e}")
    raise

try:
    query_rewriter = QueryRewriter(llm_interface)
    logger.info("✅ Query Rewriter inicializado.")
except Exception as e:
    logger.error(f"Error inicializando Query Rewriter: {e}")
    raise

@pytest.mark.parametrize(
    "input_output_pair",
    input_output_pairs
)
def test_rag_pdfs(input_output_pair: Dict):
    
    input = input_output_pair.get("query", None)
    expected_output = input_output_pair.get("expected_output", None)

    retrieval_context_retrieved = vector_store.hybrid_search_with_rerank(  
                        input, 
                        limit=5, 
                        use_rerank=True  # use_rerank
            )
 
    context_retrieval_context_for_llm = [
            {
                "chunk_id": chunk["id"],
                "content": chunk["content"],
                "source_document": f'book: {chunk["book_name"]} - chapter: {chunk["chapter"]}',
                "relevance_score": chunk["rerank_score"],  # get("score", 0.0),
                "original_score": chunk["original_score"],  # .get("original_score", 0.0),
                "text_preview": chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else ""),
                }
            for chunk in retrieval_context_retrieved
        ]
    

    actual_output = llm_interface.generate_response(
                query=input,
                context_retrieval_context=context_retrieval_context_for_llm,
                max_tokens=500,
                temperature= 0  # temperature
        )
    retrieval_context = [chunk["content"] for chunk in context_retrieval_context_for_llm]


    test_case = LLMTestCase(
        input=input,
        actual_output=actual_output,
        retrieval_context=retrieval_context,
        expected_output=expected_output
    )
    # assert test case
    assert_test(test_case, evaluation_metrics)