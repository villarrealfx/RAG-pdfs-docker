import os
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, FewShotChatMessagePromptTemplate
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

# langchain-deepseek

api_key = os.getenv('OPENAI_API_KEY')
model = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)

embeddings_model_name = "BAAI/bge-small-en"
model_kwargs = {"device": "cpu"}
encode_kwargs = {"normalize_embeddings": True}
embeddings_model = HuggingFaceBgeEmbeddings(
                model_name=embeddings_model_name, model_kwargs=model_kwargs, encode_kwargs=encode_kwargs
)

system_rewrite = """You are a helpful assistant that generates multiple search queries based on a single input query.

Perform query expansion. If there are multiple common ways of phrasing a user question
or common synonyms for key words in the question, make sure to return multiple versions
of the query with the different phrasings.

If there are acronyms or words you are not familiar with, do not try to rephrase them.

Return 3 different versions of the question."""

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_rewrite),
        ("human", "{question}"),
    ]
)

chain = prompt | model

response = chain.invoke({
    "question": "Which food items does this recipe need?"
})
