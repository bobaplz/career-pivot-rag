"""Query pipeline: embed question -> retrieve top-k chunks -> grounded generation.

Run from project root:  python -m src.rag_chain "your question here"
"""
import sys

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import config

load_dotenv()

# Sentinel the grounded prompt emits when the corpus can't answer —
# detected in code to trigger the general-knowledge fallback.
NOT_IN_CONTEXT = "NOT_IN_CONTEXT"

TRANSLATION_PROMPT = ChatPromptTemplate.from_template(
    """Rewrite the question in English so it can be used to search an English-language knowledge base.
If the question is already in English, return it unchanged.
Return only the rewritten question, nothing else.

Question: {question}"""
)

FALLBACK_PROMPT = ChatPromptTemplate.from_template(
    """You are a helpful assistant for analysts transitioning into data science.
The question is outside the knowledge base, so answer from your own general knowledge.
Be accurate. If you are not confident about a fact (e.g. future events, obscure
details, anything you might be misremembering), say you don't know — do not guess.
Answer in the same language the question is written in.

Question: {question}

Answer:"""
)

PROMPT = ChatPromptTemplate.from_template(
    """You are a helpful assistant for analysts transitioning into data science.
Answer in the same language the question is written in.
Ground your answer in the context below — it comes from the user's hand-written study notes.
Where the context is silent on a relevant detail, you may carefully supplement with
general knowledge, but never contradict the context.
Do not mention the notes, the context, or file names in your answer — sources are
shown separately in the UI.
If the context is entirely irrelevant to the question, reply with exactly NOT_IN_CONTEXT and nothing else.

Context:
{context}

Question: {question}

Answer:"""
)


def source_labels(docs):
    """Deduplicated '[file § section]' labels for the UI, from chunk metadata."""
    labels, seen = [], set()
    for doc in docs:
        source = doc.metadata.get("source", "unknown").removesuffix(".md")
        # Deepest header available = most specific section label
        section = doc.metadata.get("h3") or doc.metadata.get("h2") or doc.metadata.get("h1") or ""
        label = f"{source} § {section}" if section else source
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def build_chain():
    embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    vector_store = Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=config.CHROMA_PERSIST_DIR,
    )
    llm = ChatOpenAI(model=config.LLM_MODEL, temperature=0)
    translator = TRANSLATION_PROMPT | llm | StrOutputParser()

    def answer(question: str, category: str | None = None) -> dict:
        """Returns {"answer": str, "sources": [str, ...]}."""
        # Corpus is English: non-English questions retrieve poorly against it
        # (observed with Korean), so translate the query before embedding.
        # ASCII fast path keeps English questions at zero extra latency/cost.
        search_query = question
        if not question.isascii():
            search_query = translator.invoke({"question": question}).strip()

        # Category picker: restrict retrieval to one note file
        search_filter = None
        if category in config.CATEGORIES:
            search_filter = {"source": config.CATEGORIES[category]}

        docs = vector_store.similarity_search(
            search_query, k=config.TOP_K, filter=search_filter
        )
        context = "\n\n---\n\n".join(d.page_content for d in docs)
        chain = PROMPT | llm | StrOutputParser()
        result = chain.invoke({"context": context, "question": question})

        if NOT_IN_CONTEXT in result:
            if not config.GENERAL_KNOWLEDGE_FALLBACK:
                return {
                    "answer": "I don't know — this isn't covered by the knowledge base.",
                    "sources": [],
                }
            fallback = FALLBACK_PROMPT | llm | StrOutputParser()
            general = fallback.invoke({"question": question})
            return {
                "answer": (
                    "*💡 Not in my notes — answering from general knowledge:*\n\n"
                    + general
                ),
                "sources": [],
            }

        return {"answer": result, "sources": source_labels(docs)}

    return answer


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Why does NOT IN return no rows when the subquery has NULLs?"
    answer = build_chain()
    result = answer(question)
    print(result["answer"])
    if result["sources"]:
        print("\n--- Sources ---")
        for label in result["sources"]:
            print(f"  {label}")
