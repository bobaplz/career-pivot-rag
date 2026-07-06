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

PROMPT = ChatPromptTemplate.from_template(
    """You are a helpful assistant for analysts transitioning into data science.
Answer the question using ONLY the context below.
If the context doesn't contain the answer, say you don't know — do not guess.
Each context chunk begins with a bracketed label like [filename.md § Section Title].
Cite the source of each claim inline by copying that exact label.

Context:
{context}

Question: {question}

Answer:"""
)


def format_chunk(doc):
    """Render one retrieved chunk with its citation metadata."""
    source = doc.metadata.get("source", "unknown")
    # Deepest header available = most specific section label
    section = doc.metadata.get("h3") or doc.metadata.get("h2") or doc.metadata.get("h1") or ""
    return f"[{source} § {section}]\n{doc.page_content}"


def build_chain():
    embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    vector_store = Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=config.CHROMA_PERSIST_DIR,
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": config.TOP_K})
    llm = ChatOpenAI(model=config.LLM_MODEL, temperature=0)

    def answer(question: str) -> str:
        docs = retriever.invoke(question)
        context = "\n\n---\n\n".join(format_chunk(d) for d in docs)
        chain = PROMPT | llm | StrOutputParser()
        return chain.invoke({"context": context, "question": question})

    return answer


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Why does NOT IN return no rows when the subquery has NULLs?"
    answer = build_chain()
    print(answer(question))
