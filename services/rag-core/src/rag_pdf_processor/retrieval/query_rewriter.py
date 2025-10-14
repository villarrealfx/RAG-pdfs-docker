import logging
from typing import List, Optional
from rag_pdf_processor.retrieval.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

class QueryRewriter:
    """
    Sistema para reescribir o reformular consultas antes de la búsqueda.
    Utiliza un LLM para mejorar la intención o claridad de la consulta original.
    """
    def __init__(self, llm_interface: LLMInterface):
        """
        Inicializa el QueryRewriter con una instancia de LLMInterface.

        Args:
            llm_interface: Instancia de LLMInterface ya configurada.
        """
        self.llm_interface = llm_interface
        logger.info("✅ QueryRewriter inicializado")

    def rewrite_query(self, original_query: str) -> str:
        """
        Reescribe la consulta original utilizando el LLM.

        Args:
            original_query: La consulta original del usuario.

        Returns:
            La consulta reescrita.
        """
        try:
            logger.debug(f"🔄 Reescribiendo consulta: '{original_query}'")

            # Prompt para que el LLM reformule la consulta
            # Puedes experimentar con diferentes prompts para diferentes estrategias
            system_prompt = """
            You are an expert query rewriter for a technical document search system.
            Your task is to take the user's original query and reformulate it to be more effective for searching technical documentation.
            Focus on:
            - Clarifying ambiguous terms or acronyms if context allows.
            - Expanding the query with relevant synonyms or related terms if it seems too specific or uses jargon.
            - Breaking down complex multi-part queries into a more focused single search query that captures the main intent.
            - Preserving the core meaning and intent of the user's original question.
            - Respond with ONLY the reformulated query, nothing else.
            """

            user_prompt = f"Reformulate this query: {original_query}"

            # Llamar al LLM para reformular
            rewritten_query = self.llm_interface.generate_response(
                query=user_prompt,
                context_chunks=[], # No contexto necesario para reformular la consulta
                max_tokens=100, # Longitud razonable para una consulta reformulada
                system_prompt_override=system_prompt # Pasar el system prompt específico
            ).strip()

            # Asegurarse de devolver una consulta no vacía
            if not rewritten_query or rewritten_query.lower() == "none" or rewritten_query.lower() == "null":
                logger.warning(f"⚠️ El LLM devolvió una consulta vacía o inválida. Usando la original: '{original_query}'")
                return original_query

            logger.debug(f"✅ Consulta reescrita: '{original_query}' -> '{rewritten_query}'")
            return rewritten_query

        except Exception as e:
            logger.error(f"❌ Error reescribiendo la consulta '{original_query}': {e}")
            # En caso de error, devolver la consulta original
            return original_query

    # Opcional: Estrategias alternativas
    def rewrite_query_expansion(self, original_query: str) -> str:
        """
        Estrategia alternativa: Expande la consulta original con sinónimos o términos relacionados
        (usando LLM para generarlos).
        """
        try:
            logger.debug(f"🔄 Expandiendo consulta: '{original_query}'")

            system_prompt = """
            You are an expert at expanding search queries for a technical document search system.
            Your task is to take the user's original query and add synonyms, related terms, or alternative phrasings
            that might help find relevant documents.
            List the original terms and their expansions, then combine them into a single improved query.
            Respond with ONLY the expanded query, nothing else.
            """

            user_prompt = f"Expand this query with synonyms and related terms: {original_query}"

            expanded_query = self.llm_interface.generate_response(
                query=user_prompt,
                context_chunks=[],
                max_tokens=150,
                system_prompt_override=system_prompt
            ).strip()

            if not expanded_query or expanded_query.lower() == "none" or expanded_query.lower() == "null":
                 logger.warning(f"⚠️ El LLM devolvió una consulta expandida vacía o inválida. Usando la original: '{original_query}'")
                 return original_query

            logger.debug(f"✅ Consulta expandida: '{original_query}' -> '{expanded_query}'")
            return expanded_query

        except Exception as e:
            logger.error(f"❌ Error expandiendo la consulta '{original_query}': {e}")
            return original_query
        
    # En la clase QueryRewriter

    def expand_query_multiple(self, original_query: str, num_queries: int = 3) -> List[str]:
        """
        Expande la consulta original en múltiples variantes usando el LLM.

        Args:
            original_query: La consulta original del usuario.
            num_queries: Número de variantes a generar (por defecto 3).

        Returns:
            Una lista de consultas expandidas.
        """
        try:
            logger.debug(f"🔄 Expandiendo consulta en {num_queries} variantes: '{original_query}'")

            system_prompt = f"""
            You are a helpful assistant that generates multiple search queries based on a single input query.

            Perform query expansion. If there are multiple common ways of phrasing a user question
            or common synonyms for key words in the question, make sure to return multiple versions
            of the query with the different phrasings.

            If there are acronyms or words you are not familiar with, do not try to rephrase them.

            Return exactly {num_queries} different versions of the question, each on a new line.
            Do not number them or add extra text, just the queries.
            """

            user_prompt = original_query

            # Llamar al LLM para generar las consultas
            response_text = self.llm_interface.generate_response(
                query=user_prompt,
                context_chunks=[],
                max_tokens=200, # Ajusta según sea necesario
                system_prompt_override=system_prompt
            )

            # Separar por saltos de línea y limpiar
            queries = [q.strip() for q in response_text.split('\n') if q.strip()]

            # Asegurarse de devolver al menos la original si no hay resultados válidos
            if not queries or all(q.lower() in ["none", "null"] for q in queries):
                logger.warning(f"⚠️ El LLM no devolvió consultas válidas. Usando la original: '{original_query}'")
                return [original_query]

            # Filtrar consultas vacías o inválidas
            queries = [q for q in queries if q.lower() not in ["none", "null"]]

            logger.debug(f"✅ Consultas expandidas generadas: {queries}")
            return queries

        except Exception as e:
            logger.error(f"❌ Error expandiendo la consulta '{original_query}': {e}")
            # En caso de error, devolver la consulta original como fallback
            return [original_query]
