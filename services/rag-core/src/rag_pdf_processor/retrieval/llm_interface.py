import logging
import os
from typing import List, Dict, Optional
from openai import OpenAI
from langdetect import detect
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger(__name__)

class LLMInterface:
    """Interfaz con LLM vía API con soporte multilenguaje"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "deepseek-chat",
                 api_base: Optional[str] = None):
        """
        Inicializar interfaz con LLM vía API
        
        Args:
            api_key: Clave API (si no se provee, busca en env)
            model: Modelo a usar (gpt-3.5-turbo, gpt-4, etc.)
            api_base: URL base (para otros proveedores)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model or os.getenv('MODEL')
        
        if not self.api_key:
            logger.warning("⚠️ No se encontró API key. Se usará modo simulado.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=os.getenv('OPENAI_BASE_URL')
            )
            logger.info(f"✅ LLMInterface inicializado con modelo: {model}")
    
    def detect_language(self, text: str) -> str:
        """
        Detectar idioma de la entrada
        
        Args:
            text: Texto a analizar
            
        Returns:
            Código de idioma (ej: 'es', 'en', 'fr')
        """
        try:
            detected_lang = detect(text)
            return detected_lang
        except:
            # Si no se puede detectar, asumir inglés (porque la KB es en inglés)
            logger.debug("No se pudo detectar idioma, asumiendo inglés")
            return 'en'
    

    def generate_response(self, query: str, context_retrieval_context: List[Dict], max_tokens: int = 500, system_prompt_override: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """
        Generar respuesta usando LLM vía API

        Args:
            query: Pregunta del usuario (o instrucción para reformular)
            context_retrieval_context: retrieval_context recuperados del vector store (puede ser vacío para reformulación)
            max_tokens: Máximo de tokens en la respuesta
            system_prompt_override: Opcional. Permitir sobrescribir el system prompt estándar (útil para reformular consultas).
            temperature: Opcional. Permitir sobrescribir la temperatura usada por el modelo (0.0 a 2.0, valores más bajos son más deterministas).

        Returns:
            Respuesta generada por el LLM
        """
        try:
            if not self.client:
                # Modo simulado si no hay API key
                return self._simulate_response(query, context_retrieval_context)

            # Detectar idioma de la pregunta
            query_language = self.detect_language(query)

            # Usar el system_prompt_override si se proporciona, sino el estándar
            if system_prompt_override:
                system_prompt = system_prompt_override
            else:
                system_prompt = f"""You are an expert assistant that answers questions based on technical documents.
                - Use only the information provided in the context
                - If the answer is not in the context, say you cannot answer with the available information
                - Be clear, precise and professional
                - Format your response in a readable way
                - Respond in the same language as the user's question: {query_language}
                - If the question is in Spanish, respond in Spanish. If in English, respond in English."""

            # Construir contexto (en inglés, porque la KB es en inglés)
            context = "\n".join([
                f"Document: {chunk['source_document']} \nContent: {chunk['content']}"
                for chunk in context_retrieval_context
            ])

            user_prompt = f"""
                Query: {query}

                Context:
                {context}

                Please answer the query based only on the provided context if applicable, or follow the instructions if it's a task like rewriting.
                """

            # Usar la temperatura proporcionada, o la del objeto si no se especifica
            temp_to_use = temperature if temperature is not None else 0.3 # Usar 0.3 como valor por defecto si no está en __init__

            # Llamar a la API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=temp_to_use # Usar la temperatura especificada
            )

            answer = response.choices[0].message.content.strip()

            # ... logging ...
            logger.debug(f"📝 LLM generated response of {len(answer)} characters",
                        extra={
                            "query_length": len(query),
                            "context_retrieval_context": len(context_retrieval_context),
                            "model": self.model,
                            "query_language": query_language,
                            "response_language": self.detect_language(answer) if len(answer) > 10 else "unknown",
                            "temperature_used": temp_to_use # Añadir temperatura usada al log
                        })

            return answer

        except Exception as e:
            logger.error(f"❌ Error generating response: {e}")
            return "Sorry, there was an error generating the response. Please try again."

        
    def _simulate_response(self, query: str, context_retrieval_context: List[Dict]) -> str:
        """
        Respuesta simulada cuando no hay API key
        
        Args:
            query: Pregunta del usuario
            context_retrieval_context: retrieval_context recuperados
            
        Returns:
            Respuesta simulada
        """
        query_language = self.detect_language(query)
        logger.warning(f"⚠️ Usando modo simulado (no hay API key). Idioma: {query_language}")
        
        return f"[Simulado] Para la pregunta: '{query[:50]}...' (usando {len(context_retrieval_context)} retrieval_context). Idioma detectado: {query_language}"