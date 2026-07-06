"""Central configuration — every tunable knob in one place."""

KNOWLEDGE_BASE_DIR = "knowledge_base"
CHROMA_PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "career_pivot_kb"

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"
TOP_K = 4

# When the corpus can't answer, fall back to the LLM's general knowledge
# (clearly labeled). Set False for strict grounded-only mode.
GENERAL_KNOWLEDGE_FALLBACK = True

# Category picker (UI label -> source file): restricts retrieval to one note.
CATEGORIES = {
    "sql": "sql-reference-and-common-mistakes.md",
    "pandas": "pandas-patterns-for-analysts.md",
    "ab_testing": "ab-testing-stats-essentials.md",
    "ml": "choosing-an-ml-model.md",
    "rag": "rag-concepts.md",
}

# Chunking: split on markdown headers first, then enforce a max size
HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]
MAX_CHUNK_SIZE = 2000      # characters (~500 tokens) — oversized sections get re-split
CHUNK_OVERLAP = 200
