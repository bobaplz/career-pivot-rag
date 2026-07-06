# career-pivot-rag

RAG (Retrieval-Augmented Generation) chatbot over my personal data-analytics study notes — SQL, pandas, A/B testing, ML model selection, and RAG concepts.

## Stack

- **LangChain** — pipeline orchestration
- **OpenAI** — `text-embedding-3-small` embeddings, `gpt-4o-mini` generation
- **Chroma** — local persistent vector store
- **Streamlit** — chat UI

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
```

## Usage

```bash
# 1. Index the knowledge base (markdown -> chunks -> embeddings -> chroma_db/)
python -m src.ingest

# 2a. Ask from the CLI
python -m src.rag_chain "What does a p-value below 0.05 actually mean?"

# 2b. Or chat in the browser
streamlit run app.py
```

## How it works

- **Indexing** (`src/ingest.py`): each markdown file is split on headings (`MarkdownHeaderTextSplitter`), then capped at 2000 chars with 200 overlap. Chunks carry `source` and header metadata for citations.
- **Query** (`src/rag_chain.py`): the question is embedded with the same model, top-4 chunks are retrieved from Chroma, and the LLM answers *only* from that context, citing sources as `[file § section]` — or says it doesn't know.
