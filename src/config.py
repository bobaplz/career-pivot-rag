"""Central configuration — every tunable knob in one place."""

KNOWLEDGE_BASE_DIR = "knowledge_base"
CHROMA_PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "career_pivot_kb"

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"
TOP_K = 4

# Chunking: split on markdown headers first, then enforce a max size
HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]
MAX_CHUNK_SIZE = 2000      # characters (~500 tokens) — oversized sections get re-split
CHUNK_OVERLAP = 200
